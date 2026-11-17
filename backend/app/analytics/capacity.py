"""Capacity degradation and SOH from measured discharge capacity only.

The full analytics (``legacy_v1``) need temperature, voltage and at least 221 cycles, which the
CALCE cells (no temperature channel) and every NASA cell (at most 197 cycles) do not have. This
view needs neither: it summarises what the measured discharge capacity itself shows, and states
what it cannot support.

Rules (documented in ``docs/datasets/capacity-soh.md``):

* **SOH reference.** ``SOH = capacity / reference x 100`` with the battery's stated reference
  (``rated_capacity`` from the source documentation). No stated reference means no SOH: the
  first measured capacity is never used in its place (NASA cells start as low as 0.06 Ah).
* **Usable cycles.** Every stored cycle except those flagged as incomplete discharges
  (:data:`EXCLUDED_FLAGS`); nothing is filled in or smoothed.
* **Initial and final capacity.** Median of the first / last :data:`EDGE_WINDOW` usable cycles,
  so one abnormal cycle at either end does not decide retention and loss.
* **Trend.** Least-squares line of capacity against cycle over all usable cycles, only with at
  least :data:`MIN_TREND_CYCLES` of them. It describes the recorded cycles; it is never
  extrapolated to an end of life.
* **Level shifts.** A sustained jump between parts of the recording (5-cycle medians before and
  after differ by more than :data:`LEVEL_SHIFT_FRACTION` of the rated capacity) means the
  recording is not one continuous fade: initial capacity, SOH at start, loss, retention, trend
  and end of life are withheld; final capacity and current SOH (measured) stay.
* **No recovery claims.** A final capacity above the initial one withholds loss and retention; a
  rising fitted line withholds the trend. Neither is presented as battery recovery.
* **Warnings.** An R² below :data:`LOW_R2`, and a fitted line whose end differs from the measured
  final capacity by more than :data:`LINE_GAP_FRACTION` of the rated capacity (non-linear fade),
  are stated in ``limitations``.
* **End of life.** Observed only: the first usable cycle with SOH at or below the threshold whose
  forward :data:`EOL_CONFIRM_WINDOW`-cycle median is also at or below it (the Phase 7 rule);
  none when the recording already starts at or below the threshold.

Standard library only; sums go through :mod:`app.analytics.jsmath`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from app.analytics.jsmath import js_div, reduce_add
from app.analytics.stats import lin, median

#: Cycle flags that mark an incomplete discharge: the capacity is not the cell's capacity.
EXCLUDED_FLAGS: tuple[str, ...] = ("capacity_zero", "file_ends_during_discharge")
EDGE_WINDOW = 5
MIN_TREND_CYCLES = 10
EOL_CONFIRM_WINDOW = 5
#: Below this R² the fade rate is reported as indicative only.
LOW_R2 = 0.5
#: A sustained level shift: the medians of the EDGE_WINDOW cycles before and after a cycle differ
#: by more than this fraction of the rated capacity (NASA 0.5 Ah, CALCE 0.275 / 0.3375 Ah). Single
#: abnormal cycles and recovery after rest (NASA B0005: about 0.07 Ah) stay well below it.
LEVEL_SHIFT_FRACTION = 0.25
#: The fitted line's end and the measured final capacity differ by more than this fraction of the
#: rated capacity: the fade is not linear and the line must not be read as the current state.
LINE_GAP_FRACTION = 0.05


@dataclass(frozen=True)
class CapacityPoint:
    cycle: int
    capacity_ah: float
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapacityTrend:
    """Least-squares line over the usable cycles (``fitted``), never extrapolated."""

    cycles: int
    slope_ah_per_cycle: float
    slope_se_ah_per_cycle: float | None
    #: Slope as SOH percentage points per 100 cycles; null without a reference.
    fade_pct_per_100_cycles: float | None
    r2: float | None
    start_cycle: int
    end_cycle: int
    start_capacity_ah: float
    end_capacity_ah: float


@dataclass(frozen=True)
class LevelShift:
    """A sustained jump in measured capacity between two parts of the recording."""

    cycle: int
    before_ah: float
    after_ah: float


@dataclass(frozen=True)
class CapacityDegradation:
    stored_cycles: int
    usable_cycles: int
    excluded_cycles: int
    first_cycle: int | None
    last_cycle: int | None
    initial_capacity_ah: float | None
    final_capacity_ah: float | None
    capacity_loss_ah: float | None
    retention_pct: float | None
    reference: str | None
    reference_capacity_ah: float | None
    initial_soh_pct: float | None
    final_soh_pct: float | None
    latest_soh_pct: float | None
    eol_pct: float
    starts_below_eol: bool | None
    eol_cycle_observed: int | None
    trend: CapacityTrend | None
    limitations: tuple[str, ...]
    level_shifts: tuple[LevelShift, ...] = ()
    #: Start-to-end figures (loss, retention; with a level shift also initial capacity and SOH
    #: at start) were withheld.
    start_to_end_withheld: bool = False


def soh_pct(capacity_ah: float, reference_capacity_ah: float) -> float:
    return capacity_ah / reference_capacity_ah * 100


def _fit(points: Sequence[CapacityPoint], reference_ah: float | None) -> CapacityTrend:
    xs = [float(p.cycle) for p in points]
    ys = [p.capacity_ah for p in points]
    fit = lin(xs, ys)
    mean_y = reduce_add(ys) / len(ys)
    ss_tot = 0.0
    ss_res = 0.0
    for x, y in zip(xs, ys, strict=True):
        ss_tot += (y - mean_y) * (y - mean_y)
        r = y - fit.predict(x)
        ss_res += r * r
    r2 = None if ss_tot == 0 else 1 - js_div(ss_res, ss_tot)
    se = fit.slope_se if math.isfinite(fit.slope_se) else None
    fade = None if reference_ah is None else -fit.slope / reference_ah * 100 * 100
    return CapacityTrend(
        cycles=len(points),
        slope_ah_per_cycle=fit.slope,
        slope_se_ah_per_cycle=se,
        fade_pct_per_100_cycles=fade,
        r2=r2,
        start_cycle=points[0].cycle,
        end_cycle=points[-1].cycle,
        start_capacity_ah=fit.predict(xs[0]),
        end_capacity_ah=fit.predict(xs[-1]),
    )


def _level_shifts(points: Sequence[CapacityPoint], scale_ah: float) -> list[LevelShift]:
    """Sustained jumps: 5-cycle medians before and after differ by > LEVEL_SHIFT_FRACTION.

    Neighbouring candidate cycles belong to one jump, placed at the largest single-cycle step
    among them (the boundary itself; the median difference breaks ties).
    """
    caps = [p.capacity_ah for p in points]
    threshold = LEVEL_SHIFT_FRACTION * scale_ah
    shifts: list[LevelShift] = []
    best: LevelShift | None = None
    best_key = (0.0, 0.0)
    last_i = -2
    for i in range(EDGE_WINDOW, len(caps) - EDGE_WINDOW + 1):
        before = median(caps[i - EDGE_WINDOW : i])
        after = median(caps[i : i + EDGE_WINDOW])
        if abs(after - before) <= threshold:
            continue
        candidate = LevelShift(points[i].cycle, before, after)
        key = (abs(caps[i] - caps[i - 1]), abs(after - before))
        if best is not None and i == last_i + 1:
            if key > best_key:
                best, best_key = candidate, key
        else:
            if best is not None:
                shifts.append(best)
            best, best_key = candidate, key
        last_i = i
    if best is not None:
        shifts.append(best)
    return shifts


def _eol_observed(sohs: Sequence[float], cycles: Sequence[int], eol_pct: float) -> int | None:
    for i, value in enumerate(sohs):
        if value <= eol_pct and median(sohs[i : i + EOL_CONFIRM_WINDOW]) <= eol_pct:
            return cycles[i]
    return None


def capacity_degradation(
    points: Sequence[CapacityPoint],
    *,
    reference: str | None,
    reference_capacity_ah: float | None,
    eol_pct: float,
) -> CapacityDegradation:
    """Summarise the measured capacity of one battery (``points`` in any order)."""
    ordered = sorted(points, key=lambda p: p.cycle)
    usable = [p for p in ordered if not any(f in EXCLUDED_FLAGS for f in p.quality_flags)]
    excluded = len(ordered) - len(usable)
    has_reference = reference_capacity_ah is not None and reference_capacity_ah > 0
    ref = reference_capacity_ah if has_reference else None
    limitations: list[str] = []
    if excluded:
        limitations.append(
            f"{excluded} cycles flagged as incomplete discharges ({', '.join(EXCLUDED_FLAGS)}) "
            "are left out of these figures; they stay visible in the per-cycle data"
        )
    if ref is None:
        limitations.append(
            "SOH is unavailable: the source states no rated capacity for this battery, and the "
            "first measured capacity is not used in its place"
        )
    if not usable:
        limitations.append("No usable measured capacity: nothing can be summarised")
        return CapacityDegradation(
            stored_cycles=len(ordered),
            usable_cycles=0,
            excluded_cycles=excluded,
            first_cycle=None,
            last_cycle=None,
            initial_capacity_ah=None,
            final_capacity_ah=None,
            capacity_loss_ah=None,
            retention_pct=None,
            reference=reference if ref is not None else None,
            reference_capacity_ah=ref,
            initial_soh_pct=None,
            final_soh_pct=None,
            latest_soh_pct=None,
            eol_pct=eol_pct,
            starts_below_eol=None,
            eol_cycle_observed=None,
            trend=None,
            limitations=tuple(limitations),
        )

    caps = [p.capacity_ah for p in usable]
    initial = median(caps[:EDGE_WINDOW])
    final = median(caps[-EDGE_WINDOW:])
    shifts = _level_shifts(usable, ref if ref is not None else median(caps))
    # Start-to-end figures only describe degradation when the recording is one continuous fade.
    withhold = bool(shifts) or final > initial
    if shifts:
        jumps = "; ".join(
            f"cycle {s.cycle}: {s.before_ah:.3f} → {s.after_ah:.3f} Ah" for s in shifts
        )
        limitations.append(
            f"Measured capacity shifts abruptly ({jumps}; medians of {EDGE_WINDOW} cycles before "
            "and after). Parts of the recording differ in test conditions or contain abnormal "
            "discharges, so the start-to-end figures (initial capacity, SOH at start, loss, "
            "retention), the trend and the end of life are withheld. "
            + (
                "An upward jump is not evidence of battery recovery. "
                if any(s.after_ah > s.before_ah for s in shifts)
                else "A sudden drop is not, on its own, evidence of degradation. "
            )
            + "Final capacity and current SOH are the measured values of the last cycles; every "
            "measurement stays in the per-cycle data"
        )
    elif withhold:
        limitations.append(
            f"The final capacity ({final:.3f} Ah) is higher than the initial one "
            f"({initial:.3f} Ah), so loss and retention are withheld. This is not evidence of "
            "battery recovery: the first cycles may be incomplete or abnormal discharges, or "
            "capacity recovers temporarily after rest"
        )
    if len(usable) < 2 * EDGE_WINDOW:
        limitations.append(
            f"Only {len(usable)} usable cycles: the initial and final capacities (medians of "
            f"the first and last {EDGE_WINDOW}) overlap, so retention and loss are indicative"
        )
    trend = None
    if shifts:
        pass  # a line across a level shift describes neither part of the recording
    elif len(usable) >= MIN_TREND_CYCLES:
        trend = _fit(usable, ref)
        if trend.slope_ah_per_cycle > 0:
            # A rising line is not a degradation trend: it is withheld, not reported.
            trend = None
            limitations.append(
                "Capacity rises over the recorded cycles, so no degradation trend is reported "
                "and the rise is not treated as battery recovery (early cycles may be incomplete "
                "or abnormal discharges); check the per-cycle data"
            )
        else:
            if trend.r2 is not None and trend.r2 < LOW_R2:
                limitations.append(
                    f"The straight line explains only {trend.r2:.2f} of the capacity variation "
                    "(R²): treat the fade rate as indicative"
                )
            gap_scale = ref if ref is not None else initial
            if abs(trend.end_capacity_ah - final) > LINE_GAP_FRACTION * gap_scale:
                limitations.append(
                    f"The fitted straight line ends at {trend.end_capacity_ah:.3f} Ah, but the "
                    f"measured final capacity is {final:.3f} Ah: the capacity does not fall "
                    "along a straight line (the fade changes pace), so the line averages the "
                    "whole recording and does not describe the latest cycles. Use the measured "
                    "values for the current state"
                )
    else:
        limitations.append(
            f"A degradation trend needs at least {MIN_TREND_CYCLES} usable cycles; this battery "
            f"has {len(usable)}"
        )

    initial_soh = final_soh = latest_soh = None
    starts_below = None
    eol_cycle = None
    if ref is not None:
        initial_soh = None if shifts else soh_pct(initial, ref)
        final_soh = soh_pct(final, ref)
        latest_soh = soh_pct(caps[-1], ref)
        sohs = [soh_pct(c, ref) for c in caps]
        if not shifts:
            starts_below = soh_pct(initial, ref) <= eol_pct
            if starts_below:
                limitations.append(
                    f"The recording starts at or below {eol_pct:g} % SOH of the rated capacity: "
                    "the cell was already aged (or tested under conditions that lower its "
                    "capacity), so no end-of-life crossing can be observed"
                )
            else:
                eol_cycle = _eol_observed(sohs, [p.cycle for p in usable], eol_pct)

    return CapacityDegradation(
        stored_cycles=len(ordered),
        usable_cycles=len(usable),
        excluded_cycles=excluded,
        first_cycle=usable[0].cycle,
        last_cycle=usable[-1].cycle,
        initial_capacity_ah=None if shifts else initial,
        final_capacity_ah=final,
        capacity_loss_ah=None if withhold else initial - final,
        retention_pct=None if withhold or initial <= 0 else final / initial * 100,
        reference=reference if ref is not None else None,
        reference_capacity_ah=ref,
        initial_soh_pct=initial_soh,
        final_soh_pct=final_soh,
        latest_soh_pct=latest_soh,
        eol_pct=eol_pct,
        starts_below_eol=starts_below,
        eol_cycle_observed=eol_cycle,
        trend=trend,
        limitations=tuple(limitations),
        level_shifts=tuple(shifts),
        start_to_end_withheld=withhold,
    )
