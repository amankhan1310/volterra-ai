"""Overview analytics (v1): summary, forecast, backtest and insights."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.analytics.health import DEFAULT_EOL_PCT
from app.api.deps import get_analysis_service, get_repository
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
    battery_id: uuid.UUID, repo: RepoDep, service: ServiceDep, eol_pct: EolQuery = DEFAULT_EOL_PCT
) -> SummaryResponse:
    return mappers.summary_response(await service.analyze(repo, battery_id, eol_pct))


@router.get(
    "/forecast",
    response_model=ForecastResponse,
    responses=ERRORS,
    summary="Observed SOH and the v1 linear forecast",
)
async def get_forecast(
    battery_id: uuid.UUID, repo: RepoDep, service: ServiceDep, eol_pct: EolQuery = DEFAULT_EOL_PCT
) -> ForecastResponse:
    return mappers.forecast_response(await service.analyze(repo, battery_id, eol_pct))


@router.get(
    "/backtest",
    response_model=BacktestResponse,
    responses=ERRORS,
    summary="Time-ordered hold-out backtest of the linear forecast",
)
async def get_backtest(
    battery_id: uuid.UUID, repo: RepoDep, service: ServiceDep
) -> BacktestResponse:
    return mappers.backtest_response(await service.analyze(repo, battery_id, DEFAULT_EOL_PCT))


@router.get(
    "/insights",
    response_model=InsightsResponse,
    responses=ERRORS,
    summary="Rule-based insights (v1, includes known defect F5)",
)
async def get_insights(
    battery_id: uuid.UUID, repo: RepoDep, service: ServiceDep
) -> InsightsResponse:
    return mappers.insights_response(await service.analyze(repo, battery_id, DEFAULT_EOL_PCT))
