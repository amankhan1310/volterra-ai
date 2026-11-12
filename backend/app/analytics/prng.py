"""mulberry32 pseudo-random number generator, ported bit-exactly from ``legacy/core.js:6-14``.

JavaScript source::

    function rng(a) {
      return () => {
        a |= 0;
        a = (a + 0x6d2b79f5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
      };
    }

Each output is ``uint32 / 2**32`` and is therefore reproduced exactly.
"""

from __future__ import annotations

from collections.abc import Callable

from app.analytics.jsmath import imul, number_to_int32, to_int32, to_uint32

_INCREMENT = 0x6D2B79F5
_TWO_32 = 4294967296


class Mulberry32:
    """Stateful generator; each call returns the next value in ``[0, 1)``."""

    __slots__ = ("_state",)

    def __init__(self, seed: float) -> None:
        self._state = number_to_int32(seed)  # `a |= 0` on the first call

    def next_uint32(self) -> int:
        a = to_int32(self._state + _INCREMENT)
        self._state = a
        t = imul(a ^ (to_uint32(a) >> 15), 1 | a)
        t = to_int32(t + imul(t ^ (to_uint32(t) >> 7), 61 | t)) ^ t
        return to_uint32(t ^ (to_uint32(t) >> 14))

    def __call__(self) -> float:
        return self.next_uint32() / _TWO_32


def mulberry32(seed: float) -> Callable[[], float]:
    """Return a generator function equivalent to the prototype's ``rng(seed)``."""
    return Mulberry32(seed)
