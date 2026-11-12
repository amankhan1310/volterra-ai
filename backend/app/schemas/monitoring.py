"""Responses for anomaly detection and the digital twin (v1)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.analytics.anomalies import ChannelKey, Severity
from app.analytics.display import HealthLevel
from app.analytics.twin import TemperatureBand
from app.schemas.analysis import AnomalyCounts
from app.schemas.common import AnalysisContext, ApiModel, Quantity


class DetectorOut(ApiModel):
    name: str
    version: str
    mode: str = Field(description="'retrospective': uses past and future cycles (see F7).")


class AnomalyMethodOut(ApiModel):
    z_scale: float
    flag_threshold_abs_z: float
    high_severity_abs_z: float
    mad_floor: float
    residual_half_window: int


class AnomalyEventOut(ApiModel):
    cycle: int
    channel: ChannelKey
    type: str
    value: float
    unit: str
    expected_low: float
    expected_high: float
    z: float
    severity: Severity


class ChannelStatsOut(ApiModel):
    channel: ChannelKey
    label: str
    unit: str
    median: float
    mad: float
    expected_low: float
    expected_high: float
    values: list[float] = Field(description="Detector input (soh: residual vs rolling median).")
    z: list[float]


class AnomaliesResponse(ApiModel):
    context: AnalysisContext
    detector: DetectorOut
    method: AnomalyMethodOut
    summary: AnomalyCounts
    events: list[AnomalyEventOut]
    channels: list[ChannelStatsOut] | None = Field(
        default=None, description="Per-cycle statistics; only with include_scores=true."
    )
    known_issues: list[str] = Field(
        description="Documented v1 defects affecting these results (ARCHITECTURE_PLAN §3.6)."
    )
    provenance: Literal["fitted"] = "fitted"


class TwinPack(ApiModel):
    soh: Quantity
    capacity: Quantity
    temperature: Quantity
    voltage: Quantity


class TwinModules(ApiModel):
    count: int
    illustrative: Literal[True] = True
    note: str


class TwinResponse(ApiModel):
    context: AnalysisContext
    cycle: int
    last_cycle: int
    pack: TwinPack
    health_level: HealthLevel
    temperature_band: TemperatureBand
    modules: TwinModules
