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
from typing import Any

import numpy as np

VOLTAGE_LOW_V = 1.5
VOLTAGE_HIGH_V = 4.5
TEMP_LOW_C = -20.0
TEMP_HIGH_C = 80.0

Flags = dict[str, str]


def _fmt(x: float) -> str:
    return format(float(x), ".6g")


def _finite(a: Any) -> Any:
    arr = np.asarray(a, dtype=float).ravel()
    return arr[np.isfinite(arr)]


def check_samples(
    time_s: Sequence[float] | Any,
    voltage_v: Sequence[float] | Any,
    current_a: Sequence[float] | Any,
    temp_c: Sequence[float] | Any | None,
) -> Flags:
    """Flags about the per-sample traces of one charge or discharge.

    ``temp_c=None`` means the source has no temperature channel (e.g. CALCE): temperature is
    then neither compared in length nor checked, and is never treated as zero.
    """
    flags: Flags = {}
    series = [time_s, voltage_v, current_a] + ([] if temp_c is None else [temp_c])
    lengths = {len(s) for s in series}
    if len(lengths) != 1:
        flags["unequal_array_lengths"] = "lengths " + ",".join(str(n) for n in sorted(lengths))
    if min(lengths) == 0:
        flags["empty_samples"] = "no samples"
        return flags
    bad = sum(int((~np.isfinite(np.asarray(s, dtype=float))).sum()) for s in series)
    if bad:
        flags["non_finite_values"] = f"{bad} non-finite sample values"
    finite_t = _finite(time_s)
    if finite_t.size > 1 and bool(np.any(np.diff(finite_t) <= 0)):
        flags["time_not_increasing"] = "time vector is not strictly increasing"
    finite_v = _finite(voltage_v)
    if finite_v.size and finite_v.min() < VOLTAGE_LOW_V:
        flags["voltage_below_1_5v"] = f"min {_fmt(finite_v.min())} V"
    if finite_v.size and finite_v.max() > VOLTAGE_HIGH_V:
        flags["voltage_above_4_5v"] = f"max {_fmt(finite_v.max())} V"
    if temp_c is not None:
        finite_temp = _finite(temp_c)
        if finite_temp.size and (finite_temp.min() < TEMP_LOW_C or finite_temp.max() > TEMP_HIGH_C):
            flags["temperature_out_of_range"] = (
                f"range {_fmt(finite_temp.min())}..{_fmt(finite_temp.max())} C"
            )
    return flags


def first_positive_capacity(rows: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """The first canonical cycle whose measured capacity is positive (``first_capacity_ah``).

    Zero and missing capacities are skipped: e.g. every Severson batch-1 cell reports 0 Ah for
    its first cycle, which is not a capacity measurement of the cell.
    """
    return next((r for r in rows if r["capacity_ah"] is not None and r["capacity_ah"] > 0), None)


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
