"""Parity: mulberry32 sequences match ``prng.json`` bit-for-bit."""

from __future__ import annotations

from app.analytics.prng import Mulberry32
from tests.support.golden import assert_matches


def test_prng_sequences_match_golden(golden) -> None:
    expected = golden("prng")["sequences"]
    actual = []
    for seq in expected:
        gen = Mulberry32(seq["seed"])
        uints = [gen.next_uint32() for _ in seq["values"]]
        actual.append(
            {"seed": seq["seed"], "values": [u / 4294967296 for u in uints], "uint32": uints}
        )
    assert_matches(actual, expected, label="prng")
