"""Dataset, battery and cycle responses."""

from __future__ import annotations

import uuid

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


class BatteryList(ApiModel):
    items: list[BatteryOut]


class CycleOut(ApiModel):
    cycle: int
    capacity_ah: float
    soh_pct: float
    temp_c: float = Field(description="Mean cycle temperature.")
    voltage_v: float = Field(description="Mean cycle voltage.")


class CyclesResponse(ApiModel):
    context: AnalysisContext
    provenance: DataProvenance
    units: dict[str, str]
    items: list[CycleOut]
