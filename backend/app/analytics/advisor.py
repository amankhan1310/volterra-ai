"""Charging Advisor: one-factor sensitivity on the v1 simulator.

Ported from the live renderer ``legacy/ui.js:624-666``::

    const b = eolN({ ...P, ...BASE });
    rows: n = eolN({ ...P, ...BASE, ...change });
          d = n && b ? ((n - b) / b) * 100 : 0;

The original renderer (``legacy/core.js:249-266``) used ``null`` instead of ``0`` when either
cycle count is missing or zero. v1 reproduces the live ``ui.js`` behaviour; the discrepancy is
known defect **F8** and is preserved in the golden fixtures as evidence. Bar geometry is
presentation and belongs to the frontend.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import ClassVar

from app.analytics.jsmath import js_truthy
from app.analytics.simulator import LEGACY_KEYS, ScenarioParams, cycles_to_eol
from app.analytics.types import Provenance


@dataclass(frozen=True)
class AdvisorChange:
    label: str
    why: str
    override: dict[str, float]  # prototype keys (T, C, D)


ADVISOR_CHANGES: tuple[AdvisorChange, ...] = (
    AdvisorChange("Cooler: 15 °C", "Lower temperature slows modelled fade", {"T": 15}),
    AdvisorChange("Warmer: 35 °C", "Heat accelerates modelled fade", {"T": 35}),
    AdvisorChange("Gentler charge: 0.5C", "Slower charging reduces modelled stress", {"C": 0.5}),
    AdvisorChange("Fast charge: 2C", "Faster charging increases modelled stress", {"C": 2}),
    AdvisorChange("Shallower cycles: 60% DoD", "Less depth per cycle is gentler", {"D": 60}),
    AdvisorChange(
        "Full-depth cycles: 100% DoD", "Deeper cycles wear faster in the model", {"D": 100}
    ),
)


@dataclass(frozen=True)
class AdvisorRow:
    change: AdvisorChange
    cycles_to_eol: int | None
    delta_pct: float


@dataclass(frozen=True)
class AdvisorTable:
    start_soh_pct: float
    eol_pct: float
    baseline_cycles_to_eol: int | None
    rows: tuple[AdvisorRow, ...]

    provenance: ClassVar[Provenance] = "simulated"


def delta_pct_v1(n: int | None, baseline: int | None) -> float:
    """``n && b ? ((n - b) / b) * 100 : 0`` (ui.js). Missing or zero counts give 0 (F8)."""
    if js_truthy(n) and js_truthy(baseline) and n is not None and baseline is not None:
        return ((n - baseline) / baseline) * 100
    return 0.0


def sensitivity_table(p: ScenarioParams, base_fade: float) -> AdvisorTable:
    """Cycles to EOL for each one-factor change relative to the baseline conditions."""
    base = p.with_baseline_conditions()
    b = cycles_to_eol(base, base_fade)
    rows = []
    for change in ADVISOR_CHANGES:
        overrides = {LEGACY_KEYS[k]: v for k, v in change.override.items()}
        n = cycles_to_eol(dataclasses.replace(base, **overrides), base_fade)  # type: ignore[arg-type]
        rows.append(AdvisorRow(change=change, cycles_to_eol=n, delta_pct=delta_pct_v1(n, b)))
    return AdvisorTable(
        start_soh_pct=p.start_soh_pct,
        eol_pct=p.eol_pct,
        baseline_cycles_to_eol=b,
        rows=tuple(rows),
    )
