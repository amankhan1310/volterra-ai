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
    # A gradual rise (no level shift): loss, retention and trend are withheld, not
    # presented as recovery.
    rising = run([1.6 + 0.002 * i for i in range(30)])
    assert rising.level_shifts == ()
    assert rising.start_to_end_withheld is True
    assert rising.retention_pct is None and rising.capacity_loss_ah is None
    assert rising.initial_capacity_ah is not None  # still a measured value, no level shift
    assert rising.trend is None  # a rising line is not reported as a degradation trend
    assert any("Capacity rises" in m for m in rising.limitations)
    assert any("not evidence of battery recovery" in m for m in rising.limitations)
    noise = (0.12, -0.12, -0.12, 0.12)  # balanced: uncorrelated with the cycle number
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


# --- Data-quality regressions (shapes of real cells; exact real values: *_realdata.py) -----------


def b0041_like() -> list[float]:
    """~40 abnormal 0.05 Ah discharges, then a jump to ~1.2 Ah that fades to ~0.85 Ah."""
    return [0.05] * 40 + [1.22 - 0.015 * i for i in range(25)]


def test_upward_level_shift_withholds_start_figures_and_claims_no_recovery() -> None:
    caps = b0041_like()
    view = run(caps)
    assert len(view.level_shifts) == 1
    shift = view.level_shifts[0]
    assert shift.cycle == 40 and shift.before_ah == pytest.approx(0.05)
    assert shift.after_ah == pytest.approx(statistics.median(caps[40:45]))
    assert view.start_to_end_withheld is True
    assert view.initial_capacity_ah is None and view.initial_soh_pct is None
    assert view.capacity_loss_ah is None and view.retention_pct is None
    assert view.trend is None and view.eol_cycle_observed is None
    assert view.starts_below_eol is None
    # The measured end state stays, unchanged.
    assert view.final_capacity_ah == pytest.approx(statistics.median(caps[-5:]))
    assert view.final_soh_pct == pytest.approx(statistics.median(caps[-5:]) / REF * 100)
    text = " ".join(view.limitations)
    assert "shifts abruptly" in text and "cycle 40" in text
    assert "not evidence of battery recovery" in text
    assert "recovered" not in text


def test_downward_level_shift_is_not_called_degradation_either() -> None:
    view = run([1.36] * 12 + [0.30 - 0.001 * i for i in range(10)])
    assert [s.cycle for s in view.level_shifts] == [12]
    assert view.retention_pct is None and view.initial_capacity_ah is None
    assert any("not, on its own, evidence of degradation" in m for m in view.limitations)


def test_single_abnormal_cycles_and_rest_recovery_are_not_level_shifts() -> None:
    caps = linear(80)
    caps[30] = 0.1  # one aborted discharge
    caps[50] += 0.07  # recovery after a rest (NASA B0005 size)
    view = run(caps)
    assert view.level_shifts == () and view.start_to_end_withheld is False


def cs2_33_like() -> list[float]:
    """Slow fade, then an accelerating collapse (the CALCE CS2 shape)."""
    return [1.16 - 0.0004 * i for i in range(600)] + [0.92 - 0.0034 * i for i in range(250)]


def test_curved_fade_warns_that_the_line_end_is_not_the_measured_final_capacity() -> None:
    caps = cs2_33_like()
    view = capacity_degradation(
        [CapacityPoint(i, c) for i, c in enumerate(caps)],
        reference="rated_capacity",
        reference_capacity_ah=1.1,
        eol_pct=80.0,
    )
    assert view.trend is not None and view.level_shifts == ()
    measured_final = statistics.median(caps[-5:])
    assert view.final_capacity_ah == pytest.approx(measured_final)
    assert abs(view.trend.end_capacity_ah - measured_final) > 0.05 * 1.1
    gap = [m for m in view.limitations if "fitted straight line ends at" in m]
    assert len(gap) == 1
    assert f"{view.trend.end_capacity_ah:.3f} Ah" in gap[0]
    assert f"{measured_final:.3f} Ah" in gap[0]
    # Measured figures are unaffected by the warning.
    assert view.initial_capacity_ah is not None
    assert view.retention_pct == pytest.approx(measured_final / view.initial_capacity_ah * 100)


def test_b0005_like_linear_fade_is_unchanged() -> None:
    caps = [1.85 - 0.0035 * i + (0.01 if i % 7 == 0 else 0.0) for i in range(168)]
    view = run(caps)
    assert view.level_shifts == () and view.start_to_end_withheld is False
    assert view.trend is not None
    assert not any("fitted straight line ends at" in m for m in view.limitations)
    assert view.limitations == ()
    assert view.retention_pct == pytest.approx(
        statistics.median(caps[-5:]) / statistics.median(caps[:5]) * 100
    )
