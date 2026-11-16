"""Dataset, battery and cycle responses."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field

from app.schemas.common import AnalysisContext, ApiModel, DataProvenance


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
