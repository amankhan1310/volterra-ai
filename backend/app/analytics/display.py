"""Health level and condition label (``legacy/core.js:166-175``).

Returns semantic values only. Mapping a level to a colour is presentation and belongs to the
frontend (the prototype used ``var(--gr)``, ``var(--am)`` and ``var(--rd)``).
"""

from __future__ import annotations

from typing import Literal

HealthLevel = Literal["healthy", "caution", "critical"]

CAUTION_BELOW_PCT = 85.0
CRITICAL_BELOW_PCT = 80.0


def health_level(soh_pct: float) -> HealthLevel:
    """``hcol``: >= 85 healthy, >= 80 caution, otherwise critical (NaN is critical)."""
    if soh_pct >= CAUTION_BELOW_PCT:
        return "healthy"
    if soh_pct >= CRITICAL_BELOW_PCT:
        return "caution"
    return "critical"


def condition_label(soh_pct: float) -> str:
    """``cond``: the condition text shown on the Overview."""
    if soh_pct >= 90:
        return "Healthy"
    if soh_pct >= 85:
        return "Good"
    if soh_pct >= 80:
        return "Approaching end-of-life threshold"
    return "Below threshold"
