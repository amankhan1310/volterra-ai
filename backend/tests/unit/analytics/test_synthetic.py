"""Unit tests for the synthetic-v1 generator."""

from __future__ import annotations

import dataclasses
import math

import pytest

from app.analytics.synthetic import SYNTHETIC_V1, column, generate_synthetic_v1


def test_default_dataset_shape_and_determinism() -> None:
    a = generate_synthetic_v1()
    assert len(a) == 320
    assert [r.cycle for r in a] == list(range(320))
    assert generate_synthetic_v1() == a
    assert a[0].provenance == "simulated"


def test_shorter_dataset_is_a_prefix_of_the_default() -> None:
    full = generate_synthetic_v1()
    short = generate_synthetic_v1(dataclasses.replace(SYNTHETIC_V1, n_cycles=25))
    assert short == full[:25]


def test_soh_is_capacity_relative_to_nominal() -> None:
    for r in generate_synthetic_v1()[:20]:
        assert r.soh_pct == (r.capacity_ah / SYNTHETIC_V1.nominal_capacity_ah) * 100


def test_injected_spikes_and_dips_are_the_only_differences() -> None:
    base = generate_synthetic_v1()
    clean = generate_synthetic_v1(
        dataclasses.replace(SYNTHETIC_V1, temp_spike_cycles=(), voltage_dip_cycles=())
    )
    for a, b in zip(base, clean, strict=True):
        assert a.capacity_ah == b.capacity_ah
        if a.cycle in SYNTHETIC_V1.temp_spike_cycles:
            assert math.isclose(a.temp_c - b.temp_c, 9.0, abs_tol=1e-12)
        else:
            assert a.temp_c == b.temp_c
        if a.cycle in SYNTHETIC_V1.voltage_dip_cycles:
            assert math.isclose(b.voltage_v - a.voltage_v, 0.18, abs_tol=1e-12)
        else:
            assert a.voltage_v == b.voltage_v


def test_different_seed_gives_different_data() -> None:
    other = generate_synthetic_v1(dataclasses.replace(SYNTHETIC_V1, seed=8, n_cycles=5))
    assert other != generate_synthetic_v1()[:5]


def test_column() -> None:
    records = generate_synthetic_v1()
    assert column(records, "soh_pct") == [r.soh_pct for r in records]
    with pytest.raises(ValueError):
        column(records, "cycle")
