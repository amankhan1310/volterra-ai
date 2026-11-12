"""Responses for the Overview analytics: summary, forecast, backtest and insights (v1)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.analytics.display import HealthLevel
from app.analytics.insights import InsightKind
from app.schemas.common import AnalysisContext, ApiModel, DataProvenance, Interval, Quantity

#: Allowed end-of-life thresholds (the prototype's EOL slider range).
EOL_MIN_PCT = 60.0
EOL_MAX_PCT = 90.0


class LinearFitOut(ApiModel):
    slope: float
    intercept: float
    residual_sd: float
    slope_se: float


class TrendOut(LinearFitOut):
    fit_from_cycle: int
    fit_to_cycle: int
    provenance: Literal["fitted"] = "fitted"


class LatestCycle(ApiModel):
    cycle: int
    capacity: Quantity
    temperature: Quantity
    voltage: Quantity


class AnomalyCounts(ApiModel):
    total: int
    high: int
    medium: int


class AccelerationOut(ApiModel):
    accelerated: bool = Field(description="Recent fade exceeds 1.2x the first-half fade.")
    note: str = Field(description="Sentence appended to the Overview text ('' if none).")
    provenance: Literal["fitted"] = "fitted"


class SummaryResponse(ApiModel):
    context: AnalysisContext
    soh_now: Quantity
    observed_last_soh: Quantity
    fade_rate: Quantity
    rul: Interval
    health_level: HealthLevel
    condition: str
    life_used_fraction: Quantity
    cycle_count: int
    latest: LatestCycle
    anomalies: AnomalyCounts
    acceleration: AccelerationOut
    trend: TrendOut


class SeriesOut(ApiModel):
    cycles: list[int]
    values: list[float]
    unit: str
    provenance: DataProvenance | Literal["fitted", "predicted"]


class ForecastResponse(ApiModel):
    context: AnalysisContext
    observed: SeriesOut
    forecast: SeriesOut
    method: str = Field(description="v1: straight line through the most recent 120 cycles.")
    extent_cycles: int = Field(description="Number of cycle positions on the timeline.")
    prediction_boundary_cycle: int = Field(description="Last observed cycle; forecast starts here.")


class CycleWindow(ApiModel):
    from_cycle: int
    to_cycle: int


class BacktestPointOut(ApiModel):
    cycle: int
    observed_soh_pct: float
    predicted_soh_pct: float
    abs_error: float


class BacktestResponse(ApiModel):
    context: AnalysisContext
    train: CycleWindow
    test: CycleWindow
    fit: LinearFitOut
    points: list[BacktestPointOut]
    mae: Quantity
    provenance: Literal["fitted"] = "fitted"


class InsightOut(ApiModel):
    kind: InsightKind
    text: str
    values: dict[str, float | int]
    provenance: Literal["fitted"] = "fitted"


class InsightsResponse(ApiModel):
    context: AnalysisContext
    insights: list[InsightOut]
    acceleration: AccelerationOut
