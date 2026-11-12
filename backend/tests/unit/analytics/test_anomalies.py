"""Unit and property tests for the v1 robust z-score detector."""

from __future__ import annotations

import math

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from app.analytics.anomalies import (
    CHANNELS,
    MAD_FLOOR,
    capacity_residuals_v1,
    detect_anomalies_v1,
    robust_z_channel,
    severity_for,
)
from app.analytics.stats import median
from app.analytics.synthetic import CycleRecord, generate_synthetic_v1

TEMP = CHANNELS[0]
values_strategy = st.lists(
    st.floats(min_value=-1e3, max_value=1e3, allow_nan=False), min_size=5, max_size=60
)


@pytest.mark.parametrize(
    ("z", "expected"),
    [(0.0, None), (3.5, None), (-3.5, None), (3.5000001, "medium"), (-4.0, "medium")]
    + [(6.0, "medium"), (6.0000001, "high"), (-7.0, "high"), (math.nan, None)],
)
def test_severity_boundaries(z: float, expected: str | None) -> None:
    assert severity_for(z) == expected


def test_mad_floor_when_most_values_are_identical() -> None:
    values = [5.0] * 9 + [6.0]
    stats, events = robust_z_channel(TEMP, values, list(range(10)))
    assert stats.mad == MAD_FLOOR
    assert [e.cycle for e in events] == [9]
    assert events[0].severity == "high"


@given(values_strategy, st.floats(min_value=-100, max_value=100))
def test_z_scores_are_shift_invariant(values: list[float], shift: float) -> None:
    base, _ = robust_z_channel(TEMP, values, list(range(len(values))))
    assume(base.mad > 1e-3)
    moved, _ = robust_z_channel(TEMP, [v + shift for v in values], list(range(len(values))))
    for a, b in zip(base.z, moved.z, strict=True):
        assert math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)


@given(values_strategy, st.floats(min_value=0.01, max_value=100))
def test_z_scores_are_scale_invariant(values: list[float], factor: float) -> None:
    base, _ = robust_z_channel(TEMP, values, list(range(len(values))))
    assume(base.mad > 1e-3)
    scaled, _ = robust_z_channel(TEMP, [v * factor for v in values], list(range(len(values))))
    for a, b in zip(base.z, scaled.z, strict=True):
        assert math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)


def test_capacity_residual_windows_are_centred_and_truncated() -> None:
    soh = [float(i * i % 7) for i in range(20)]
    res = capacity_residuals_v1(soh)
    assert res[0] == soh[0] - median(soh[0:8])
    assert res[10] == soh[10] - median(soh[3:18])
    assert res[19] == soh[19] - median(soh[12:20])


def test_events_are_sorted_by_cycle_with_stable_channel_order() -> None:
    records = tuple(
        CycleRecord(i, 2.0, 100.0, 50.0 if i == 4 else 25.0, 1.0 if i == 4 else 3.7)
        for i in range(30)
    )
    report = detect_anomalies_v1(records)
    at_four = [e.channel for e in report.events if e.cycle == 4]
    assert at_four[:2] == ["temp", "volt"]
    assert [e.cycle for e in report.events] == sorted(e.cycle for e in report.events)


def test_report_helpers_on_synthetic_v1() -> None:
    report = detect_anomalies_v1(generate_synthetic_v1())
    assert (report.detector, report.version, report.mode) == ("robust_z", "v1", "retrospective")
    assert report.count() == 8
    assert report.count("high") == 2
    assert report.detected_cycles("volt") == [130, 271]
    assert report.provenance == "fitted"
