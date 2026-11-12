"""JavaScript number semantics needed for exact parity with the legacy prototype.

Python and JavaScript share IEEE-754 doubles but differ in several operations. Each helper here
reproduces the JavaScript behaviour the prototype relies on:

* ``arr.reduce((a, b) => a + b)``: Python 3.12+ ``sum()`` uses compensated summation.
  Use :func:`reduce_add` / :func:`sum_from_zero`.
* ``Math.round``: ``round()`` rounds half to even. Use :func:`js_round`.
* ``Math.ceil``: ``math.ceil`` returns int and fails on infinity. Use :func:`js_ceil`.
* ``x.toFixed(d)``: ``format`` rounds ties to even. Use :func:`to_fixed`.
* ``a / 0``: Python raises ``ZeroDivisionError``. Use :func:`js_div`.
* ``Math.max`` / ``Math.min``: ``max(0, nan)`` is 0 in Python. Use :func:`js_max`, :func:`js_min`.
* Truthiness (``||``, ``&&``): NaN is truthy in Python. Use :func:`js_truthy`.
* ``x | 0``, ``x >>> 0``, ``Math.imul``: Python ints are unbounded. Use :func:`to_int32`,
  :func:`to_uint32`, :func:`number_to_int32`, :func:`imul`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

_UINT32 = 0xFFFF_FFFF
_INT32_SIGN = 0x8000_0000
_TWO_32 = 0x1_0000_0000


def to_uint32(x: int) -> int:
    """ToUint32 for an integer value (JavaScript ``x >>> 0``)."""
    return x & _UINT32


def to_int32(x: int) -> int:
    """ToInt32 for an integer value (JavaScript ``x | 0``)."""
    x &= _UINT32
    return x - _TWO_32 if x & _INT32_SIGN else x


def number_to_int32(value: float) -> int:
    """ToInt32 for any JavaScript number: NaN/±Infinity -> 0, otherwise truncate and wrap."""
    if isinstance(value, int):
        return to_int32(value)
    if not math.isfinite(value):
        return 0
    return to_int32(math.trunc(value))


def imul(a: int, b: int) -> int:
    """JavaScript ``Math.imul``: low 32 bits of the product, as a signed 32-bit integer."""
    return to_int32(to_int32(a) * to_int32(b))


def reduce_add(values: Iterable[float]) -> float:
    """``values.reduce((a, b) => a + b)``: strict left-to-right addition, no initial value.

    Raises ``TypeError`` for an empty input, as JavaScript does.
    """
    it = iter(values)
    try:
        acc = float(next(it))
    except StopIteration:
        raise TypeError("Reduce of empty array with no initial value") from None
    for v in it:
        acc += v
    return acc


def sum_from_zero(values: Iterable[float]) -> float:
    """``values.reduce((a, b) => a + b, 0)``: strict left-to-right addition starting at 0."""
    acc = 0.0
    for v in values:
        acc += v
    return acc


def js_div(a: float, b: float) -> float:
    """JavaScript division: ``x / 0`` is ±Infinity and ``0 / 0`` is NaN instead of raising."""
    if b != 0:
        return a / b
    if a == 0 or math.isnan(a):
        return math.nan
    return math.copysign(math.inf, a) * math.copysign(1.0, b)


def js_max(*values: float) -> float:
    """``Math.max``: NaN if any argument is NaN."""
    if any(math.isnan(v) for v in values):
        return math.nan
    return max(values)


def js_min(*values: float) -> float:
    """``Math.min``: NaN if any argument is NaN."""
    if any(math.isnan(v) for v in values):
        return math.nan
    return min(values)


def js_truthy(value: object) -> bool:
    """JavaScript truthiness for the value types the prototype uses (None, bool, numbers, str)."""
    if value is None:
        return False
    if isinstance(value, float):
        return value != 0 and not math.isnan(value)
    return bool(value)


def js_round(x: float) -> float:
    """``Math.round``: nearest integer, ties toward +Infinity (not banker's rounding)."""
    if not math.isfinite(x):
        return x
    floor = math.floor(x)
    result = float(floor + 1) if x - floor >= 0.5 else float(floor)
    return math.copysign(0.0, x) if result == 0 else result


def js_ceil(x: float) -> float:
    """``Math.ceil``: returns a float and passes NaN/±Infinity through."""
    return x if not math.isfinite(x) else float(math.ceil(x))


def to_fixed(x: float, digits: int) -> str:
    """``Number.prototype.toFixed`` for 0 <= digits <= 100.

    Rounds the exact binary value half away from zero (JavaScript picks the larger ``n`` on a
    tie), prints ``-0`` as ``"0"``, and uses ``String(x)`` for non-finite or |x| >= 1e21.
    """
    if not 0 <= digits <= 100:
        raise ValueError("digits must be between 0 and 100")
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if abs(x) >= 1e21:
        raise NotImplementedError("toFixed for |x| >= 1e21 falls back to String(x)")
    sign = "-" if x < 0 else ""
    quantum = Decimal(1).scaleb(-digits)
    rounded = Decimal(abs(x)).quantize(quantum, rounding=ROUND_HALF_UP)
    return f"{sign}{rounded:.{digits}f}"
