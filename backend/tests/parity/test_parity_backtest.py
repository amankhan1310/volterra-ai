"""Parity: the backtest matches ``backtest.json``."""

from __future__ import annotations

from app.analytics.backtest import run_backtest
from app.analytics.synthetic import generate_synthetic_v1
from tests.support.golden import assert_matches


def test_backtest_matches_golden(golden) -> None:
    expected = golden("backtest")
    r = run_backtest(generate_synthetic_v1())
    actual = {
        "train_cycles": {"from": r.train_from_cycle, "to_inclusive": r.train_to_cycle},
        "test_cycles": {"from": r.test_from_cycle, "to_inclusive": r.test_to_cycle},
        "fit": {
            "slope": r.fit.slope,
            "intercept": r.fit.intercept,
            "residual_sd": r.fit.residual_sd,
            "slope_se": r.fit.slope_se,
        },
        "columns": ["cycle", "observed_soh_pct", "predicted_soh_pct", "abs_error"],
        "per_cycle": [
            [p.cycle, p.observed_soh_pct, p.predicted_soh_pct, p.abs_error] for p in r.points
        ],
        "mae": r.mae,
    }
    assert_matches(actual, {k: v for k, v in expected.items() if k != "meta"}, label="backtest")
