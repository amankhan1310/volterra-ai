"""Rule-based insights, version 1 (ported from ``legacy/core.js:277-291`` and ``ui.js:196-228``).

Returns structured results (kind, text, values). The text reproduces the prototype's strings
exactly, including JavaScript ``toFixed`` rounding.

Known defect reproduced on purpose: **F5**, the second insight always says
"Fade is accelerating" regardless of the computed slopes. (The Overview hero sentence does apply
its ``fade > first_half * 1.2`` rule; see :func:`overview_acceleration_v1`.)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal

from app.analytics.anomalies import AnomalyReport
from app.analytics.backtest import BacktestResult
from app.analytics.health import TrendSummary
from app.analytics.jsmath import to_fixed
from app.analytics.stats import lin
from app.analytics.synthetic import CycleRecord
from app.analytics.types import Provenance

InsightKind = Literal["observation", "watch", "note", "model"]

FIRST_HALF_CYCLES = 160
ACCELERATION_RATIO = 1.2
ACCELERATION_NOTE = (
    " Fade has accelerated over the cell’s life, so the true remaining life may be shorter"
    " than a linear fit implies."
)


@dataclass(frozen=True)
class Insight:
    kind: InsightKind
    text: str
    values: Mapping[str, float | int]

    provenance: ClassVar[Provenance] = "fitted"


@dataclass(frozen=True)
class AccelerationNote:
    accelerated: bool
    appended_text: str


def first_half_fade(records: Sequence[CycleRecord]) -> float:
    """Fade rate (% SOH / cycle) fitted over the first 160 cycles."""
    rows = records[:FIRST_HALF_CYCLES]
    return -lin([r.cycle for r in rows], [r.soh_pct for r in rows]).slope


def generate_insights_v1(
    records: Sequence[CycleRecord],
    trend: TrendSummary,
    anomalies: AnomalyReport,
    backtest: BacktestResult,
) -> tuple[Insight, ...]:
    """The four Overview insights, in the prototype's order."""
    first_soh = records[0].soh_pct
    fade = trend.fade_pct_per_cycle
    early = first_half_fade(records)
    temp_events = len(anomalies.detected_cycles("temp"))
    volt_events = len(anomalies.detected_cycles("volt"))
    n = len(records)
    return (
        Insight(
            "observation",
            f"Capacity fell from {to_fixed(first_soh, 1)}% to {to_fixed(trend.soh_now_pct, 1)}%"
            f" SOH over {n} cycles; recent fade is {to_fixed(fade, 3)} %/cycle.",
            {"first_soh_pct": first_soh, "soh_now_pct": trend.soh_now_pct, "n_cycles": n},
        ),
        Insight(
            "watch",
            f"Fade is accelerating: first-half {to_fixed(early, 3)} vs last-120"
            f" {to_fixed(fade, 3)} %/cycle.",  # F5: unconditional wording
            {"first_half_fade_pct_per_cycle": early, "recent_fade_pct_per_cycle": fade},
        ),
        Insight(
            "note",
            f"{temp_events} temperature and {volt_events} voltage events were flagged. With so"
            " few events there is insufficient evidence to link them to degradation"
            " (correlation ≠ causation).",
            {"temp_events": temp_events, "volt_events": volt_events},
        ),
        Insight(
            "model",
            f"The straight-line forecast has a hold-out MAE of {to_fixed(backtest.mae, 2)} SOH"
            " points; treat the RUL as an estimate.",
            {"backtest_mae": backtest.mae},
        ),
    )


def overview_acceleration_v1(fade: float, first_half: float) -> AccelerationNote:
    """Overview hero rule: note acceleration when recent fade exceeds 1.2× the early fade."""
    accelerated = fade > first_half * ACCELERATION_RATIO
    return AccelerationNote(accelerated, ACCELERATION_NOTE if accelerated else "")
