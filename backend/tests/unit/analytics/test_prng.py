"""Unit and property tests for the mulberry32 port."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from app.analytics.prng import Mulberry32, mulberry32


@given(st.integers(min_value=-(2**40), max_value=2**40), st.integers(1, 50))
def test_values_are_in_unit_interval_and_exact_uint32_fractions(seed: int, n: int) -> None:
    gen = Mulberry32(seed)
    for _ in range(n):
        value = gen()
        assert 0.0 <= value < 1.0
        assert (value * 4294967296).is_integer()


def test_same_seed_same_sequence_and_generators_are_independent() -> None:
    a, b = mulberry32(7), mulberry32(7)
    first = [a() for _ in range(10)]
    assert [b() for _ in range(10)] == first
    c = mulberry32(7)
    c()
    assert mulberry32(7)() == first[0]


def test_seed_is_coerced_like_javascript_int32() -> None:
    zero = [mulberry32(0)() for _ in range(3)]
    assert [mulberry32(4294967296)() for _ in range(3)] == zero
    assert mulberry32(7.9)() == mulberry32(7)()
