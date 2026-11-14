"""F4 (v2): the simulator baseline is the shared v2 forecast, so it agrees with the Overview.

v1 expectations (106 vs 112.7) stay in tests/parity and the strict-xfail F4 test.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.analytics.forecast_v2 import recent_trend_v2, rul_v2
from app.analytics.jsmath import js_round
from app.analytics.legacy_v1 import analyze
from app.analytics.simulator import ScenarioParams
from app.analytics.simulator_v2 import (
    COEFFICIENT_PROVENANCE_V2,
    compare_to_baseline_v2,
    cycles_to_eol_v2,
    default_params_v2,
    degradation_rate_v2,
    soh_at_v2,
    stress_factor,
    trajectory_v2,
)

A = analyze()
TREND = recent_trend_v2(A.records)
DEFAULTS = default_params_v2(TREND)


def scenario(**changes: float) -> ScenarioParams:
    return dataclasses.replace(DEFAULTS, **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize("eol", [80.0, 75.0, 85.0])
def test_f4_regression_baseline_agrees_with_overview_rul(eol: float) -> None:
    """F4 acceptance (as in test_known_defects.py, for v2): baseline == round(Overview RUL)."""
    rul = rul_v2(TREND, eol)
    assert rul is not None
    baseline = compare_to_baseline_v2(scenario(eol_pct=eol), TREND)
    assert baseline.baseline_cycles_to_eol == js_round(rul)


def test_defaults_start_from_the_unrounded_fitted_soh() -> None:
    assert DEFAULTS.start_soh_pct == TREND.soh_now_pct  # v1 rounds to 86.1
    assert (DEFAULTS.temp_c, DEFAULTS.c_rate, DEFAULTS.dod_pct) == (25.0, 1.0, 80.0)


def test_baseline_curve_is_the_overview_forecast() -> None:
    for n in (0, 50, 96, 300):
        assert soh_at_v2(DEFAULTS, n, TREND) == pytest.approx(TREND.fit.ahead(n), abs=1e-12)


@pytest.mark.parametrize(
    ("change", "cycles", "delta_pct"),
    [
        ({"temp_c": 35.0}, 53, -45.36082474226804),
        ({"temp_c": 15.0}, 176, 81.44329896907216),
        ({"c_rate": 2.0}, 69, -28.865979381443296),
        ({"dod_pct": 100.0}, 79, -18.556701030927837),
    ],
)
def test_scenario_expected_values(change, cycles, delta_pct) -> None:
    result = compare_to_baseline_v2(scenario(**change), TREND)
    assert result.baseline_cycles_to_eol == 97
    assert result.cycles_to_eol == cycles
    assert result.delta_pct == pytest.approx(delta_pct, rel=1e-12)


def test_scenario_cycles_are_baseline_times_the_fade_ratio() -> None:
    hot = scenario(temp_c=35.0)
    base_cycles = rul_v2(TREND, 80.0)
    assert base_cycles is not None
    ratio = degradation_rate_v2(DEFAULTS, TREND) / degradation_rate_v2(hot, TREND)
    assert cycles_to_eol_v2(hot, TREND) == js_round(base_cycles * ratio)


def test_stress_factor_is_one_at_baseline_conditions() -> None:
    assert stress_factor(DEFAULTS) == 1.0
    assert degradation_rate_v2(DEFAULTS, TREND) == TREND.fade_pct_per_cycle


def test_no_separate_acceleration_term() -> None:
    assert "acceleration" not in COEFFICIENT_PROVENANCE_V2
    assert COEFFICIENT_PROVENANCE_V2["base_fade"] == "fitted"


def test_beyond_the_scan_horizon_is_unknown() -> None:
    gentle = scenario(temp_c=5.0, c_rate=0.5, dod_pct=20.0, eol_pct=60.0)
    result = compare_to_baseline_v2(gentle, TREND)
    assert result.cycles_to_eol is None
    assert result.baseline_cycles_to_eol == 360
    assert result.delta_pct is None


def test_never_reaching_eol_is_unknown() -> None:
    rising = dataclasses.replace(TREND, fit=dataclasses.replace(TREND.fit, c1=0.01, c2=0.0))
    assert cycles_to_eol_v2(DEFAULTS, rising) is None


def test_already_at_end_of_life_has_no_percentage() -> None:
    result = compare_to_baseline_v2(scenario(start_soh_pct=80.0), TREND)
    assert (result.cycles_to_eol, result.baseline_cycles_to_eol) == (0, 0)
    assert result.delta_cycles == 0
    assert result.delta_pct is None  # v1 reports NaN here


def test_trajectory_covers_the_horizon() -> None:
    traj = trajectory_v2(scenario(horizon_cycles=100), TREND)
    assert len(traj) == 101
    assert traj[0] == DEFAULTS.start_soh_pct


def test_v1_simulator_is_unchanged() -> None:
    assert A.simulator_baseline.cycles_to_eol == 106
    assert A.simulator_defaults.start_soh_pct == 86.1
