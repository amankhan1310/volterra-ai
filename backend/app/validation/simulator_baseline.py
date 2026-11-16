"""Phase 8: validate the simulator's baseline (and the Overview RUL) on real cells, offline.

``uv run python -m app.validation.simulator_baseline --data-dir <dir> --out <file.json>``

The What-If Simulator's baseline is the battery's own fitted trend: v1 extrapolates a straight
line plus the prototype's acceleration term; v2 the quadratic forecast that also gives the Overview
RUL (F4 fix). This tool runs the backend's *own* analytics code (``app.analytics``), unchanged, on
real Severson cells truncated at 30/50/70/90 % of their documented cycle life, and compares each
method's cycles-to-EOL with the cycles the cell actually had left. No fitting or tuning happens
here; it only measures how the existing methods behave on measured data.

Severson only: NASA cells are shorter than the 120-cycle trend window and CALCE has no
temperature, which the cycle records require. Aggregate numbers only are written.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from app.analytics.forecast_v2 import recent_trend_v2, rul_v2
from app.analytics.health import RECENT_WINDOW_CYCLES, recent_trend, rul_at
from app.analytics.simulator import cycles_to_eol, default_params
from app.analytics.synthetic import CycleRecord

SCHEMA = 1
EOL_PCT = 80.0
FRACTIONS = (0.3, 0.5, 0.7, 0.9)
SEVERSON = Path("processed") / "severson-2019" / "2019-03-11"
NOT_MEASUREMENTS = {"capacity_missing", "capacity_negative", "capacity_zero", "empty_samples"}
METHODS = {
    "v1_overview_linear": "v1 Overview RUL: straight line over the last 120 cycles",
    "v1_simulator_baseline": "v1 simulator baseline: linear fade plus the (1 + n/1500) term",
    "v2_quadratic": "v2 Overview RUL = v2 simulator baseline: quadratic over the last 120 cycles",
}


def load_cells(bundle: Path) -> list[tuple[str, float, list[CycleRecord]]]:
    """(battery, documented cycle life, records re-indexed 0..n-1) for usable Severson cells."""
    lives: dict[str, float] = {}
    for b in pq.read_table(bundle / "batteries.parquet").to_pylist():
        tc = json.loads(b["test_conditions_json"])
        flags = tc.get("dataset_flags") or {}
        flags = json.loads(flags) if isinstance(flags, str) else flags
        life = tc.get("cycle_life_source_joined") or tc.get("cycle_life_source")
        if "paper_excluded" not in flags and life is not None:
            lives[b["external_id"]] = float(life)
    columns = ["external_id", "cycle_index", "capacity_ah", "soh_pct", "temp_mean_c",
               "voltage_mean_v", "quality_flags_json"]  # fmt: skip
    rows: dict[str, list[dict[str, Any]]] = {}
    for r in pq.read_table(bundle / "cycles.parquet", columns=columns).to_pylist():
        usable = r["external_id"] in lives and r["soh_pct"] is not None
        if usable and not set(json.loads(r["quality_flags_json"])) & NOT_MEASUREMENTS:
            rows.setdefault(r["external_id"], []).append(r)
    out = []
    for eid, rs in sorted(rows.items()):
        rs.sort(key=lambda r: r["cycle_index"])
        records = [
            CycleRecord(i, r["capacity_ah"], r["soh_pct"], r["temp_mean_c"], r["voltage_mean_v"])
            for i, r in enumerate(rs)
        ]
        out.append((eid, lives[eid], records))
    return out


def estimates(records: Sequence[CycleRecord]) -> dict[str, float | None]:
    t1 = recent_trend(records)
    sim = cycles_to_eol(default_params(t1.soh_now_pct), t1.fade_pct_per_cycle)
    return {
        "v1_overview_linear": rul_at(t1, EOL_PCT),
        "v1_simulator_baseline": None if sim is None else float(sim),
        "v2_quadratic": rul_v2(recent_trend_v2(records), EOL_PCT),
    }


def summarise(errors: list[tuple[float, float]], none: int) -> dict[str, Any]:
    """errors: (estimate, actual) pairs."""
    if not errors:
        return {"n": 0, "no_estimate": none}
    abs_err = [abs(e - a) for e, a in errors]
    rel = [abs(e - a) / a for e, a in errors if a > 0]
    return {
        "n": len(errors),
        "no_estimate": none,
        "mae_cycles": statistics.fmean(abs_err),
        "median_abs_error_cycles": statistics.median(abs_err),
        "bias_cycles": statistics.fmean(e - a for e, a in errors),
        "within_20_pct": statistics.fmean(1.0 if r <= 0.2 else 0.0 for r in rel) if rel else None,
    }


def validate(data_dir: Path) -> dict[str, Any]:
    bundle = data_dir / SEVERSON
    manifest = json.loads((bundle / "bundle_manifest.json").read_text(encoding="utf-8"))
    cells = load_cells(bundle)
    pairs: dict[str, dict[float, list[tuple[float, float]]]] = {m: {} for m in METHODS}
    missing: dict[str, dict[float, int]] = {m: {} for m in METHODS}
    used = 0
    for _eid, life, records in cells:
        eol_index = min(int(life) - 1, len(records) - 1)
        any_point = False
        for f in FRACTIONS:
            k = int(f * eol_index)
            if k + 1 < RECENT_WINDOW_CYCLES:
                continue
            any_point = True
            actual = float(eol_index - k)
            for method, est in estimates(records[: k + 1]).items():
                if est is None:
                    missing[method][f] = missing[method].get(f, 0) + 1
                else:
                    pairs[method].setdefault(f, []).append((est, actual))
        used += any_point
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": manifest["dataset"]["slug"],
        "bundle_checksum": manifest["bundle_checksum"],
        "eol_pct": EOL_PCT,
        "eol_label": "documented cycle life (joined for continued cells); index = life - 1",
        "cells": used,
        "cells_skipped_short": len(cells) - used,
        "methods": METHODS,
        "results": {
            m: {f"{f:.1f}": summarise(pairs[m].get(f, []), missing[m].get(f, 0)) for f in FRACTIONS}
            for m in METHODS
        },
        "note": "No estimate: the trend does not reach EOL (flat or rising) within the method's "
        "horizon. Errors are in cycles of remaining life.",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.validation.simulator_baseline")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = validate(args.data_dir)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for method, by_f in result["results"].items():
        print(
            method,
            {f: (round(v.get("mae_cycles", 0)), v["n"], v["no_estimate"]) for f, v in by_f.items()},
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
