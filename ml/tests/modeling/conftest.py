"""Generated bundles for the modelling tests (synthetic values, never real data).

Each cell fades along ``soh = start - a*n - b*(n/life)^4`` with measurement noise, so cells have a
knee and a known life; some cells stop before EOL (censored) and one has a capacity dip that
recovers (like NASA regeneration). Only the columns ``load_bundle`` reads are written.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from volterra_ml.modeling.data import CHANNELS, Cell, FloatArray


def make_cell(
    life: int,
    observed: int,
    seed: int,
    *,
    dataset: str = "gen",
    eid: str = "c0",
    reported_life: float | None = None,
    channels: bool = True,
) -> Cell:
    rng = np.random.default_rng(seed)
    n = np.arange(observed, dtype=np.float64)
    soh = 98.0 - 6.0 * n / life - 12.0 * (n / life) ** 4 + rng.normal(0.0, 0.15, observed)
    ch: dict[str, FloatArray] = {c: np.full(observed, np.nan) for c in CHANNELS}
    if channels:
        ch["internal_resistance_ohm"] = (
            0.015 + 0.004 * (n / life) ** 2 + rng.normal(0, 1e-4, observed)
        )
        ch["temp_mean_c"] = 30.0 + 2.0 * n / life + rng.normal(0, 0.2, observed)
        ch["charge_time_s"] = np.full(observed, 600.0 + 3000.0 / life * 100)
    return Cell(dataset, eid, "generated", 1.1, n, soh, ch, None, reported_life)


def write_bundle(root: Path, slug: str, cells: list[Cell]) -> Path:
    out = root / "processed" / slug / "v1"
    out.mkdir(parents=True)
    (out / "bundle_manifest.json").write_text(
        json.dumps({"dataset": {"slug": slug, "version": "v1"}, "bundle_checksum": f"sha-{slug}"}),
        encoding="utf-8",
    )
    conditions = []
    for c in cells:
        tc: dict[str, object] = {"dataset_flags": {"paper_excluded": "x"} if c.excluded else {}}
        if c.reported_cycle_life is not None:
            tc["cycle_life_source"] = str(c.reported_cycle_life)
        conditions.append(json.dumps(tc))
    pq.write_table(
        pa.table(
            {
                "external_id": [c.external_id for c in cells],
                "chemistry": [c.chemistry for c in cells],
                "soh_reference_capacity_ah": [c.rated_capacity_ah for c in cells],
                "test_conditions_json": conditions,
            }
        ),
        out / "batteries.parquet",
    )
    rows: dict[str, list[object]] = {
        k: [] for k in ("external_id", "cycle_index", "soh_pct", "quality_flags_json", *CHANNELS)
    }
    for c in cells:
        for i in range(len(c)):
            rows["external_id"].append(c.external_id)
            rows["cycle_index"].append(int(c.cycle[i]))
            rows["soh_pct"].append(float(c.soh[i]))
            rows["quality_flags_json"].append("{}")
            for ch in CHANNELS:
                v = c.channels[ch][i]
                rows[ch].append(None if np.isnan(v) else float(v))
        # A placeholder that is not a capacity measurement must be dropped by the loader.
        rows["external_id"].append(c.external_id)
        rows["cycle_index"].append(int(len(c)) + 5000)
        rows["soh_pct"].append(0.0)
        rows["quality_flags_json"].append(json.dumps({"capacity_zero": "placeholder"}))
        for ch in CHANNELS:
            rows[ch].append(None)
    schema = pa.schema(
        [
            ("external_id", pa.string()),
            ("cycle_index", pa.int32()),
            ("soh_pct", pa.float64()),
            ("quality_flags_json", pa.string()),
        ]
        + [(ch, pa.float64()) for ch in CHANNELS]
    )
    pq.write_table(pa.table(rows, schema=schema), out / "cycles.parquet")
    return out


def generated_cells(slug: str, count: int, seed: int, *, channels: bool = True) -> list[Cell]:
    rng = np.random.default_rng(seed)
    cells = []
    for i in range(count):
        life = int(rng.integers(150, 500))
        observed = life + 20 if i % 5 else int(life * 0.6)  # every 5th battery is censored
        cells.append(
            make_cell(
                life,
                observed,
                seed * 100 + i,
                dataset=slug,
                eid=f"{slug[:3]}{i}",
                channels=channels,
            )
        )
    return cells


@pytest.fixture(scope="session")
def bundles(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    root = tmp_path_factory.mktemp("data")
    return [
        write_bundle(root, "severson-2019", generated_cells("severson-2019", 30, 1)),
        write_bundle(root, "small-test", generated_cells("small-test", 8, 2, channels=False)),
    ]
