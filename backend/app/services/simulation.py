"""Scenario simulation and Charging Advisor: calls the v1 (or opt-in v2) simulator unchanged."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from app.analytics.advisor import AdvisorTable, sensitivity_table
from app.analytics.advisor_v2 import AdvisorTableV2, sensitivity_table_v2
from app.analytics.forecast_v2 import TrendSummaryV2
from app.analytics.simulator import (
    ScenarioComparison,
    ScenarioParams,
    compare_to_baseline,
    degradation_rate,
    trajectory,
)
from app.analytics.simulator_v2 import (
    compare_to_baseline_v2,
    degradation_rate_v2,
    trajectory_v2,
)


@dataclass(frozen=True)
class SimulationResult:
    comparison: ScenarioComparison
    rate_pct_per_cycle: float
    trajectory_cycles: list[int] | None
    trajectory: list[float] | None
    baseline_trajectory: list[float] | None


def simulate(
    params: ScenarioParams, base_fade: float, include_trajectories: bool
) -> SimulationResult:
    comparison = compare_to_baseline(params, base_fade)
    if not include_trajectories:
        return SimulationResult(comparison, degradation_rate(params, base_fade), None, None, None)
    return SimulationResult(
        comparison=comparison,
        rate_pct_per_cycle=degradation_rate(params, base_fade),
        trajectory_cycles=list(range(params.horizon_cycles + 1)),
        trajectory=trajectory(params, base_fade),
        baseline_trajectory=trajectory(comparison.baseline_params, base_fade),
    )


def advisor_table(
    defaults: ScenarioParams, base_fade: float, start_soh_pct: float | None
) -> AdvisorTable:
    """The advisor table for the simulator defaults, optionally from another starting SOH."""
    params = (
        defaults
        if start_soh_pct is None
        else dataclasses.replace(defaults, start_soh_pct=start_soh_pct)
    )
    return sensitivity_table(params, base_fade)


def simulate_v2(
    params: ScenarioParams, trend: TrendSummaryV2, include_trajectories: bool
) -> SimulationResult:
    """v2 simulation, anchored to the shared v2 forecast (F4)."""
    comparison = compare_to_baseline_v2(params, trend)
    rate = degradation_rate_v2(params, trend)
    if not include_trajectories:
        return SimulationResult(comparison, rate, None, None, None)
    return SimulationResult(
        comparison=comparison,
        rate_pct_per_cycle=rate,
        trajectory_cycles=list(range(params.horizon_cycles + 1)),
        trajectory=trajectory_v2(params, trend),
        baseline_trajectory=trajectory_v2(comparison.baseline_params, trend),
    )


def advisor_table_v2(
    defaults: ScenarioParams, trend: TrendSummaryV2, start_soh_pct: float | None
) -> AdvisorTableV2:
    """The v2 advisor table (F8) for the v2 defaults, optionally from another starting SOH."""
    params = (
        defaults
        if start_soh_pct is None
        else dataclasses.replace(defaults, start_soh_pct=start_soh_pct)
    )
    return sensitivity_table_v2(params, trend)
