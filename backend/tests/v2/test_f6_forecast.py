"""F6 (v2): the interim quadratic forecast removes the straight-line bias.

v1 expectations live in ``tests/parity`` and the strict-xfail ``test_known_defects.py``; this
file holds only v2 expected values.
"""

from __future__ import annotations

import math

import pytest

from app.analytics.backtest import run_backtest
from app.analytics.forecast_v2 import (
    FORECAST_MODEL_V2,
    first_crossing,
    forecast_series_v2,
    quad_fit,
    recent_trend_v2,
    rul_v2,
    run_backtest_v2,
)
from app.analytics.jsmath import sum_from_zero
from app.analytics.legacy_v1 import analyze

A = analyze()
TREND = recent_trend_v2(A.records)


def test_quad_fit_recovers_an_exact_quadratic() -> None:
    xs = list(range(200, 320))
    ys = [90 - 0.03 * (x - 319) - 2e-5 * (x - 319) ** 2 for x in xs]
    fit = quad_fit(xs, ys, origin=319)
    assert fit.c0 == pytest.approx(90, abs=1e-9)
    assert fit.c1 == pytest.approx(-0.03, abs=1e-12)
    assert fit.c2 == pytest.approx(-2e-5, abs=1e-14)
    assert fit.residual_sd == pytest.approx(0, abs=1e-9)
    assert fit.predict(250) == pytest.approx(ys[50], abs=1e-9)


def test_quad_fit_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="same length"):
        quad_fit([1, 2, 3, 4], [1, 2, 3], origin=4)
    with pytest.raises(ValueError, match="at least 4"):
        quad_fit([1, 2, 3], [1, 2, 3], origin=3)
    with pytest.raises(ValueError, match="singular"):
        quad_fit([5, 5, 5, 5], [1, 2, 3, 4], origin=5)


@pytest.mark.parametrize(
    ("start", "c1", "c2", "level", "expected"),
    [
        (79.0, -0.05, 0.0, 80.0, 0.0),  # already at or below the threshold
        (90.0, -0.05, 0.0, 80.0, 200.0),  # straight line
        (90.0, 0.01, 0.0, 80.0, None),  # rising line never reaches it
        (90.0, -0.05, -1e-4, 80.0, (0.05 - math.sqrt(0.0025 + 4e-3)) / -2e-4),  # bends down
        (90.0, 0.02, 1e-4, 80.0, None),  # opens upward, never dips to the level
        (90.0, -0.5, 1e-3, 80.0, (0.5 - math.sqrt(0.25 - 0.04)) / 2e-3),  # dips: first root
    ],
)
def test_first_crossing(start, c1, c2, level, expected) -> None:
    got = first_crossing(start, c1, c2, level)
    assert got == (None if expected is None else pytest.approx(expected, rel=1e-12))


def test_trend_and_rul_expected_values() -> None:
    assert (TREND.fit_from_cycle, TREND.fit_to_cycle) == (200, 319)  # same window as v1
    assert TREND.model == FORECAST_MODEL_V2
    assert TREND.soh_now_pct == pytest.approx(86.00097581847331, abs=1e-9)
    assert TREND.fade_pct_per_cycle == pytest.approx(0.05851481682579258, abs=1e-12)
    assert TREND.fit.c2 < 0  # fade accelerates
    assert rul_v2(TREND, 80.0) == pytest.approx(96.53608427644004, abs=1e-6)
    assert rul_v2(TREND, 70.0) == pytest.approx(237.13435529373166, abs=1e-6)


def test_v2_rul_is_closer_to_the_generator_truth_than_v1() -> None:
    # synthetic-v1: SOH = 100 - 0.028·i - 5e-5·i² (noise-free) reaches 80% at i ≈ 411.7.
    truth = (-0.028 + math.sqrt(0.028**2 + 4 * 5e-5 * 20)) / (2 * 5e-5) - 319
    v1 = A.rul_cycles
    v2 = rul_v2(TREND, 80.0)
    assert v1 is not None and v2 is not None
    assert abs(v2 - truth) < abs(v1 - truth)


def test_forecast_series_starts_at_the_fitted_soh_now() -> None:
    series = forecast_series_v2(TREND, 330)
    assert len(series) == 330 - 319
    assert series[0] == pytest.approx(TREND.soh_now_pct, abs=1e-12)
    assert all(b < a for a, b in zip(series, series[1:], strict=False))


def test_f6_regression_v2_backtest_is_unbiased() -> None:
    """F6 acceptance (as in test_known_defects.py, for v2): |mean signed error| < 0.1."""
    bt = run_backtest_v2(A.records)
    assert (bt.train_from_cycle, bt.train_to_cycle, bt.test_from_cycle) == (100, 219, 220)
    assert abs(bt.mean_signed_error) < 0.1
    assert bt.mean_signed_error == pytest.approx(0.04177346273644403, abs=1e-9)
    assert bt.mae == pytest.approx(0.09806773982568799, abs=1e-9)


def test_v1_backtest_is_unchanged_and_still_biased() -> None:
    v1 = run_backtest(A.records)
    signed = [p.predicted_soh_pct - p.observed_soh_pct for p in v1.points]
    assert sum_from_zero(signed) / len(signed) > 0.5  # the v1 defect, kept on purpose


def test_backtest_v2_rejects_bad_windows() -> None:
    with pytest.raises(ValueError, match="train_from"):
        run_backtest_v2(A.records, train_from=220, test_from=100)


def test_trend_v2_rejects_bad_windows() -> None:
    with pytest.raises(ValueError, match="window"):
        recent_trend_v2(A.records, window=3)
