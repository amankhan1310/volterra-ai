"""Capacity/SOH figures on the real CALCE and NASA cells (local only; skipped without the data).

The bundles' per-cycle capacities equal the original workbooks / .mat files (checked value by
value in ml/tests/loaders/test_calce_realdata.py and test_nasa_realdata.py). Here every cell's
figures from app.analytics.capacity are recomputed independently (statistics.median, math.fsum,
closed-form least squares) from the cycles that the importer puts in the database
(measured capacity and SOH, at least one sample), and the SOH reference is checked against
the documented rated capacities.
"""

from __future__ import annotations

import json
import math
import os
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from app.analytics.capacity import (
    EDGE_WINDOW,
    EXCLUDED_FLAGS,
    MIN_TREND_CYCLES,
    CapacityPoint,
    capacity_degradation,
)

DATA_DIR = Path(os.environ.get("VOLTERRA_DATA_DIR", "__unset__"))
BUNDLES = {
    "calce-cs2-cx2": DATA_DIR / "processed" / "calce-cs2-cx2" / "2015-08-10",
    "nasa-pcoe-battery": DATA_DIR / "processed" / "nasa-pcoe-battery" / "2022-09-18",
}
#: Rated capacities in the source documentation (docs/datasets/*.md).
RATED = {"CS2": 1.10, "CX2": 1.35, "B0": 2.0}

pytestmark = [
    pytest.mark.realdata,
    pytest.mark.skipif(
        not all((p / "bundle_manifest.json").is_file() for p in BUNDLES.values()),
        reason="no CALCE/NASA bundles in $VOLTERRA_DATA_DIR/processed",
    ),
]


def imported(r: dict[str, Any]) -> bool:
    """The importer's rule: measured capacity and SOH and at least one sample."""
    return r["capacity_ah"] is not None and r["soh_pct"] is not None and r["n_samples"] > 0


def cells(slug: str) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    root = BUNDLES[slug]
    rows = defaultdict(list)
    for r in pq.read_table(root / "cycles.parquet").to_pylist():
        if imported(r):
            rows[r["external_id"]].append(r)
    bats = pq.read_table(root / "batteries.parquet").to_pylist()
    return [(b, sorted(rows[b["external_id"]], key=lambda r: r["cycle_index"])) for b in bats]


def oracle(caps: list[float], xs: list[int]) -> tuple[float, float, float, float]:
    initial = statistics.median(caps[:EDGE_WINDOW])
    final = statistics.median(caps[-EDGE_WINDOW:])
    n = len(xs)
    mx, my = math.fsum(xs) / n, math.fsum(caps) / n
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    slope = math.fsum((x - mx) * (y - my) for x, y in zip(xs, caps, strict=True)) / sxx
    return initial, final, slope, my - slope * mx


@pytest.mark.parametrize("slug", sorted(BUNDLES))
def test_every_cell_matches_an_independent_computation(slug: str) -> None:
    checked = cycles = 0
    rising: list[str] = []
    for battery, rows in cells(slug):
        ext = battery["external_id"]
        rated = next(v for prefix, v in RATED.items() if ext.startswith(prefix))
        # The SOH reference is the documented rated capacity, not the first measurement.
        assert battery["soh_reference"] == "rated_capacity"
        assert battery["soh_reference_capacity_ah"] == pytest.approx(rated)
        ref = battery["soh_reference_capacity_ah"]
        points = [
            CapacityPoint(
                r["cycle_index"], r["capacity_ah"], tuple(json.loads(r["quality_flags_json"]))
            )
            for r in rows
        ]
        view = capacity_degradation(
            points, reference="rated_capacity", reference_capacity_ah=ref, eol_pct=80.0
        )
        usable = [
            r for r in rows if not set(json.loads(r["quality_flags_json"])) & set(EXCLUDED_FLAGS)
        ]
        assert view.usable_cycles == len(usable)
        assert view.excluded_cycles == len(rows) - len(usable)
        caps = [r["capacity_ah"] for r in usable]
        assert all(c is not None for c in caps)  # nothing missing is filled in
        xs = [r["cycle_index"] for r in usable]
        initial, final, slope, intercept = oracle(caps, xs)
        assert view.initial_capacity_ah == pytest.approx(initial, rel=1e-12)
        assert view.final_capacity_ah == pytest.approx(final, rel=1e-12)
        assert view.retention_pct == pytest.approx(final / initial * 100, rel=1e-12)
        assert view.final_soh_pct == pytest.approx(final / rated * 100, rel=1e-12)
        # Same reference as the importer's stored per-cycle SOH.
        assert view.latest_soh_pct == pytest.approx(usable[-1]["soh_pct"], rel=1e-12)
        if len(usable) >= MIN_TREND_CYCLES and slope > 0:
            assert view.trend is None  # rising capacity: no degradation trend is reported
            rising.append(ext)
        elif len(usable) >= MIN_TREND_CYCLES:
            assert view.trend is not None
            assert view.trend.slope_ah_per_cycle == pytest.approx(slope, rel=1e-9, abs=1e-15)
            assert view.trend.end_capacity_ah == pytest.approx(intercept + slope * xs[-1], rel=1e-9)
        else:
            assert view.trend is None
        checked += 1
        cycles += len(rows)
    assert checked == {"calce-cs2-cx2": 12, "nasa-pcoe-battery": 34}[slug]
    assert cycles == {"calce-cs2-cx2": 15971, "nasa-pcoe-battery": 2769}[slug]  # as in the DB
    print(slug, "cells whose capacity rises (trend withheld):", rising)


def test_calce_cells_have_no_temperature_and_are_still_analysed() -> None:
    for _battery, rows in cells("calce-cs2-cx2"):
        assert all(r["temp_mean_c"] is None for r in rows)  # never invented
    battery, rows = next((b, r) for b, r in cells("calce-cs2-cx2") if b["external_id"] == "CS2_33")
    points = [
        CapacityPoint(
            r["cycle_index"], r["capacity_ah"], tuple(json.loads(r["quality_flags_json"]))
        )
        for r in rows
    ]
    view = capacity_degradation(
        points, reference="rated_capacity", reference_capacity_ah=1.1, eol_pct=80.0
    )
    assert view.trend is not None and view.trend.slope_ah_per_cycle < 0
    assert view.eol_cycle_observed is not None
