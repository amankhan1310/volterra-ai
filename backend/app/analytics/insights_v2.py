"""Rule-based insights, version 2: the fade wording follows the numbers (fixes F5).

v1's second insight always reads "Fade is accelerating", whatever the computed slopes (**F5**,
ARCHITECTURE_PLAN.md §3.6). The Overview hero applies a ``> 1.2×`` check; the insights panel did
not. On ``synthetic-v1`` the text happens to be true (fade did accelerate), so the defect is
dormant there, but it is wrong for any battery whose fade slows.

v2 classifies the fade explicitly with one rule shared by the insight and the Overview note,
comparing the current fade (v2 forecast) with the first-half fade (cycles 0-159):

* ratio > 1.2: **accelerating** (insight kind ``watch``)
* ratio < 1/1.2: **slowing**
* otherwise: **steady**

The other insights keep v1's wording but take v2 inputs (v2 anomalies, the v2 backtest).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from app.analytics.anomalies_v2 import AnomalyReportV2
from app.analytics.forecast_v2 import BacktestResultV2, TrendSummaryV2
from app.analytics.insights import (
    ACCELERATION_RATIO,
    AccelerationNote,
    Insight,
    first_half_fade,
)
from app.analytics.jsmath import to_fixed
from app.analytics.synthetic import CycleRecord

FadeTrend = Literal["accelerating", "slowing", "steady"]

ACCELERATION_NOTE_V2 = (
    " Fade has accelerated over the cell’s life; the v2 forecast follows the recent curvature,"
    " but extrapolating it far ahead is uncertain."
)


def classify_fade(recent: float, early: float) -> FadeTrend:
    """Accelerating above 1.2× the early fade, slowing below 1/1.2×, otherwise steady.

    With no early fade to compare against (``early <= 0``), any positive recent fade counts as
    accelerating and none as steady.
    """
    if early <= 0:
        return "accelerating" if recent > 0 else "steady"
    ratio = recent / early
    if ratio > ACCELERATION_RATIO:
        return "accelerating"
    if ratio < 1 / ACCELERATION_RATIO:
        return "slowing"
    return "steady"


FADE_SENTENCE: dict[FadeTrend, str] = {
    "accelerating": "Fade is accelerating",
    "slowing": "Fade is slowing",
    "steady": "Fade is steady",
}
FADE_RULE: dict[FadeTrend, str] = {
    "accelerating": "more than 1.2×",
    "slowing": "less than 1/1.2×",
    "steady": "within 1.2× either way",
}


def signed(x: float, digits: int) -> str:
    """``+0.04`` / ``-0.04``: ``toFixed`` with an explicit plus sign."""
    return ("+" if x >= 0 else "") + to_fixed(x, digits)


def generate_insights_v2(
    records: Sequence[CycleRecord],
    trend: TrendSummaryV2,
    anomalies: AnomalyReportV2,
    backtest: BacktestResultV2,
) -> tuple[Insight, ...]:
    """The four Overview insights, in v1's order, with the fade sentence decided by the rule."""
    first_soh = records[0].soh_pct
    fade = trend.fade_pct_per_cycle
    early = first_half_fade(records)
    verdict = classify_fade(fade, early)
    ratio = fade / early if early > 0 else 0.0
    temp_events = len(anomalies.detected_cycles("temp"))
    volt_events = len(anomalies.detected_cycles("volt"))
    n = len(records)
    return (
        Insight(
            "observation",
            f"Capacity fell from {to_fixed(first_soh, 1)}% to {to_fixed(trend.soh_now_pct, 1)}%"
            f" SOH over {n} cycles; current fade is {to_fixed(fade, 3)} %/cycle.",
            {"first_soh_pct": first_soh, "soh_now_pct": trend.soh_now_pct, "n_cycles": n},
        ),
        Insight(
            "watch" if verdict == "accelerating" else "observation",
            f"{FADE_SENTENCE[verdict]}: first-half {to_fixed(early, 3)} vs current"
            f" {to_fixed(fade, 3)} %/cycle ({FADE_RULE[verdict]}).",
            {
                "first_half_fade_pct_per_cycle": early,
                "recent_fade_pct_per_cycle": fade,
                "fade_ratio": ratio,
            },
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
            f"The interim quadratic forecast has a hold-out MAE of {to_fixed(backtest.mae, 2)} SOH"
            f" points and a bias of {signed(backtest.mean_signed_error, 2)}; treat the RUL as an"
            " estimate.",
            {"backtest_mae": backtest.mae, "backtest_bias": backtest.mean_signed_error},
        ),
    )


def overview_acceleration_v2(fade: float, first_half: float) -> AccelerationNote:
    """Overview note from the same rule as the insight (so the two cannot disagree)."""
    accelerated = classify_fade(fade, first_half) == "accelerating"
    return AccelerationNote(accelerated, ACCELERATION_NOTE_V2 if accelerated else "")
