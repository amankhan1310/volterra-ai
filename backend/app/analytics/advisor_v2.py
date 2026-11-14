"""Charging Advisor, version 2: explicit "cannot compare" state (fixes F8).

v1 reproduces the live prototype renderer: ``d = n && b ? ((n - b) / b) * 100 : 0``. When either
cycle count is unknown (beyond the 5000-cycle horizon) or the baseline is already at end of life,
a change is reported as **0%**, which reads as "no effect" (**F8**, ARCHITECTURE_PLAN.md §3.6).

v2 runs the same six one-factor changes on the v2 simulator (anchored to the v2 forecast, F4) and
reports each row's ``change_pct`` as ``None`` with an explicit ``comparison`` state when it cannot
be computed:

* ``"comparable"``: both counts known and the baseline above 0; ``change_pct`` is a number.
* ``"at_or_below_eol"``: the baseline is already at end of life (0 cycles).
* ``"beyond_horizon"``: the baseline or the changed scenario never reaches end of life within the
  simulator's 5000-cycle horizon.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import ClassVar, Literal

from app.analytics.advisor import ADVISOR_CHANGES, AdvisorChange
from app.analytics.forecast_v2 import TrendSummaryV2
from app.analytics.simulator import LEGACY_KEYS, ScenarioParams
from app.analytics.simulator_v2 import cycles_to_eol_v2
from app.analytics.types import Provenance

Comparison = Literal["comparable", "at_or_below_eol", "beyond_horizon"]


@dataclass(frozen=True)
class AdvisorRowV2:
    change: AdvisorChange
    cycles_to_eol: int | None
    #: Percentage change in cycles to EOL vs the baseline; ``None`` unless ``comparable``.
    change_pct: float | None
    comparison: Comparison


@dataclass(frozen=True)
class AdvisorTableV2:
    start_soh_pct: float
    eol_pct: float
    baseline_cycles_to_eol: int | None
    rows: tuple[AdvisorRowV2, ...]

    provenance: ClassVar[Provenance] = "simulated"


def compare_cycles(n: int | None, baseline: int | None) -> tuple[float | None, Comparison]:
    """Percentage change of ``n`` vs ``baseline``, or ``None`` with the reason it is undefined."""
    if baseline is None or n is None:
        return None, "beyond_horizon"
    if baseline == 0:
        return None, "at_or_below_eol"
    return (n - baseline) / baseline * 100, "comparable"


def sensitivity_table_v2(p: ScenarioParams, trend: TrendSummaryV2) -> AdvisorTableV2:
    """Cycles to EOL for each one-factor change relative to the baseline conditions."""
    base = p.with_baseline_conditions()
    b = cycles_to_eol_v2(base, trend)
    rows = []
    for change in ADVISOR_CHANGES:
        overrides = {LEGACY_KEYS[k]: v for k, v in change.override.items()}
        n = cycles_to_eol_v2(dataclasses.replace(base, **overrides), trend)  # type: ignore[arg-type]
        pct, comparison = compare_cycles(n, b)
        rows.append(AdvisorRowV2(change, n, pct, comparison))
    return AdvisorTableV2(
        start_soh_pct=p.start_soh_pct,
        eol_pct=p.eol_pct,
        baseline_cycles_to_eol=b,
        rows=tuple(rows),
    )
