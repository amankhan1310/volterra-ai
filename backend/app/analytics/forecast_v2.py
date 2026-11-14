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

**F3 (prediction interval).** v1's "95% fit interval" re-runs RUL with slope ± 1.96·SE: it
ignores intercept error, residual noise and model-form error, so it is about 2.6 cycles wide
while the backtest error implies about ±11. v2 calibrates a **90% prediction interval** from
repeated historical backtests of this battery: the quadratic is refitted at every past origin,
its actual errors are collected per forecast horizon, and the 5% and 95% error quantiles bound
the forecast path. The interval is only claimed up to horizons with at least
``MIN_ORIGINS_PER_HORIZON`` backtests. **Calibration uses this battery's own history; it does not
establish coverage across batteries** (that needs held-out cells, Phase 6-7).

Standard library only; sums use ``jsmath`` (source-hygiene rule).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
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


# --- F3: calibrated prediction interval -------------------------------------------------------

INTERVAL_LEVEL_V2 = 0.90
INTERVAL_METHOD_V2 = "rolling_origin_backtest_quantiles"
INTERVAL_LABEL_V2 = "90% prediction interval"
#: A horizon is calibrated only if at least this many historical backtests reach it.
MIN_ORIGINS_PER_HORIZON = 30


@dataclass(frozen=True)
class ForecastErrors:
    """Errors (observed - predicted) of repeated historical backtests, by horizon in cycles.

    Each entry is ``(origin_cycle, error)``. Horizons count positions in the record sequence.
    """

    by_horizon: Mapping[int, tuple[tuple[int, float], ...]]
    window: int

    def calibrated_horizon(self, min_origins: int = MIN_ORIGINS_PER_HORIZON) -> int:
        """Largest horizon with at least ``min_origins`` backtests (0 if none)."""
        ok = [h for h, errs in self.by_horizon.items() if len(errs) >= min_origins]
        return max(ok) if ok else 0


def rolling_origin_errors(
    records: Sequence[CycleRecord], window: int = RECENT_WINDOW_CYCLES
) -> ForecastErrors:
    """Refit the v2 quadratic at every past origin and record its errors at every horizon."""
    cycles = [r.cycle for r in records]
    soh = [r.soh_pct for r in records]
    acc: dict[int, list[tuple[int, float]]] = {}
    for k in range(window - 1, len(records) - 1):
        lo = k - window + 1
        fit = quad_fit(cycles[lo : k + 1], soh[lo : k + 1], origin=cycles[k])
        for j in range(k + 1, len(records)):
            acc.setdefault(j - k, []).append((cycles[k], soh[j] - fit.ahead(j - k)))
    return ForecastErrors({h: tuple(v) for h, v in acc.items()}, window)


def empirical_quantile(values: Sequence[float], p: float) -> float:
    """Conformal-rank quantile: the ``ceil(p·(m+1))``-th smallest value, clamped to the sample."""
    if not values:
        raise ValueError("no values")
    s = sorted(values)
    idx = math.ceil(p * (len(s) + 1)) - 1
    return s[min(len(s) - 1, max(0, idx))]


@dataclass(frozen=True)
class PredictionIntervalV2:
    """RUL bounds; ``None`` when the bound lies beyond the calibrated horizon."""

    lower: float | None
    upper: float | None
    max_calibrated_horizon: int
    level: float = INTERVAL_LEVEL_V2
    method: str = INTERVAL_METHOD_V2
    label: str = INTERVAL_LABEL_V2

    provenance: ClassVar[Provenance] = "predicted"


def rul_interval_v2(
    trend: TrendSummaryV2,
    errors: ForecastErrors,
    eol_pct: float,
    level: float = INTERVAL_LEVEL_V2,
) -> PredictionIntervalV2:
    """First cycle at which the lower (upper) error band of the forecast reaches ``eol_pct``."""
    hmax = errors.calibrated_horizon()
    if trend.soh_now_pct <= eol_pct:
        return PredictionIntervalV2(lower=0.0, upper=0.0, max_calibrated_horizon=hmax)
    tail = (1 - level) / 2
    lower: float | None = None
    upper: float | None = None
    for t in range(1, hmax + 1):
        errs = [e for _, e in errors.by_horizon[t]]
        path = trend.fit.ahead(t)
        if lower is None and path + empirical_quantile(errs, tail) <= eol_pct:
            lower = float(t)
        if path + empirical_quantile(errs, 1 - tail) <= eol_pct:
            upper = float(t)
            break
    return PredictionIntervalV2(lower=lower, upper=upper, max_calibrated_horizon=hmax)


def held_out_coverage(
    errors: ForecastErrors, split_origin: int, level: float = INTERVAL_LEVEL_V2
) -> tuple[float, int]:
    """Calibrate on origins <= ``split_origin``, score backtests from later origins.

    Returns ``(coverage, n_scored)``: the share of later errors inside the earlier quantiles, for
    horizons with at least ``MIN_ORIGINS_PER_HORIZON`` calibration backtests.
    """
    tail = (1 - level) / 2
    inside = 0
    scored = 0
    for errs in errors.by_horizon.values():
        cal = [e for k, e in errs if k <= split_origin]
        if len(cal) < MIN_ORIGINS_PER_HORIZON:
            continue
        lo, hi = empirical_quantile(cal, tail), empirical_quantile(cal, 1 - tail)
        for k, e in errs:
            if k > split_origin:
                scored += 1
                inside += 1 if lo <= e <= hi else 0
    if scored == 0:
        raise ValueError("no backtests to score after split_origin")
    return inside / scored, scored
