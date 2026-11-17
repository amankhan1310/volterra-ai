"""Capacity degradation view of one battery: picks the SOH reference and runs the analytics.

Reference capacity (``docs/datasets/capacity-soh.md``):

* measured cells: the reference the importer stored from the source documentation
  (``soh_reference = rated_capacity``: NASA 2.0 Ah, CALCE CS2 1.10 Ah / CX2 1.35 Ah, Severson
  1.1 Ah); none stored means no SOH;
* the synthetic cell: its nominal 2.0 Ah, the capacity its generator defines SOH against.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.analytics.capacity import CapacityDegradation, CapacityPoint, capacity_degradation
from app.db.repositories import BatteryInfo, CycleData

SYNTHETIC_REFERENCE = "nominal_capacity"


def reference_of(battery: BatteryInfo) -> tuple[str | None, float | None]:
    if battery.is_synthetic:
        return SYNTHETIC_REFERENCE, battery.nominal_capacity_ah
    return battery.soh_reference, battery.soh_reference_capacity_ah


def capacity_view(battery: BatteryInfo, cycles: Sequence[CycleData]) -> CapacityDegradation:
    reference, reference_ah = reference_of(battery)
    return capacity_degradation(
        [CapacityPoint(c.cycle, c.capacity_ah, c.quality_flags) for c in cycles],
        reference=reference,
        reference_capacity_ah=reference_ah,
        eol_pct=battery.eol_threshold_pct,
    )
