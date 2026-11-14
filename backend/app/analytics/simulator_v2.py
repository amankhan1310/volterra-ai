"""What-if simulator, version 2: anchored to the shared v2 forecast (fixes F4).

v1 gives two lifetimes for identical conditions: the Overview's linear RUL (112.7 cycles to 80%)
and the simulator baseline (106), because the simulator adds its own ``(1 + n/1500)``
acceleration term and starts from a rounded SOH (**F4**, ARCHITECTURE_PLAN.md §3.6).

v2 has one source of truth, the v2 forecast (:mod:`app.analytics.forecast_v2`):

* The **baseline** curve is the forecast's shape started at the scenario's initial SOH:
  ``SOH_b(t) = S + c1·t + c2·t²``. With ``S`` = the fitted SOH now, it *is* the Overview forecast,
  so the baseline cycles to EOL equal the Overview RUL (rounded).
* A **scenario** runs the same curve faster or slower by its stress factor ``k`` (the v1 assumed
  temperature, C-rate and DoD factors, which are 1 at 25 °C / 1C / 80% DoD):
  ``SOH_s(n) = SOH_b(n·k)``, so ``cycles_s = cycles_b / k``, i.e. baseline cycles ×
  (baseline fade / scenario fade).
* No separate acceleration term (the curvature comes from the forecast) and no rounding of the
  starting SOH.

The stress coefficients stay **assumed** (not fitted); fitting them is Phase 8. Inherits the
interim status of the v2 forecast (see :mod:`app.analytics.forecast_v2`).
"""

from __future__ import annotations

from collections.abc import Mapping

from app.analytics.forecast_v2 import TrendSummaryV2, first_crossing
from app.analytics.health import DEFAULT_EOL_PCT
from app.analytics.jsmath import js_round
from app.analytics.simulator import (
    BASELINE_C_RATE,
    BASELINE_DOD_PCT,
    BASELINE_TEMP_C,
    DEFAULT_HORIZON_CYCLES,
    EOL_SCAN_MAX_CYCLES,
    ScenarioComparison,
    ScenarioParams,
    degradation_rate,
)
from app.analytics.types import Provenance

SIMULATOR_VERSION_V2 = "v2"

#: No "acceleration" coefficient: the forecast's curvature replaces it.
COEFFICIENT_PROVENANCE_V2: Mapping[str, Provenance] = {
    "base_fade": "fitted",
    "temperature": "assumed",
    "c_rate": "assumed",
    "dod": "assumed",
}


def default_params_v2(trend: TrendSummaryV2, eol_pct: float = DEFAULT_EOL_PCT) -> ScenarioParams:
    """Baseline conditions from the fitted SOH now (not rounded, unlike v1)."""
    return ScenarioParams(
        temp_c=BASELINE_TEMP_C,
        c_rate=BASELINE_C_RATE,
        dod_pct=BASELINE_DOD_PCT,
        horizon_cycles=DEFAULT_HORIZON_CYCLES,
        start_soh_pct=trend.soh_now_pct,
        eol_pct=eol_pct,
    )


def stress_factor(p: ScenarioParams) -> float:
    """Scenario fade relative to the baseline fade (exactly 1 at baseline conditions)."""
    return degradation_rate(p, 1.0)


def degradation_rate_v2(p: ScenarioParams, trend: TrendSummaryV2) -> float:
    """Scenario fade rate now (% SOH / cycle): the forecast's current fade × the stress factor."""
    return trend.fade_pct_per_cycle * stress_factor(p)


def soh_at_v2(p: ScenarioParams, n: int, trend: TrendSummaryV2) -> float:
    """Simulated SOH after ``n`` cycles: the baseline curve evaluated at ``n·k``."""
    t = n * stress_factor(p)
    return p.start_soh_pct + trend.fit.c1 * t + trend.fit.c2 * t * t


def cycles_to_eol_v2(p: ScenarioParams, trend: TrendSummaryV2) -> int | None:
    """Rounded cycles until SOH <= EOL; ``None`` if never or beyond 5000 cycles."""
    baseline_cycles = first_crossing(p.start_soh_pct, trend.fit.c1, trend.fit.c2, p.eol_pct)
    if baseline_cycles is None:
        return None
    cycles = baseline_cycles / stress_factor(p)
    if cycles > EOL_SCAN_MAX_CYCLES:
        return None
    return int(js_round(cycles))


def trajectory_v2(p: ScenarioParams, trend: TrendSummaryV2) -> list[float]:
    """SOH for cycles ``0..horizon`` inclusive (unclamped, like v1; the chart clamps at 0)."""
    return [soh_at_v2(p, n, trend) for n in range(p.horizon_cycles + 1)]


def compare_to_baseline_v2(p: ScenarioParams, trend: TrendSummaryV2) -> ScenarioComparison:
    """Scenario vs the same start/EOL under baseline conditions.

    ``delta_pct`` is ``None`` when it cannot be computed (either count unknown, or the baseline
    is already at end of life), instead of v1's ``NaN``.
    """
    baseline = p.with_baseline_conditions()
    cs = cycles_to_eol_v2(p, trend)
    cb = cycles_to_eol_v2(baseline, trend)
    delta = cs - cb if cs is not None and cb is not None else None
    return ScenarioComparison(
        params=p,
        cycles_to_eol=cs,
        baseline_params=baseline,
        baseline_cycles_to_eol=cb,
        delta_cycles=delta,
        delta_pct=None if delta is None or not cb else delta / cb * 100,
        soh_after_horizon_pct=soh_at_v2(p, p.horizon_cycles, trend),
        baseline_soh_after_horizon_pct=soh_at_v2(baseline, p.horizon_cycles, trend),
    )
