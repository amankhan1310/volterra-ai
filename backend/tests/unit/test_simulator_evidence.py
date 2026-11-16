"""Phase 8: the committed simulator evidence and the offline baseline validation tool."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.services.evidence import DATA_DIR, load_evidence
from app.validation import simulator_baseline as sb
from tests.support.api import client_for, memory_app

pytestmark = pytest.mark.anyio


def test_committed_evidence_is_valid_and_says_assumed() -> None:
    e = load_evidence()
    assert e.stress.temperature.provenance == "assumed"
    assert e.stress.c_rate.provenance == "assumed"
    assert e.stress.dod.provenance == "assumed" and "not varied" in e.stress.dod.note
    t = e.stress.temperature.evidence
    lo, hi = t.observed_ratio_ci90
    assert lo <= t.observed_ratio <= hi
    assert t.assumed_within_ci == (lo <= t.assumed_factor_for_this_delta <= hi)
    assert "load" in t.confounder
    assert e.baseline_validation.dataset == "severson-2019"
    assert set(e.baseline_validation.results) == set(sb.METHODS)


def test_evidence_files_hold_aggregates_only() -> None:
    for name in ("stress_evidence.json", "baseline_validation.json"):
        path = DATA_DIR / name
        assert path.stat().st_size < 20_000, name  # summaries, not data


async def test_evidence_endpoint() -> None:
    app, _ = memory_app()
    async with client_for(app) as client:
        body = (await client.get("/api/v1/simulator/evidence")).json()
    assert body["stress"]["schema_version"] == 1
    assert body["stress"]["temperature"]["provenance"] == "assumed"
    assert "assumed, not fitted" in body["note"]


def _bundle(root: Path) -> Path:
    """Three generated Severson-style cells (made-up values) with documented lives."""
    out = root / sb.SEVERSON
    out.mkdir(parents=True)
    (out / "bundle_manifest.json").write_text(
        json.dumps({"dataset": {"slug": "severson-2019"}, "bundle_checksum": "x" * 64})
    )
    lives = {"c1": 600.0, "c2": 400.0, "c3": 100.0}
    batteries = [
        {"external_id": k, "test_conditions_json": json.dumps({"cycle_life_source": str(v)})}
        for k, v in lives.items()
    ] + [
        {
            "external_id": "x1",
            "test_conditions_json": json.dumps(
                {"cycle_life_source": "500", "dataset_flags": {"paper_excluded": "y"}}
            ),
        }
    ]
    pq.write_table(pa.Table.from_pylist(batteries), out / "batteries.parquet")
    rows = []
    for eid, life in [*lives.items(), ("x1", 500.0)]:
        for n in range(int(life)):
            soh = 98.0 - 18.0 * (n / life) ** 2
            rows.append({"external_id": eid, "cycle_index": n, "capacity_ah": soh / 100 * 1.1,
                         "soh_pct": soh, "temp_mean_c": 30.0, "voltage_mean_v": 3.2,
                         "quality_flags_json": "{}"})  # fmt: skip
        rows.append({"external_id": eid, "cycle_index": int(life) + 1, "capacity_ah": 0.0,
                     "soh_pct": 0.0, "temp_mean_c": None, "voltage_mean_v": None,
                     "quality_flags_json": json.dumps({"capacity_zero": "x"})})  # fmt: skip
    pq.write_table(pa.Table.from_pylist(rows), out / "cycles.parquet")
    return root


def test_baseline_validation_on_generated_cells(tmp_path: Path, capsys) -> None:
    root = _bundle(tmp_path)
    cells = sb.load_cells(root / sb.SEVERSON)
    assert [c[0] for c in cells] == ["c1", "c2", "c3"]  # excluded cell and placeholder dropped
    assert all(len(r) == int(life) for _, life, r in cells)
    result = sb.validate(root)
    assert result["cells"] == 2 and result["cells_skipped_short"] == 1  # c3 is shorter than 120
    late = result["results"]["v2_quadratic"]["0.9"]
    assert late["n"] == 2 and late["mae_cycles"] < 60  # a quadratic fade, seen late: close
    early = result["results"]["v1_overview_linear"]["0.5"]
    assert early["n"] + early["no_estimate"] == 2
    out = tmp_path / "v.json"
    assert sb.main(["--data-dir", str(root), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["schema"] == 1 and "v2_quadratic" in capsys.readouterr().out


def test_summary_handles_no_estimates() -> None:
    assert sb.summarise([], 3) == {"n": 0, "no_estimate": 3}
    s = sb.summarise([(110.0, 100.0), (50.0, 100.0)], 1)
    assert s["mae_cycles"] == 30.0 and s["bias_cycles"] == -20.0 and s["within_20_pct"] == 0.5
    assert math.isclose(s["median_abs_error_cycles"], 30.0)
