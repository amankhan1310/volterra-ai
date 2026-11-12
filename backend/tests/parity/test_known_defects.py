"""Known prototype defects F1–F8 as executable specifications (ARCHITECTURE_PLAN.md §3.6).

Each test asserts the **correct** behaviour and is marked ``xfail(strict=True)`` because v1
reproduces the prototype's defect on purpose. Strictness means an accidental change to v1 that
"fixes" a defect fails the suite (XPASS). The fixes arrive in Phase 5 as separate v2
implementations with their own expected-value tests; v1 and these markers stay unchanged.
"""

from __future__ import annotations

import pytest

from app.analytics.advisor import sensitivity_table
from app.analytics.anomalies import capacity_residuals_v1, detect_anomalies_v1
from app.analytics.backtest import run_backtest
from app.analytics.health import recent_trend
from app.analytics.insights import generate_insights_v1
from app.analytics.jsmath import js_round, sum_from_zero
from app.analytics.legacy_v1 import analyze
from app.analytics.simulator import ScenarioParams
from app.analytics.synthetic import SYNTHETIC_V1, CycleRecord

A = analyze()


def defect(code: str, summary: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(
        strict=True, reason=f"{code} (v1 reproduces it; fixed by v2): {summary}"
    )


@defect("F1", "temperature detector misses injected spikes")
def test_f1_all_injected_temperature_spikes_are_detected() -> None:
    assert A.anomalies.detected_cycles("temp") == list(SYNTHETIC_V1.temp_spike_cycles)


@defect("F2", "capacity-step detector raises false positives")
def test_f2_no_capacity_steps_flagged_when_none_injected() -> None:
    assert A.anomalies.detected_cycles("soh") == []


@defect("F3", "RUL interval reflects slope standard error only")
def test_f3_rul_interval_is_at_least_as_wide_as_backtest_error() -> None:
    lower, upper = A.rul_interval.lower, A.rul_interval.upper
    assert lower is not None and upper is not None
    implied_cycles = A.backtest.mae / A.trend.fade_pct_per_cycle
    assert upper - lower >= 2 * implied_cycles


@defect("F4", "simulator baseline disagrees with the Overview RUL")
def test_f4_simulator_baseline_agrees_with_overview_rul() -> None:
    assert A.rul_cycles is not None
    assert A.simulator_baseline.cycles_to_eol == js_round(A.rul_cycles)


@defect("F5", "insight #2 always says 'accelerating'")
def test_f5_insight_does_not_claim_acceleration_when_fade_slows() -> None:
    slowing = tuple(
        CycleRecord(i, 0.0, 100 - 0.08 * i if i < 160 else 87.2 - 0.02 * (i - 160), 25.0, 3.7)
        for i in range(320)
    )
    trend = recent_trend(slowing)
    text = generate_insights_v1(
        slowing, trend, detect_anomalies_v1(slowing), run_backtest(slowing)
    )[1].text
    assert "accelerating" not in text


@defect("F6", "linear model is biased on accelerating fade")
def test_f6_backtest_forecast_is_unbiased() -> None:
    signed = [p.predicted_soh_pct - p.observed_soh_pct for p in A.backtest.points]
    assert abs(sum_from_zero(signed) / len(signed)) < 0.1


@defect("F7", "capacity residual uses future cycles")
def test_f7_capacity_residual_is_causal() -> None:
    soh = [r.soh_pct for r in A.records]
    changed_future = soh[:101] + [v + 5.0 for v in soh[101:]]
    assert capacity_residuals_v1(changed_future)[100] == capacity_residuals_v1(soh)[100]


@defect("F8", "advisor reports 0% instead of 'not applicable'")
def test_f8_advisor_delta_is_undefined_without_a_baseline() -> None:
    below_eol = ScenarioParams.from_legacy({**A.simulator_defaults.to_legacy(), "S": 70})
    table = sensitivity_table(below_eol, A.trend.fade_pct_per_cycle)
    assert table.baseline_cycles_to_eol == 0
    assert all(row.delta_pct is None for row in table.rows)
