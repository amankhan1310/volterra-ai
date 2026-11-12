"""Unit and property tests for lin and median."""

from __future__ import annotations

import math
import statistics
from fractions import Fraction

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from app.analytics.stats import LinearFit, lin, median

finite = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)


def exact_ols(xs: list[float], ys: list[float]) -> tuple[Fraction, Fraction]:
    fx = [Fraction(x) for x in xs]
    fy = [Fraction(y) for y in ys]
    n = len(fx)
    zero = Fraction(0)
    mx, my = sum(fx, zero) / n, sum(fy, zero) / n
    sxx = sum(((x - mx) * (x - mx) for x in fx), zero)
    sxy = sum(((x - mx) * (y - my) for x, y in zip(fx, fy, strict=True)), zero)
    slope = sxy / sxx
    return slope, my - slope * mx


@given(st.lists(st.tuples(finite, finite), min_size=3, max_size=40))
def test_lin_agrees_with_exact_rational_ols(points: list[tuple[float, float]]) -> None:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    # Well-conditioned inputs only: with x spread below ~1e-3, Sxx underflows or cancels and the
    # comparison would test floating-point conditioning (identical in JS), not the port.
    assume(max(xs) - min(xs) > 1e-3)
    slope, intercept = exact_ols(xs, ys)
    assume(abs(slope) < 1e6)
    fit = lin(xs, ys)
    scale = max(1.0, abs(float(slope)))
    assert math.isclose(fit.slope, float(slope), rel_tol=1e-6, abs_tol=1e-6 * scale)
    assert fit.residual_sd >= 0


@given(st.integers(-50, 50), st.integers(-50, 50), st.integers(3, 30))
def test_lin_recovers_an_exact_integer_line(a: int, b: int, n: int) -> None:
    xs = list(range(n))
    fit = lin(xs, [a + b * x for x in xs])
    assert math.isclose(fit.slope, b, abs_tol=1e-9)
    assert math.isclose(fit.intercept, a, abs_tol=1e-9)
    assert fit.residual_sd < 1e-6


def test_lin_degenerate_inputs_follow_javascript() -> None:
    two = lin([0, 1], [1, 2])
    assert (two.slope, two.intercept) == (1.0, 1.0)
    assert math.isnan(two.residual_sd) and math.isnan(two.slope_se)
    flat = lin([3, 3, 3], [1, 2, 3])
    assert math.isnan(flat.slope)
    with pytest.raises(TypeError):
        lin([], [])
    with pytest.raises(ValueError):
        lin([1, 2, 3], [1, 2])


def test_predict_and_provenance() -> None:
    fit = LinearFit(slope=2.0, intercept=1.0, residual_sd=0.0, slope_se=0.0)
    assert fit.predict(3) == 7.0
    assert fit.provenance == "fitted"


@given(st.lists(finite, min_size=1, max_size=50))
def test_median_matches_statistics_median(values: list[float]) -> None:
    assert median(values) == statistics.median(values)


def test_median_empty_is_nan() -> None:
    assert math.isnan(median([]))
