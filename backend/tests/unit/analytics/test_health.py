"""Unit and property tests for SOH, RUL and forecast (v1)."""

from __future__ import annotations

import dataclasses
import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.analytics.health import (
    forecast_extent,
    forecast_series,
    life_used_fraction,
    recent_trend,
    rul_at,
    rul_interval_95,
)
from app.analytics.synthetic import CycleRecord, generate_synthetic_v1

RECORDS = generate_synthetic_v1()
TREND = recent_trend(RECORDS)


def line_records(n: int, slope: float, start: float = 100.0) -> tuple[CycleRecord, ...]:
    return tuple(CycleRecord(i, 0.0, start + slope * i, 25.0, 3.7) for i in range(n))


def test_trend_window_and_definitions() -> None:
    assert (TREND.fit_from_cycle, TREND.fit_to_cycle, TREND.n_cycles) == (200, 319, 320)
    assert TREND.soh_now_pct == TREND.fit.intercept + TREND.fit.slope * 319
    assert TREND.fade_pct_per_cycle == -TREND.fit.slope
    assert TREND.observed_last_soh_pct == RECORDS[-1].soh_pct
    assert TREND.provenance == "fitted"


@pytest.mark.parametrize("window", [2, 321])
def test_trend_rejects_invalid_windows(window: int) -> None:
    with pytest.raises(ValueError):
        recent_trend(RECORDS, window)


@given(st.floats(min_value=50, max_value=99), st.floats(min_value=50, max_value=99))
def test_rul_decreases_as_threshold_rises(e1: float, e2: float) -> None:
    lo, hi = sorted((e1, e2))
    r_lo, r_hi = rul_at(TREND, lo), rul_at(TREND, hi)
    assert r_lo is not None and r_hi is not None
    assert r_lo >= r_hi >= 0


def test_rul_is_zero_above_current_soh_and_none_without_decline() -> None:
    assert rul_at(TREND, 95) == 0
    assert rul_at(TREND, 80, slope=0.0) is None
    assert rul_at(TREND, 80, slope=0.01) is None
    assert rul_at(TREND, 80, slope=math.nan) is None
    flat = recent_trend(line_records(150, 0.0))
    assert rul_at(flat, 80) is None


def test_interval_brackets_point_estimate() -> None:
    for eol in (60, 70, 80, 85):
        iv = rul_interval_95(TREND, eol)
        point = rul_at(TREND, eol)
        assert iv.lower is not None and iv.upper is not None and point is not None
        assert iv.lower <= point <= iv.upper
    assert (iv.level, iv.method, iv.provenance) == (0.95, "slope_se", "predicted")


@pytest.mark.parametrize(
    ("rul", "expected"),
    [(None, 320 + 280), (0.0, 320 + 280), (math.nan, 320 + 280), (10.0, 334), (1000.0, 820)],
)
def test_forecast_extent_fallback_and_cap(rul: float | None, expected: int) -> None:
    assert forecast_extent(320, rul) == expected


def test_forecast_series_spans_last_cycle_to_extent() -> None:
    values = forecast_series(TREND, 330)
    assert len(values) == 330 - 319
    assert values[0] == TREND.fit.intercept + TREND.fit.slope * 319


@pytest.mark.parametrize(
    ("soh", "eol", "expected"), [(90.0, 80.0, 0.5), (70.0, 80.0, 1.0), (90.0, 100.0, 1.0)]
)
def test_life_used_fraction(soh: float, eol: float, expected: float) -> None:
    assert life_used_fraction(soh, eol) == expected


def test_frozen_results() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        TREND.soh_now_pct = 0.0  # type: ignore[misc]
