"""Tests for JavaScript number semantics. Expected values were produced by V8 (Node.js)."""

from __future__ import annotations

import math
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.analytics import jsmath

# [x, digits, x.toFixed(digits)] from V8.
TO_FIXED = [
    (0.125, 2, "0.13"),
    (-0.125, 2, "-0.13"),
    (0.5, 0, "1"),
    (1.5, 0, "2"),
    (2.5, 0, "3"),
    (-2.5, 0, "-3"),
    (1.005, 2, "1.00"),
    (9.995, 2, "9.99"),
    (-0.0, 1, "0.0"),
    (-0.0001, 1, "-0.0"),
    (86.08941987140724, 1, "86.1"),
    (0.05401766159185438, 3, "0.054"),
    (0.5777011523851212, 2, "0.58"),
    (1e-7, 3, "0.000"),
    (123.456, 0, "123"),
    (0.000001, 7, "0.0000010"),
]

# [x, Math.round(x), Object.is(result, -0)] from V8.
ROUND = [
    (0.5, 1, False),
    (1.5, 2, False),
    (2.5, 3, False),
    (-0.5, 0, True),
    (-1.5, -1, False),
    (-2.5, -2, False),
    (0.49999999999999994, 0, False),
    (-0.49999999999999994, 0, True),
    (860.8941987140724, 861, False),
    (-0.4, 0, True),
    (1e16, 1e16, False),
    (4503599627370495.5, 4503599627370496, False),
]

# [a, b, Math.imul(a, b)] from V8.
IMUL = [
    (3, 4, 12),
    (-5, 12, -60),
    (4294967295, 5, -5),
    (2147483647, 2, -2),
    (1831565813, 1831565813, -731413383),
    (-2147483648, -1, -2147483648),
]

# [x, x | 0] from V8.
INT32 = [
    (0, 0),
    (1, 1),
    (-1, -1),
    (2147483647, 2147483647),
    (2147483648, -2147483648),
    (4294967295, -1),
    (4294967296, 0),
    (-2147483649, 2147483647),
    (7.9, 7),
    (-7.9, -7),
    (1e20, 1661992960),
    (math.nan, 0),
    (math.inf, 0),
]


@pytest.mark.parametrize(("x", "digits", "expected"), TO_FIXED)
def test_to_fixed_matches_v8(x: float, digits: int, expected: str) -> None:
    assert jsmath.to_fixed(x, digits) == expected


def test_to_fixed_non_finite_and_limits() -> None:
    assert jsmath.to_fixed(math.nan, 2) == "NaN"
    assert jsmath.to_fixed(math.inf, 2) == "Infinity"
    assert jsmath.to_fixed(-math.inf, 2) == "-Infinity"
    with pytest.raises(ValueError):
        jsmath.to_fixed(1.0, 101)
    with pytest.raises(NotImplementedError):
        jsmath.to_fixed(1e21, 2)


@given(st.floats(min_value=-1e15, max_value=1e15, allow_nan=False), st.integers(0, 12))
def test_to_fixed_is_within_half_a_unit(x: float, digits: int) -> None:
    text = jsmath.to_fixed(x, digits)
    assert abs(Decimal(text) - Decimal(x)) <= Decimal(1).scaleb(-digits) / 2
    assert text.count(".") == (1 if digits else 0)


@pytest.mark.parametrize(("x", "expected", "negative_zero"), ROUND)
def test_js_round_matches_v8(x: float, expected: float, negative_zero: bool) -> None:
    result = jsmath.js_round(x)
    assert result == expected
    is_negative_zero = result == 0 and math.copysign(1.0, result) < 0
    assert is_negative_zero == negative_zero


def test_js_round_and_ceil_pass_non_finite_through() -> None:
    assert math.isnan(jsmath.js_round(math.nan))
    assert jsmath.js_round(math.inf) == math.inf
    assert jsmath.js_ceil(math.inf) == math.inf
    assert math.isnan(jsmath.js_ceil(math.nan))
    assert jsmath.js_ceil(1.2) == 2.0
    assert isinstance(jsmath.js_ceil(1.2), float)


@pytest.mark.parametrize(("a", "b", "expected"), IMUL)
def test_imul_matches_v8(a: int, b: int, expected: int) -> None:
    assert jsmath.imul(a, b) == expected


@pytest.mark.parametrize(("x", "expected"), INT32)
def test_number_to_int32_matches_v8(x: float, expected: int) -> None:
    assert jsmath.number_to_int32(x) == expected


@given(st.integers(min_value=-(2**70), max_value=2**70))
def test_int32_and_uint32_ranges(x: int) -> None:
    assert -(2**31) <= jsmath.to_int32(x) < 2**31
    assert 0 <= jsmath.to_uint32(x) < 2**32
    assert jsmath.to_uint32(jsmath.to_int32(x)) == jsmath.to_uint32(x)


def test_reduce_add_is_left_to_right_without_compensation() -> None:
    values = [1e16, 1.0, -1e16]
    # Left-to-right double addition loses the 1.0; compensated summation would keep it.
    assert jsmath.reduce_add(values) == 0.0
    assert jsmath.sum_from_zero(values) == 0.0
    assert math.fsum(values) == 1.0
    with pytest.raises(TypeError):
        jsmath.reduce_add([])
    assert jsmath.sum_from_zero([]) == 0.0


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [(1.0, 0.0, math.inf), (-1.0, 0.0, -math.inf), (1.0, -0.0, -math.inf), (6.0, 3.0, 2.0)],
)
def test_js_div(a: float, b: float, expected: float) -> None:
    assert jsmath.js_div(a, b) == expected


def test_js_div_zero_by_zero_and_nan() -> None:
    assert math.isnan(jsmath.js_div(0.0, 0.0))
    assert math.isnan(jsmath.js_div(math.nan, 0.0))


def test_js_max_min_propagate_nan() -> None:
    assert math.isnan(jsmath.js_max(0, math.nan))
    assert math.isnan(jsmath.js_min(1, math.nan))
    assert max(0, math.nan) == 0  # the Python pitfall these helpers avoid
    assert jsmath.js_max(0, -3.0) == 0
    assert jsmath.js_min(1, 0.5) == 0.5


@pytest.mark.parametrize(
    ("value", "truthy"),
    [(None, False), (0, False), (0.0, False), (-0.0, False), (math.nan, False), ("", False)]
    + [(1, True), (0.1, True), (math.inf, True), ("x", True), (True, True), (False, False)],
)
def test_js_truthy(value: object, truthy: bool) -> None:
    assert jsmath.js_truthy(value) is truthy
