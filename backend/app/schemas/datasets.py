"""Dataset, battery and cycle responses."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field

from app.schemas.common import AnalysisContext, ApiModel, DataProvenance, Quantity


class DatasetOut(ApiModel):
    """Public dataset description. Internal metadata (e.g. synthetic ground truth) is omitted."""

    slug: str
    name: str
    source: str
    version: str
    licence: str | None
    citation: str | None
    description: str | None
    status: str
    checksum: str | None
    synthetic: bool
    battery_count: int


class DatasetList(ApiModel):
    items: list[DatasetOut]


class AnalysisAvailability(ApiModel):
    """Whether the v1/v2 analytics (overview, anomalies, simulator, advisor) can run."""

    available: bool
    reason: Literal["missing_measurement", "insufficient_data"] | None = Field(
        description="Error code the analysis endpoints return (422) when unavailable."
    )
    message: str | None
    min_cycles: int = Field(description="Cycles the analytics need.")


class BatteryFlag(ApiModel):
    """A battery-level note from the source (e.g. the paper excluded this cell)."""

    code: str
    detail: str


class BatteryOut(ApiModel):
    id: uuid.UUID
    external_id: str
    dataset: str
    dataset_name: str
    chemistry: str | None
    form_factor: str | None
    nominal_capacity_ah: float
    nominal_voltage_v: float | None
    eol_threshold_pct: float
    is_synthetic: bool
    data_provenance: DataProvenance
    cycle_count: int
    incomplete_cycle_count: int = Field(
        description="Cycles without a temperature or voltage measurement (null, never filled in)."
    )
    flagged_cycle_count: int = Field(description="Cycles with at least one data-quality flag.")
    flags: list[BatteryFlag]
    analysis: AnalysisAvailability


class BatteryList(ApiModel):
    items: list[BatteryOut]


class CycleOut(ApiModel):
    cycle: int
    capacity_ah: float
    soh_pct: float
    temp_c: float | None = Field(description="Mean cycle temperature; null if not measured.")
    voltage_v: float | None = Field(description="Mean cycle voltage; null if not measured.")
    internal_resistance_ohm: float | None = Field(description="As reported by the source.")
    charge_time_s: float | None = Field(description="Charge duration, if the source has it.")
    quality_flags: list[str] = Field(description="Data-quality flags of this cycle (if any).")


class CyclesResponse(ApiModel):
    context: AnalysisContext
    provenance: DataProvenance
    units: dict[str, str]
    items: list[CycleOut]


class SampleOut(ApiModel):
    position: int = Field(description="Index of this sample in the full, time-ordered series.")
    time_s: float | None
    voltage_v: float | None
    current_a: float | None
    temp_c: float | None


class CycleSamplesResponse(ApiModel):
    """Measured samples of one cycle, deterministically downsampled for charts (decision E)."""

    context: AnalysisContext
    provenance: DataProvenance
    cycle: int
    cycle_types: list[str] = Field(description="Operations in the samples (charge, discharge).")
    total_samples: int = Field(description="Samples in the source before downsampling.")
    returned_samples: int
    downsampled: bool
    units: dict[str, str]
    items: list[SampleOut]


class SohReferenceOut(ApiModel):
    """The capacity SOH is measured against."""

    basis: str = Field(
        description="`rated_capacity` (stated by the source) or `nominal_capacity` (synthetic)."
    )
    capacity_ah: float
    description: str


class LevelShiftOut(ApiModel):
    """A sustained jump in measured capacity (medians of 5 cycles before and after)."""

    cycle: int
    before: Quantity
    after: Quantity


class CapacityTrendOut(ApiModel):
    """Least-squares line of capacity against cycle over the usable cycles (never extrapolated)."""

    cycles: int
    slope: Quantity
    slope_se_ah_per_cycle: float | None
    fade: Quantity = Field(description="SOH points lost per 100 cycles; null without a reference.")
    r2: float | None
    start_cycle: int
    end_cycle: int
    start_capacity: Quantity
    end_capacity: Quantity


class CapacityDegradationResponse(ApiModel):
    """Capacity degradation and SOH from the measured discharge capacity alone.

    Needs neither temperature nor the 221 cycles of the full analytics; states what it cannot
    support in `limitations`.
    """

    context: AnalysisContext
    provenance: DataProvenance
    stored_cycles: int
    usable_cycles: int
    excluded_cycles: int = Field(description="Cycles flagged as incomplete discharges.")
    excluded_flags: list[str]
    first_cycle: int | None
    last_cycle: int | None
    initial_capacity: Quantity = Field(description="Median of the first 5 usable cycles.")
    final_capacity: Quantity = Field(description="Median of the last 5 usable cycles.")
    capacity_loss: Quantity
    retention: Quantity = Field(description="Final over initial capacity.")
    reference: SohReferenceOut | None = Field(description="Null: no stated reference, no SOH.")
    initial_soh: Quantity
    final_soh: Quantity
    latest_soh: Quantity = Field(description="SOH of the last usable cycle.")
    starts_below_eol: bool | None
    eol_cycle_observed: int | None = Field(
        description="First cycle at or below the EOL threshold, confirmed by the next 5 cycles."
    )
    trend: CapacityTrendOut | None
    level_shifts: list[LevelShiftOut] = Field(
        description="Sustained jumps between parts of the recording; with any, the start-to-end "
        "figures, trend and end of life are withheld."
    )
    start_to_end_withheld: bool = Field(
        description="Loss and retention (and, with a level shift, initial capacity and SOH at "
        "start) are null because the recording is not one continuous fade."
    )
    full_analytics: AnalysisAvailability
    limitations: list[str]
