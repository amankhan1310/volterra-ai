"""Capacity degradation and SOH from measured capacity (app.analytics.capacity)."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping

import pytest

from app.analytics.capacity import (
    EDGE_WINDOW,
    MIN_TREND_CYCLES,
    CapacityDegradation,
    CapacityPoint,
    capacity_degradation,
    soh_pct,
)

REF = 2.0


def run(
    caps: list[float],
    *,
    ref: float | None = REF,
    flags: Mapping[int, tuple[str, ...]] | None = None,
) -> CapacityDegradation:
    flags = flags or {}
    points = [CapacityPoint(i, c, flags.get(i, ())) for i, c in enumerate(caps)]
    return capacity_degradation(
        points,
        reference="rated_capacity" if ref is not None else None,
        reference_capacity_ah=ref,
        eol_pct=80.0,
    )


def linear(n: int, start: float = 1.9, step: float = -0.004) -> list[float]:
    return [start + step * i for i in range(n)]


def test_soh_uses_the_stated_reference_not_the_first_capacity() -> None:
    caps = linear(40, start=1.8)  # first measurement 1.8 Ah, rated 2.0 Ah
    view = run(caps)
    assert view.reference == "rated_capacity" and view.reference_capacity_ah == REF
    assert view.initial_soh_pct == pytest.approx(statistics.median(caps[:5]) / REF * 100)
    assert view.initial_soh_pct == pytest.approx(89.6)  # not 100 %: 1.792 Ah of 2.0 Ah
    assert view.latest_soh_pct == pytest.approx(caps[-1] / REF * 100)
    assert soh_pct(1.1, 1.1) == 100.0


def test_retention_loss_and_trend_against_an_independent_computation() -> None:
    caps = [1.9 - 0.003 * i + (0.002 if i % 3 == 0 else -0.001) for i in range(60)]
    view = run(caps)
    initial = statistics.median(caps[:EDGE_WINDOW])
    final = statistics.median(caps[-EDGE_WINDOW:])
    assert view.initial_capacity_ah == pytest.approx(initial, abs=1e-12)
    assert view.final_capacity_ah == pytest.approx(final, abs=1e-12)
    assert view.capacity_loss_ah == pytest.approx(initial - final, abs=1e-12)
    assert view.retention_pct == pytest.approx(final / initial * 100, abs=1e-9)
    xs = list(range(60))
    mx, my = math.fsum(xs) / 60, math.fsum(caps) / 60
    slope = math.fsum((x - mx) * (y - my) for x, y in zip(xs, caps, strict=True)) / math.fsum(
        (x - mx) ** 2 for x in xs
    )
    assert view.trend is not None
    assert view.trend.slope_ah_per_cycle == pytest.approx(slope, abs=1e-12)
    assert view.trend.fade_pct_per_100_cycles == pytest.approx(-slope / REF * 1e4, abs=1e-9)
    assert view.trend.start_cycle == 0 and view.trend.end_cycle == 59
    assert view.trend.r2 is not None and view.trend.r2 > 0.99
    assert view.limitations == ()


def test_missing_temperature_is_not_an_input() -> None:
    # The analysis takes capacity only: a cell without any temperature channel is analysed.
    view = run(linear(30))
    assert view.final_soh_pct is not None and view.trend is not None


def test_no_reference_means_no_soh_and_says_why() -> None:
    view = run(linear(30), ref=None)
    assert view.reference is None and view.reference_capacity_ah is None
    assert view.initial_soh_pct is None and view.final_soh_pct is None
    assert view.latest_soh_pct is None and view.eol_cycle_observed is None
    assert view.trend is not None and view.trend.fade_pct_per_100_cycles is None
    assert view.retention_pct is not None  # capacity figures still come from the measurements
    assert any("SOH is unavailable" in m for m in view.limitations)


def test_too_few_cycles_for_a_trend_is_a_stated_limitation() -> None:
    view = run(linear(MIN_TREND_CYCLES - 1))
    assert view.trend is None
    assert any(f"at least {MIN_TREND_CYCLES} usable cycles" in m for m in view.limitations)
    assert any("indicative" in m for m in view.limitations)  # edges overlap below 10 cycles
    assert run(linear(MIN_TREND_CYCLES)).trend is not None


def test_incomplete_discharges_are_left_out_never_zero_filled() -> None:
    caps = linear(30)
    caps[29] = 0.0  # a recorded zero (aborted discharge), flagged by the importer
    caps[0] = 0.4  # a partial first discharge
    flags = {29: ("capacity_zero",), 0: ("file_ends_during_discharge",)}
    view = run(caps, flags=flags)
    assert (view.stored_cycles, view.usable_cycles, view.excluded_cycles) == (30, 28, 2)
    assert view.first_cycle == 1 and view.last_cycle == 28
    assert view.final_capacity_ah == pytest.approx(statistics.median(caps[24:29]))
    assert any("incomplete discharges" in m for m in view.limitations)


def test_other_flags_are_real_behaviour_and_stay_in() -> None:
    view = run(linear(30), flags={5: ("capacity_jump_up",), 0: ("capacity_above_rated",)})
    assert view.usable_cycles == 30 and view.excluded_cycles == 0


def test_no_usable_cycle_returns_nothing_invented() -> None:
    view = run([0.0, 0.0], flags={0: ("capacity_zero",), 1: ("capacity_zero",)})
    assert view.usable_cycles == 0 and view.trend is None
    assert view.initial_capacity_ah is None and view.final_soh_pct is None
    assert any("No usable measured capacity" in m for m in view.limitations)
    assert run([]).stored_cycles == 0


def test_end_of_life_is_observed_and_confirmed_never_extrapolated() -> None:
    caps = linear(100, start=1.9, step=-0.005)  # 80 % of 2.0 Ah = 1.6 Ah, reached at cycle 60
    view = run(caps)
    assert view.eol_cycle_observed == 60
    assert view.starts_below_eol is False
    # A single dip below the threshold, not confirmed by the next cycles, is not end of life.
    dip = [1.9] * 20
    dip[10] = 1.5
    assert run(dip).eol_cycle_observed is None
    # Still above the threshold at the end: no end of life, nothing projected.
    assert run(linear(20)).eol_cycle_observed is None


def test_recording_that_starts_below_eol_reports_no_crossing() -> None:
    view = run(linear(30, start=1.2))
    assert view.starts_below_eol is True and view.eol_cycle_observed is None
    assert any("starts at or below 80 % SOH" in m for m in view.limitations)


def test_rising_capacity_and_poor_fit_are_flagged() -> None:
    rising = run([0.06] * 5 + [0.8 + 0.001 * i for i in range(25)])
    assert rising.retention_pct is not None and rising.retention_pct > 100
    assert rising.trend is None  # a rising line is not reported as a degradation trend
    assert any("Capacity rises" in m for m in rising.limitations)
    noise = (0.3, -0.3, -0.3, 0.3)  # balanced: uncorrelated with the cycle number
    noisy = run([1.8 + noise[i % 4] - 0.002 * i for i in range(32)])
    assert noisy.trend is not None and noisy.trend.slope_ah_per_cycle < 0
    assert noisy.trend is not None and noisy.trend.r2 is not None and noisy.trend.r2 < 0.5
    assert any("indicative" in m for m in noisy.limitations)


def test_points_are_ordered_by_cycle() -> None:
    caps = linear(20)
    shuffled = [CapacityPoint(i, c) for i, c in reversed(list(enumerate(caps)))]
    view = capacity_degradation(
        shuffled, reference="rated_capacity", reference_capacity_ah=REF, eol_pct=80.0
    )
    assert view == run(caps)
