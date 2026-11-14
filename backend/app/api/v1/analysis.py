"""Overview analytics: summary, forecast, backtest and insights (v1; v2 opt-in)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.analytics.health import DEFAULT_EOL_PCT
from app.api.deps import get_analysis_service, get_repository
from app.api.v1.params import AlgorithmQuery
from app.core.errors import error_responses
from app.db.repositories import Repository
from app.schemas.analysis import (
    EOL_MAX_PCT,
    EOL_MIN_PCT,
    BacktestResponse,
    ForecastResponse,
    InsightsResponse,
    SummaryResponse,
)
from app.services import mappers
from app.services.analysis import AnalysisService

router = APIRouter(prefix="/batteries/{battery_id}", tags=["analytics"])
ERRORS = error_responses(404, 422)

RepoDep = Annotated[Repository, Depends(get_repository)]
ServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]
EolQuery = Annotated[
    float,
    Query(
        ge=EOL_MIN_PCT,
        le=EOL_MAX_PCT,
        description="End-of-life SOH threshold in percent (60-90, as in the prototype).",
    ),
]


@router.get(
    "/summary",
    response_model=SummaryResponse,
    responses=ERRORS,
    summary="Overview: SOH, fade, RUL with interval, health and KPIs",
)
async def get_summary(
    battery_id: uuid.UUID,
    repo: RepoDep,
    service: ServiceDep,
    eol_pct: EolQuery = DEFAULT_EOL_PCT,
    algorithm: AlgorithmQuery = "v1",
) -> SummaryResponse:
    if algorithm == "v2":
        return mappers.summary_response_v2(await service.analyze_v2(repo, battery_id, eol_pct))
    return mappers.summary_response(await service.analyze(repo, battery_id, eol_pct))


@router.get(
    "/forecast",
    response_model=ForecastResponse,
    responses=ERRORS,
    summary="Observed SOH and the forecast (v1 linear; v2 interim quadratic)",
)
async def get_forecast(
    battery_id: uuid.UUID,
    repo: RepoDep,
    service: ServiceDep,
    eol_pct: EolQuery = DEFAULT_EOL_PCT,
    algorithm: AlgorithmQuery = "v1",
) -> ForecastResponse:
    if algorithm == "v2":
        return mappers.forecast_response_v2(await service.analyze_v2(repo, battery_id, eol_pct))
    return mappers.forecast_response(await service.analyze(repo, battery_id, eol_pct))


@router.get(
    "/backtest",
    response_model=BacktestResponse,
    responses=ERRORS,
    summary="Time-ordered hold-out backtest of the forecast",
)
async def get_backtest(
    battery_id: uuid.UUID, repo: RepoDep, service: ServiceDep, algorithm: AlgorithmQuery = "v1"
) -> BacktestResponse:
    if algorithm == "v2":
        return mappers.backtest_response_v2(
            await service.analyze_v2(repo, battery_id, DEFAULT_EOL_PCT)
        )
    return mappers.backtest_response(await service.analyze(repo, battery_id, DEFAULT_EOL_PCT))


@router.get(
    "/insights",
    response_model=InsightsResponse,
    responses=ERRORS,
    summary="Rule-based insights (v1 includes known defect F5; fixed in v2)",
)
async def get_insights(
    battery_id: uuid.UUID, repo: RepoDep, service: ServiceDep, algorithm: AlgorithmQuery = "v1"
) -> InsightsResponse:
    if algorithm == "v2":
        return mappers.insights_response_v2(
            await service.analyze_v2(repo, battery_id, DEFAULT_EOL_PCT)
        )
    return mappers.insights_response(await service.analyze(repo, battery_id, DEFAULT_EOL_PCT))
