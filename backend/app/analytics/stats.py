"""Ordinary least squares and median, ported from ``legacy/core.js:35-56``.

JavaScript source::

    function lin(xs, ys) {
      const n = xs.length, mx = xs.reduce((a, b) => a + b) / n, my = ys.reduce((a, b) => a + b) / n;
      let sxx = 0, sxy = 0;
      xs.forEach((x, k) => { sxx += (x - mx) ** 2; sxy += (x - mx) * (ys[k] - my); });
      const s = sxy / sxx, b = my - s * mx;
      const sd = Math.sqrt(ys.reduce((a, y, k) => a + (y - b - s * xs[k]) ** 2, 0) / (n - 2));
      return { s, b, sd, se: sd / Math.sqrt(sxx) };
    }
    const med = (a) => { const s = [...a].sort((x, y) => x - y), m = s.length >> 1;
                         return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

Accumulation order is preserved exactly (``x ** 2`` is computed as ``d * d``, which V8's ``pow``
special-cases identically). Degenerate inputs return NaN as in JavaScript instead of raising.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from app.analytics.jsmath import js_div, reduce_add
from app.analytics.types import Provenance


@dataclass(frozen=True)
class LinearFit:
    """Result of :func:`lin`: ``y ≈ intercept + slope * x``."""

    slope: float
    intercept: float
    residual_sd: float
    slope_se: float

    provenance: ClassVar[Provenance] = "fitted"

    def predict(self, x: float) -> float:
        return self.intercept + self.slope * x


def lin(xs: Sequence[float], ys: Sequence[float]) -> LinearFit:
    """Least-squares line through ``(xs, ys)``, exactly as the prototype computes it.

    ``residual_sd`` and ``slope_se`` are NaN when ``n == 2``; the slope is NaN when all x are
    equal. Raises ``TypeError`` for empty input (JavaScript ``reduce`` on an empty array).
    """
    if len(xs) != len(ys):
        raise ValueError("xs and ys must have the same length")
    xf = [float(x) for x in xs]
    yf = [float(y) for y in ys]
    n = len(xf)
    mx = reduce_add(xf) / n
    my = reduce_add(yf) / n
    sxx = 0.0
    sxy = 0.0
    for x, y in zip(xf, yf, strict=True):
        dx = x - mx
        sxx += dx * dx
        sxy += dx * (y - my)
    s = js_div(sxy, sxx)
    b = my - s * mx
    acc = 0.0
    for x, y in zip(xf, yf, strict=True):
        r = y - b - s * x
        acc += r * r
    sd = math.sqrt(js_div(acc, n - 2))
    return LinearFit(slope=s, intercept=b, residual_sd=sd, slope_se=js_div(sd, math.sqrt(sxx)))


def median(values: Sequence[float]) -> float:
    """Median as the prototype computes it; NaN for an empty input (no exception)."""
    s = sorted(float(v) for v in values)
    m = len(s) >> 1
    if len(s) % 2:
        return s[m]
    if not s:
        return math.nan
    return (s[m - 1] + s[m]) / 2
