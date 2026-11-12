"""Scenario simulation and Charging Advisor: calls the v1 simulator functions unchanged."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from app.analytics.advisor import AdvisorTable, sensitivity_table
from app.analytics.simulator import (
    ScenarioComparison,
    ScenarioParams,
    compare_to_baseline,
    degradation_rate,
    trajectory,
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
