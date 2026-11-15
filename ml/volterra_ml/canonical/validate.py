"""Deterministic validation rules for one cycle (Phase 6 M2).

Rules only *flag*; they never drop, clip or replace data. Each flag is a stable code with a
short, deterministic detail string, stored in ``quality_flags_json``. The thresholds below were
chosen after measuring the real NASA data (see docs/datasets/canonical-schema.md):

* NASA discharges end at cut-offs of 2.0-2.7 V, so dips slightly below 2.0 V are normal (583 of
  2,794 discharges); runs going below 1.5 V are failed runs (36) and are flagged.
* Capacity of exactly 0 Ah, capacity above the rated value and empty capacity fields occur in
  the source and are flagged, never corrected.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

VOLTAGE_LOW_V = 1.5
VOLTAGE_HIGH_V = 4.5
TEMP_LOW_C = -20.0
TEMP_HIGH_C = 80.0

Flags = dict[str, str]


def _fmt(x: float) -> str:
    return format(x, ".6g")


def check_samples(
    time_s: Sequence[float],
    voltage_v: Sequence[float],
    current_a: Sequence[float],
    temp_c: Sequence[float],
) -> Flags:
    """Flags about the per-sample traces of one charge or discharge."""
    flags: Flags = {}
    lengths = {len(time_s), len(voltage_v), len(current_a), len(temp_c)}
    if len(lengths) != 1:
        flags["unequal_array_lengths"] = "lengths " + ",".join(str(n) for n in sorted(lengths))
    if min(lengths) == 0:
        flags["empty_samples"] = "no samples"
        return flags
    bad = sum(
        1
        for series in (time_s, voltage_v, current_a, temp_c)
        for x in series
        if not math.isfinite(x)
    )
    if bad:
        flags["non_finite_values"] = f"{bad} non-finite sample values"
    finite_t = [x for x in time_s if math.isfinite(x)]
    if any(b <= a for a, b in zip(finite_t, finite_t[1:], strict=False)):
        flags["time_not_increasing"] = "time vector is not strictly increasing"
    finite_v = [x for x in voltage_v if math.isfinite(x)]
    if finite_v and min(finite_v) < VOLTAGE_LOW_V:
        flags["voltage_below_1_5v"] = f"min {_fmt(min(finite_v))} V"
    if finite_v and max(finite_v) > VOLTAGE_HIGH_V:
        flags["voltage_above_4_5v"] = f"max {_fmt(max(finite_v))} V"
    finite_temp = [x for x in temp_c if math.isfinite(x)]
    if finite_temp and (min(finite_temp) < TEMP_LOW_C or max(finite_temp) > TEMP_HIGH_C):
        flags["temperature_out_of_range"] = (
            f"range {_fmt(min(finite_temp))}..{_fmt(max(finite_temp))} C"
        )
    return flags


#: A capacity rise above this share of the rated capacity between consecutive measured cycles
#: is flagged. On NASA the median change between cycles is about 0.01 Ah; 2.5% of 2.0 Ah
#: (0.05 Ah) marks the clear jumps (100 of 2,716 pairs), e.g. recovery after rest periods.
JUMP_UP_FRACTION = 0.025


def check_capacity_jumps(
    capacities: Sequence[float | None], rated_capacity_ah: float
) -> dict[int, str]:
    """Positions whose capacity exceeds the previous positive measured capacity by more than
    ``JUMP_UP_FRACTION`` of the rated capacity (missing and zero capacities are skipped)."""
    threshold = JUMP_UP_FRACTION * rated_capacity_ah
    out: dict[int, str] = {}
    previous: tuple[int, float] | None = None
    for k, cap in enumerate(capacities):
        if cap is None or not math.isfinite(cap) or cap <= 0:
            continue
        if previous is not None and cap - previous[1] > threshold:
            out[k] = f"+{_fmt(cap - previous[1])} Ah vs cycle {previous[0]}"
        previous = (k, cap)
    return out


def check_capacity(capacity_ah: float | None, rated_capacity_ah: float) -> Flags:
    """Flags about a discharge capacity as reported by the source."""
    if capacity_ah is None:
        return {"capacity_missing": "source capacity field is empty"}
    if not math.isfinite(capacity_ah):
        return {"capacity_missing": "source capacity is not finite"}
    if capacity_ah < 0:
        return {"capacity_negative": f"{_fmt(capacity_ah)} Ah"}
    if capacity_ah == 0:
        return {"capacity_zero": "0 Ah reported"}
    if capacity_ah > rated_capacity_ah:
        return {"capacity_above_rated": f"{_fmt(capacity_ah)} Ah > rated {_fmt(rated_capacity_ah)}"}
    return {}
