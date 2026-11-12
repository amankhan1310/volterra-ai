"""Unit and property tests for the v1 simulator and Charging Advisor."""

from __future__ import annotations

import dataclasses
import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.analytics.advisor import ADVISOR_CHANGES, delta_pct_v1, sensitivity_table
from app.analytics.simulator import (
    COEFFICIENT_PROVENANCE,
    SLIDERS,
    ScenarioParams,
    compare_to_baseline,
    cycles_to_eol,
    default_params,
    degradation_rate,
    soh_at,
    trajectory,
)

FADE = 0.054
BASE = default_params(86.08941987140724)


def scenario(**changes: float) -> ScenarioParams:
    return dataclasses.replace(BASE, **changes)  # type: ignore[arg-type]


def test_default_params_round_soh_like_math_round() -> None:
    assert BASE.start_soh_pct == 86.1
    assert default_params(86.05).start_soh_pct == 86.1  # tie rounds up (Math.round)
    assert (BASE.temp_c, BASE.c_rate, BASE.dod_pct, BASE.horizon_cycles, BASE.eol_pct) == (
        25.0,
        1.0,
        80.0,
        600,
        80.0,
    )


def test_legacy_key_round_trip() -> None:
    legacy = BASE.to_legacy()
    assert legacy == {"T": 25.0, "C": 1.0, "D": 80.0, "N": 600, "S": 86.1, "E": 80.0}
    assert ScenarioParams.from_legacy(legacy) == BASE


@given(st.floats(5, 44), st.floats(0.5, 2.9), st.floats(20, 99))
def test_rate_increases_with_each_stress_factor(t: float, c: float, d: float) -> None:
    p = scenario(temp_c=t, c_rate=c, dod_pct=d)
    rate = degradation_rate(p, FADE)
    assert degradation_rate(scenario(temp_c=t + 1, c_rate=c, dod_pct=d), FADE) > rate
    assert degradation_rate(scenario(temp_c=t, c_rate=c + 0.1, dod_pct=d), FADE) > rate
    assert degradation_rate(scenario(temp_c=t, c_rate=c, dod_pct=d + 1), FADE) > rate


@given(st.integers(5, 44))
def test_hotter_never_lasts_longer(t: int) -> None:
    a = cycles_to_eol(scenario(temp_c=float(t)), FADE)
    b = cycles_to_eol(scenario(temp_c=float(t + 1)), FADE)
    assert a is not None and b is not None and b <= a


def test_baseline_rate_equals_base_fade_and_soh_starts_at_s() -> None:
    assert degradation_rate(BASE, FADE) == FADE
    assert soh_at(BASE, 0, FADE) == BASE.start_soh_pct
    assert len(trajectory(BASE, FADE)) == 601


def test_eol_edge_cases() -> None:
    assert cycles_to_eol(scenario(start_soh_pct=70.0), FADE) == 0
    gentle = scenario(temp_c=-20.0, c_rate=0.5, dod_pct=20.0, start_soh_pct=100.0, eol_pct=60.0)
    assert cycles_to_eol(gentle, FADE) is None


def test_comparison_edge_cases() -> None:
    same = compare_to_baseline(BASE, FADE)
    assert (same.delta_cycles, same.delta_pct) == (0, 0.0)
    assert same.provenance == "simulated"
    below = compare_to_baseline(scenario(start_soh_pct=70.0), FADE)
    assert below.delta_cycles == 0 and below.delta_pct is not None and math.isnan(below.delta_pct)
    beyond = compare_to_baseline(
        scenario(temp_c=-20.0, c_rate=0.5, dod_pct=20.0, start_soh_pct=100.0, eol_pct=60.0), FADE
    )
    assert beyond.cycles_to_eol is None and beyond.delta_cycles is None and beyond.delta_pct is None


def test_sliders_and_coefficient_provenance() -> None:
    assert [s.key for s in SLIDERS] == ["T", "C", "D", "N", "S", "E"]
    assert all(s.min < s.max and s.step > 0 for s in SLIDERS)
    assert COEFFICIENT_PROVENANCE["base_fade"] == "fitted"
    assert {v for k, v in COEFFICIENT_PROVENANCE.items() if k != "base_fade"} == {"assumed"}


@pytest.mark.parametrize(
    ("n", "b", "expected"), [(120, 100, 20.0), (80, 100, -20.0), (None, 100, 0.0), (0, 0, 0.0)]
)
def test_advisor_delta_v1(n: int | None, b: int | None, expected: float) -> None:
    assert delta_pct_v1(n, b) == expected


def test_advisor_table_directions() -> None:
    table = sensitivity_table(BASE, FADE)
    assert len(table.rows) == len(ADVISOR_CHANGES) == 6
    by_label = {r.change.label: r.delta_pct for r in table.rows}
    assert by_label["Cooler: 15 °C"] > 0 > by_label["Warmer: 35 °C"]
    assert by_label["Gentler charge: 0.5C"] > 0 > by_label["Fast charge: 2C"]
    assert by_label["Shallower cycles: 60% DoD"] > 0 > by_label["Full-depth cycles: 100% DoD"]
    assert table.provenance == "simulated"
