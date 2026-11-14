"""F3 (v2): a 90% prediction interval calibrated from repeated historical backtests.

Calibration uses this battery's own history only; it does not establish coverage across
batteries (that needs held-out cells, Phase 6-7). v1 expectations stay in tests/parity.
"""

from __future__ import annotations

import math

import pytest

from app.analytics.forecast_v2 import (
    INTERVAL_LABEL_V2,
    INTERVAL_METHOD_V2,
    MIN_ORIGINS_PER_HORIZON,
    ForecastErrors,
    empirical_quantile,
    held_out_coverage,
    recent_trend_v2,
    rolling_origin_errors,
    rul_interval_v2,
    rul_v2,
    run_backtest_v2,
)
from app.analytics.legacy_v1 import analyze

A = analyze()
TREND = recent_trend_v2(A.records)
ERRORS = rolling_origin_errors(A.records)
INTERVAL = rul_interval_v2(TREND, ERRORS, 80.0)


def test_rolling_origin_backtests_cover_every_past_origin() -> None:
    assert ERRORS.window == 120
    assert len(ERRORS.by_horizon[1]) == 200  # origins 119..318
    assert ERRORS.by_horizon[1][0][0] == 119
    assert ERRORS.calibrated_horizon() == 171  # last horizon with >= 30 backtests
    assert len(ERRORS.by_horizon[171]) == MIN_ORIGINS_PER_HORIZON


def test_interval_expected_values() -> None:
    assert (INTERVAL.lower, INTERVAL.upper) == (92.0, 101.0)
    assert INTERVAL.level == 0.90
    assert INTERVAL.method == INTERVAL_METHOD_V2
    assert INTERVAL.label == INTERVAL_LABEL_V2 == "90% prediction interval"
    point = rul_v2(TREND, 80.0)
    assert point is not None and INTERVAL.lower is not None and INTERVAL.upper is not None
    assert INTERVAL.lower <= point <= INTERVAL.upper


def test_f3_regression_interval_reflects_the_forecast_error() -> None:
    """F3 acceptance (as in test_known_defects.py, with the v2 forecast's own backtest error)."""
    bt = run_backtest_v2(A.records)
    assert INTERVAL.lower is not None and INTERVAL.upper is not None
    implied_cycles = bt.mae / TREND.fade_pct_per_cycle
    assert INTERVAL.upper - INTERVAL.lower >= 2 * implied_cycles
    # Much wider than v1's slope-only interval (2.6 cycles).
    assert v1_width() < 3 < INTERVAL.upper - INTERVAL.lower


def v1_width() -> float:
    lo, hi = A.rul_interval.lower, A.rul_interval.upper
    assert lo is not None and hi is not None
    return hi - lo


@pytest.mark.parametrize("split", [150, 170, 190])
def test_held_out_coverage_is_near_nominal(split: int) -> None:
    """Calibrate on earlier origins, score later ones: 85-95% for a 90% interval (plan §9.3)."""
    coverage, scored = held_out_coverage(ERRORS, split)
    assert scored > 5000
    assert 0.85 <= coverage <= 0.95


def test_interval_contains_the_noise_free_truth() -> None:
    truth = (-0.028 + math.sqrt(0.028**2 + 4 * 5e-5 * 20)) / (2 * 5e-5) - 319
    assert INTERVAL.lower is not None and INTERVAL.upper is not None
    assert INTERVAL.lower <= truth <= INTERVAL.upper


def test_bounds_beyond_the_calibrated_horizon_are_unknown() -> None:
    far = rul_interval_v2(TREND, ERRORS, 60.0)  # RUL ≈ 360 cycles, calibrated to 171
    assert (far.lower, far.upper) == (None, None)
    assert far.max_calibrated_horizon == 171


def test_already_at_end_of_life() -> None:
    at = rul_interval_v2(TREND, ERRORS, 90.0)
    assert (at.lower, at.upper) == (0.0, 0.0)


def test_empirical_quantile_uses_the_conformal_rank() -> None:
    values = [float(v) for v in range(1, 20)]  # m = 19
    assert empirical_quantile(values, 0.05) == 1.0  # ceil(0.05·20) = 1st
    assert empirical_quantile(values, 0.95) == 19.0  # ceil(0.95·20) = 19th
    assert empirical_quantile(values, 0.5) == 10.0
    with pytest.raises(ValueError, match="no values"):
        empirical_quantile([], 0.5)


def test_coverage_needs_later_backtests() -> None:
    with pytest.raises(ValueError, match="no backtests"):
        held_out_coverage(ERRORS, split_origin=10_000)
    assert ForecastErrors({}, 120).calibrated_horizon() == 0


def test_v1_interval_is_unchanged() -> None:
    assert (A.rul_interval.level, A.rul_interval.method) == (0.95, "slope_se")
    assert v1_width() < 3
