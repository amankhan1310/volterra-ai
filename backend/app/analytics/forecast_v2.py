"""Recent-trend SOH forecast, version 2: an interim quadratic fit (fixes F6).

v1 fits a straight line to the last 120 cycles. Fade on ``synthetic-v1`` is quadratic by
construction (``-5e-7·i²``), so the line is structurally optimistic: its time-ordered backtest
over-predicts SOH by +0.58 points on average (**F6**, ARCHITECTURE_PLAN.md §3.6).

v2 fits ``SOH(t) = c0 + c1·t + c2·t²`` over the **same** 120-cycle window, with ``t`` counted in
cycles from the last fitted cycle (so ``c0`` is the fitted SOH now and ``-c1`` the current fade
rate). On ``synthetic-v1`` the backtest bias falls from +0.576 to +0.042 SOH points.

**Interim model, not production-validated.** A quadratic matches the synthetic generator's shape
by construction; on real cells, extrapolating a quadratic far ahead can bend too fast or turn
upwards. It is a stop-gap until Phase 7 compares properly validated degradation models on
held-out cells (ARCHITECTURE_PLAN.md §9.2-9.3). v1 stays unchanged and is the API default.

Standard library only; sums use ``jsmath`` (source-hygiene rule).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from app.analytics.backtest import TEST_FROM_CYCLE, TRAIN_FROM_CYCLE, BacktestPoint
from app.analytics.health import RECENT_WINDOW_CYCLES
from app.analytics.jsmath import sum_from_zero
from app.analytics.synthetic import CycleRecord
from app.analytics.types import Provenance

FORECAST_VERSION_V2 = "v2"
FORECAST_MODEL_V2 = "quadratic_recent_120_cycles_interim"


@dataclass(frozen=True)
class QuadraticFit:
    """``y ≈ c0 + c1·t + c2·t²`` with ``t = cycle - origin``."""

    origin: int
    c0: float
    c1: float
    c2: float
    residual_sd: float
    #: Standard error of ``c1`` (the slope at the origin).
    slope_se: float

    provenance: ClassVar[Provenance] = "fitted"

    def ahead(self, t: float) -> float:
        """Fitted value ``t`` cycles after the origin."""
        return self.c0 + self.c1 * t + self.c2 * t * t

    def predict(self, cycle: float) -> float:
        return self.ahead(cycle - self.origin)


def _inverse3(m: Sequence[Sequence[float]]) -> list[list[float]]:
    """Inverse of a 3×3 matrix by the adjugate (the normal equations are tiny)."""
    (a, b, c), (d, e, f), (g, h, i) = m
    co = [
        [e * i - f * h, -(d * i - f * g), d * h - e * g],
        [-(b * i - c * h), a * i - c * g, -(a * h - b * g)],
        [b * f - c * e, -(a * f - c * d), a * e - b * d],
    ]
    det = a * co[0][0] + b * co[0][1] + c * co[0][2]
    if det == 0:
        raise ValueError("singular normal equations (need at least 3 distinct x values)")
    return [[co[col][row] / det for col in range(3)] for row in range(3)]


def quad_fit(xs: Sequence[float], ys: Sequence[float], origin: int) -> QuadraticFit:
    """Least-squares quadratic through ``(xs, ys)``, centred on ``origin``.

    Time is scaled by the number of points before solving, which keeps the normal equations well
    conditioned; coefficients are converted back to per-cycle units.
    """
    if len(xs) != len(ys):
        raise ValueError("xs and ys must have the same length")
    n = len(xs)
    if n < 4:
        raise ValueError("a quadratic fit needs at least 4 points")
    scale = float(n)
    us = [(float(x) - origin) / scale for x in xs]
    yf = [float(y) for y in ys]
    s = [sum_from_zero(u**k for u in us) for k in range(5)]
    rhs = [sum_from_zero(y * u**k for u, y in zip(us, yf, strict=True)) for k in range(3)]
    inv = _inverse3([[s[0], s[1], s[2]], [s[1], s[2], s[3]], [s[2], s[3], s[4]]])
    d0, d1, d2 = (sum_from_zero(inv[r][k] * rhs[k] for k in range(3)) for r in range(3))
    ssr = sum_from_zero((y - (d0 + d1 * u + d2 * u * u)) ** 2 for u, y in zip(us, yf, strict=True))
    sd = math.sqrt(ssr / (n - 3))
    return QuadraticFit(
        origin=origin,
        c0=d0,
        c1=d1 / scale,
        c2=d2 / (scale * scale),
        residual_sd=sd,
        slope_se=sd * math.sqrt(inv[1][1]) / scale,
    )


def first_crossing(start: float, c1: float, c2: float, level: float) -> float | None:
    """Smallest ``t >= 0`` with ``start + c1·t + c2·t² <= level``; ``None`` if it never gets there.

    Uses the numerically stable root formula, so a tiny curvature does not lose precision.
    """
    if start <= level:
        return 0.0
    gap = start - level  # > 0; solve c2·t² + c1·t + gap = 0
    if c2 == 0:
        return gap / -c1 if c1 < 0 else None
    disc = c1 * c1 - 4 * c2 * gap
    if disc < 0:
        return None
    q = -0.5 * (c1 + math.copysign(math.sqrt(disc), c1))
    roots = [q / c2] + ([gap / q] if q != 0 else [])
    positive = [r for r in roots if r > 0]
    return min(positive) if positive else None


@dataclass(frozen=True)
class TrendSummaryV2:
    """Quadratic SOH trend over the most recent cycles (origin = last fitted cycle)."""

    fit: QuadraticFit
    fit_from_cycle: int
    fit_to_cycle: int
    n_cycles: int
    soh_now_pct: float
    fade_pct_per_cycle: float
    observed_last_soh_pct: float
    model: str = FORECAST_MODEL_V2

    provenance: ClassVar[Provenance] = "fitted"


def recent_trend_v2(
    records: Sequence[CycleRecord], window: int = RECENT_WINDOW_CYCLES
) -> TrendSummaryV2:
    """Fit the quadratic over the last ``window`` cycles (the same window as v1)."""
    n = len(records)
    if not 4 <= window <= n:
        raise ValueError(f"window must be between 4 and the number of cycles ({n})")
    rows = records[n - window :]
    fit = quad_fit([r.cycle for r in rows], [r.soh_pct for r in rows], origin=rows[-1].cycle)
    return TrendSummaryV2(
        fit=fit,
        fit_from_cycle=rows[0].cycle,
        fit_to_cycle=rows[-1].cycle,
        n_cycles=n,
        soh_now_pct=fit.c0,
        fade_pct_per_cycle=-fit.c1,
        observed_last_soh_pct=records[-1].soh_pct,
    )


def rul_v2(trend: TrendSummaryV2, eol_pct: float) -> float | None:
    """Cycles until the quadratic forecast reaches ``eol_pct`` (0 if already there)."""
    return first_crossing(trend.soh_now_pct, trend.fit.c1, trend.fit.c2, eol_pct)


def forecast_series_v2(trend: TrendSummaryV2, extent: int) -> list[float]:
    """Forecast values for cycles ``n-1 .. extent-1`` (same positions as v1)."""
    return [trend.fit.predict(i) for i in range(trend.n_cycles - 1, extent)]


@dataclass(frozen=True)
class BacktestResultV2:
    train_from_cycle: int
    train_to_cycle: int
    test_from_cycle: int
    test_to_cycle: int
    fit: QuadraticFit
    points: tuple[BacktestPoint, ...]
    mae: float
    #: Mean of (predicted - observed): the forecast's bias (F6 acceptance: |bias| < 0.1).
    mean_signed_error: float

    provenance: ClassVar[Provenance] = "fitted"


def run_backtest_v2(
    records: Sequence[CycleRecord],
    train_from: int = TRAIN_FROM_CYCLE,
    test_from: int = TEST_FROM_CYCLE,
) -> BacktestResultV2:
    """The v1 hold-out split (fit 100-219, score 220-end) with the quadratic model."""
    if not 0 <= train_from < test_from < len(records):
        raise ValueError("need 0 <= train_from < test_from < number of cycles")
    train = records[train_from:test_from]
    test = records[test_from:]
    fit = quad_fit([r.cycle for r in train], [r.soh_pct for r in train], origin=train[-1].cycle)
    points = tuple(
        BacktestPoint(
            cycle=r.cycle,
            observed_soh_pct=r.soh_pct,
            predicted_soh_pct=fit.predict(r.cycle),
            abs_error=abs(fit.predict(r.cycle) - r.soh_pct),
        )
        for r in test
    )
    return BacktestResultV2(
        train_from_cycle=train[0].cycle,
        train_to_cycle=train[-1].cycle,
        test_from_cycle=test[0].cycle,
        test_to_cycle=test[-1].cycle,
        fit=fit,
        points=points,
        mae=sum_from_zero(p.abs_error for p in points) / len(points),
        mean_signed_error=sum_from_zero(p.predicted_soh_pct - p.observed_soh_pct for p in points)
        / len(points),
    )
