"""Semi-empirical what-if degradation simulator, version 1.

Ported from ``legacy/core.js:104-116`` (model) and ``legacy/ui.js:467-547`` (comparison)::

    rate  = fade * Math.exp(0.06 * (T - 25)) * (1 + 0.4 * (C - 1)) * Math.pow(D / 80, 0.9)
    sohAt = (p, n) => p.S - rate(p) * n * (1 + n / 1500)
    eolN  = (p) => first n in 0..5000 with sohAt(p, n) <= p.E, else null
    P     = { T: 25, C: 1, D: 80, N: 600, S: Math.round(sohNow * 10) / 10, E: 80 }

Only the base fade rate is fitted; the temperature, C-rate, depth-of-discharge and acceleration
coefficients are **assumed** (not fitted to data). Known defect reproduced on purpose: **F4**,
the baseline cycles-to-EOL disagrees with the Overview's linear RUL for identical conditions.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from app.analytics.health import DEFAULT_EOL_PCT
from app.analytics.jsmath import js_div, js_round
from app.analytics.types import Provenance

SIMULATOR_VERSION = "v1"

TEMP_EXP_PER_C = 0.06
C_RATE_LINEAR = 0.4
DOD_EXPONENT = 0.9
ACCELERATION_CYCLES = 1500
EOL_SCAN_MAX_CYCLES = 5000

BASELINE_TEMP_C = 25.0
BASELINE_C_RATE = 1.0
BASELINE_DOD_PCT = 80.0
DEFAULT_HORIZON_CYCLES = 600

COEFFICIENT_PROVENANCE: Mapping[str, Provenance] = {
    "base_fade": "fitted",
    "temperature": "assumed",
    "c_rate": "assumed",
    "dod": "assumed",
    "acceleration": "assumed",
}

#: Prototype parameter keys (used by the UI and the golden fixtures).
LEGACY_KEYS = {
    "T": "temp_c",
    "C": "c_rate",
    "D": "dod_pct",
    "N": "horizon_cycles",
    "S": "start_soh_pct",
    "E": "eol_pct",
}


@dataclass(frozen=True)
class ScenarioParams:
    temp_c: float
    c_rate: float
    dod_pct: float
    horizon_cycles: int
    start_soh_pct: float
    eol_pct: float

    @classmethod
    def from_legacy(cls, values: Mapping[str, float]) -> ScenarioParams:
        """Build from prototype keys ``T, C, D, N, S, E``."""
        kwargs = {LEGACY_KEYS[k]: v for k, v in values.items()}
        kwargs["horizon_cycles"] = int(kwargs["horizon_cycles"])
        return cls(**kwargs)  # type: ignore[arg-type]

    def to_legacy(self) -> dict[str, float]:
        return {k: getattr(self, attr) for k, attr in LEGACY_KEYS.items()}

    def with_baseline_conditions(self) -> ScenarioParams:
        """``{ ...p, ...BASE }``: 25 °C, 1C, 80% DoD, keeping S, E and N."""
        return dataclasses.replace(
            self, temp_c=BASELINE_TEMP_C, c_rate=BASELINE_C_RATE, dod_pct=BASELINE_DOD_PCT
        )


@dataclass(frozen=True)
class SliderSpec:
    key: str
    label: str
    min: float
    max: float
    step: float
    unit: str


#: Scenario controls and their ranges (``legacy/core.js:402-409``).
SLIDERS: tuple[SliderSpec, ...] = (
    SliderSpec("T", "Temperature", 5, 45, 1, "°C"),
    SliderSpec("C", "Charge rate", 0.5, 3, 0.1, "C"),
    SliderSpec("D", "Depth of discharge", 20, 100, 5, "%"),
    SliderSpec("N", "Cycles to simulate", 100, 1500, 50, ""),
    SliderSpec("S", "Initial SOH", 70, 100, 0.5, "%"),
    SliderSpec("E", "End-of-life SOH", 60, 90, 1, "%"),
)


@dataclass(frozen=True)
class ScenarioComparison:
    params: ScenarioParams
    cycles_to_eol: int | None
    baseline_params: ScenarioParams
    baseline_cycles_to_eol: int | None
    delta_cycles: int | None
    delta_pct: float | None
    soh_after_horizon_pct: float
    baseline_soh_after_horizon_pct: float

    provenance: ClassVar[Provenance] = "simulated"


def default_params(soh_now_pct: float) -> ScenarioParams:
    """The simulator's initial controls: baseline conditions from the rounded current SOH."""
    return ScenarioParams(
        temp_c=BASELINE_TEMP_C,
        c_rate=BASELINE_C_RATE,
        dod_pct=BASELINE_DOD_PCT,
        horizon_cycles=DEFAULT_HORIZON_CYCLES,
        start_soh_pct=js_round(soh_now_pct * 10) / 10,
        eol_pct=DEFAULT_EOL_PCT,
    )


def degradation_rate(p: ScenarioParams, base_fade: float) -> float:
    """SOH loss per cycle (% / cycle) under the scenario's stress factors."""
    return (
        base_fade
        * math.exp(TEMP_EXP_PER_C * (p.temp_c - 25))
        * (1 + C_RATE_LINEAR * (p.c_rate - 1))
        * math.pow(p.dod_pct / 80, DOD_EXPONENT)
    )


def soh_at(p: ScenarioParams, n: int, base_fade: float) -> float:
    """Simulated SOH after ``n`` cycles (unclamped; the chart clamps at 0)."""
    return p.start_soh_pct - degradation_rate(p, base_fade) * n * (1 + n / ACCELERATION_CYCLES)


def cycles_to_eol(p: ScenarioParams, base_fade: float) -> int | None:
    """First cycle in ``0..5000`` at which SOH <= EOL, or ``None`` beyond the scan horizon."""
    for n in range(EOL_SCAN_MAX_CYCLES + 1):
        if soh_at(p, n, base_fade) <= p.eol_pct:
            return n
    return None


def trajectory(p: ScenarioParams, base_fade: float) -> list[float]:
    """SOH for cycles ``0..horizon`` inclusive."""
    return [soh_at(p, n, base_fade) for n in range(p.horizon_cycles + 1)]


def compare_to_baseline(p: ScenarioParams, base_fade: float) -> ScenarioComparison:
    """Scenario vs the same start/EOL under baseline conditions (``simDraw`` in ui.js)."""
    baseline = p.with_baseline_conditions()
    cs = cycles_to_eol(p, base_fade)
    cb = cycles_to_eol(baseline, base_fade)
    delta = cs - cb if cs is not None and cb is not None else None
    return ScenarioComparison(
        params=p,
        cycles_to_eol=cs,
        baseline_params=baseline,
        baseline_cycles_to_eol=cb,
        delta_cycles=delta,
        delta_pct=None if delta is None or cb is None else js_div(delta, cb) * 100,
        soh_after_horizon_pct=soh_at(p, p.horizon_cycles, base_fade),
        baseline_soh_after_horizon_pct=soh_at(baseline, p.horizon_cycles, base_fade),
    )
