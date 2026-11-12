"""State of health, fade rate, remaining useful life and forecast (v1).

Ported from ``legacy/core.js:57-64`` and the Overview renderer in ``legacy/ui.js``::

    const W0 = N - 120, F = lin(cycles W0..N-1, soh);
    const sohNow = F.b + F.s * (N - 1), fade = -F.s;
    const rulAt = (e, s = F.s) => (s < 0 ? Math.max(0, (sohNow - e) / -s) : null);
    // 95% "fit interval": rulAt(e, F.s - 1.96 * F.se) .. rulAt(e, F.s + 1.96 * F.se)
    const xt = () => Math.min(N + Math.ceil((rulAt(P.E) || 200) * 1.4), N + 500);   // ui.js:190
    used = Math.min(1, (100 - sohNow) / (100 - P.E));                                 // ui.js:242

Known defects reproduced on purpose (fixed only in v2): **F3**, the interval reflects slope
standard error only; **F6**, a straight line is fitted to accelerating (quadratic) fade.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from app.analytics.jsmath import js_ceil, js_div, js_max, js_min, js_truthy
from app.analytics.stats import LinearFit, lin
from app.analytics.synthetic import CycleRecord
from app.analytics.types import Provenance

RECENT_WINDOW_CYCLES = 120
DEFAULT_EOL_PCT = 80.0
INTERVAL_Z_95 = 1.96
FORECAST_FALLBACK_RUL_CYCLES = 200
FORECAST_STRETCH = 1.4
FORECAST_MAX_EXTRA_CYCLES = 500


@dataclass(frozen=True)
class TrendSummary:
    """Linear SOH trend over the most recent cycles."""

    fit: LinearFit
    fit_from_cycle: int
    fit_to_cycle: int
    n_cycles: int
    soh_now_pct: float
    fade_pct_per_cycle: float
    observed_last_soh_pct: float

    provenance: ClassVar[Provenance] = "fitted"


@dataclass(frozen=True)
class RulInterval:
    """The prototype's "95% fit interval" for RUL (slope SE only, see F3)."""

    lower: float | None
    upper: float | None
    level: float = 0.95
    method: str = "slope_se"

    provenance: ClassVar[Provenance] = "predicted"


def recent_trend(
    records: Sequence[CycleRecord], window: int = RECENT_WINDOW_CYCLES
) -> TrendSummary:
    """Fit SOH against cycle index over the last ``window`` cycles."""
    n = len(records)
    if not 3 <= window <= n:
        raise ValueError(f"window must be between 3 and the number of cycles ({n})")
    rows = records[n - window :]
    fit = lin([r.cycle for r in rows], [r.soh_pct for r in rows])
    return TrendSummary(
        fit=fit,
        fit_from_cycle=rows[0].cycle,
        fit_to_cycle=rows[-1].cycle,
        n_cycles=n,
        soh_now_pct=fit.intercept + fit.slope * (n - 1),
        fade_pct_per_cycle=-fit.slope,
        observed_last_soh_pct=records[-1].soh_pct,
    )


def rul_at(trend: TrendSummary, eol_pct: float, slope: float | None = None) -> float | None:
    """Cycles until the linear trend reaches ``eol_pct``; ``None`` unless the slope is negative."""
    s = trend.fit.slope if slope is None else slope
    if not s < 0:
        return None
    return js_max(0, (trend.soh_now_pct - eol_pct) / -s)


def rul_interval_95(trend: TrendSummary, eol_pct: float) -> RulInterval:
    """RUL recomputed with slope ∓ 1.96·SE (``lower`` uses the steeper slope)."""
    fit = trend.fit
    return RulInterval(
        lower=rul_at(trend, eol_pct, fit.slope - INTERVAL_Z_95 * fit.slope_se),
        upper=rul_at(trend, eol_pct, fit.slope + INTERVAL_Z_95 * fit.slope_se),
    )


def forecast_extent(n_cycles: int, rul_cycles: float | None) -> int:
    """Number of cycle positions on the Overview timeline (``xt()`` in ui.js)."""
    base = rul_cycles if js_truthy(rul_cycles) and rul_cycles is not None else 200
    stretched = n_cycles + js_ceil(base * FORECAST_STRETCH)
    return int(js_min(stretched, n_cycles + FORECAST_MAX_EXTRA_CYCLES))


def forecast_series(trend: TrendSummary, extent: int) -> list[float]:
    """Linear forecast values for cycles ``n-1 .. extent-1``."""
    fit = trend.fit
    return [fit.intercept + fit.slope * i for i in range(trend.n_cycles - 1, extent)]


def life_used_fraction(soh_now_pct: float, eol_pct: float) -> float:
    """Inner gauge ring: share of life used down to the EOL threshold, capped at 1."""
    return js_min(1, js_div(100 - soh_now_pct, 100 - eol_pct))
