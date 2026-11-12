"""Anomaly detection and digital twin (v1)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.analytics.health import DEFAULT_EOL_PCT
from app.api.deps import get_analysis_service, get_repository
from app.core.errors import ApiError, error_responses
from app.db.repositories import Repository
from app.schemas.monitoring import AnomaliesResponse, TwinResponse
from app.services import mappers
from app.services.analysis import AnalysisService

router = APIRouter(prefix="/batteries/{battery_id}", tags=["monitoring"])

RepoDep = Annotated[Repository, Depends(get_repository)]
ServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]


@router.get(
    "/anomalies",
    response_model=AnomaliesResponse,
    responses=error_responses(404, 422),
    summary="Robust z-score anomaly events (v1; see known_issues)",
)
async def get_anomalies(
    battery_id: uuid.UUID,
    repo: RepoDep,
    service: ServiceDep,
    include_scores: Annotated[
        bool, Query(description="Include per-cycle detector inputs and z-scores.")
    ] = False,
) -> AnomaliesResponse:
    analysis = await service.analyze(repo, battery_id, DEFAULT_EOL_PCT)
    return mappers.anomalies_response(analysis, include_scores)


@router.get(
    "/twin",
    response_model=TwinResponse,
    responses=error_responses(404, 422),
    summary="Pack state at a cycle (module values are illustrative)",
)
async def get_twin(
    battery_id: uuid.UUID,
    repo: RepoDep,
    service: ServiceDep,
    cycle: Annotated[int | None, Query(ge=0, description="Cycle to show; default latest.")] = None,
) -> TwinResponse:
    battery = await service.battery(repo, battery_id)
    records = await repo.load_records(battery_id)
    if not records:
        raise ApiError(422, "insufficient_data", "The battery has no cycle data")
    by_cycle = {r.cycle: r for r in records}
    last = records[-1]
    record = last if cycle is None else by_cycle.get(cycle)
    if record is None:
        raise ApiError(
            422, "cycle_out_of_range", f"Cycle {cycle} not found (cycles 0..{last.cycle})"
        )
    return mappers.twin_response(battery, record, last.cycle)
