"""Anomaly detection (v1; v2 opt-in) and digital twin."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.analytics.health import DEFAULT_EOL_PCT
from app.analytics.synthetic import CycleRecord
from app.api.deps import get_analysis_service, get_repository
from app.api.v1.params import AlgorithmQuery, ModeQuery
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
    summary="Robust z-score anomaly events (v1 default, see known_issues; v2 opt-in)",
)
async def get_anomalies(
    battery_id: uuid.UUID,
    repo: RepoDep,
    service: ServiceDep,
    include_scores: Annotated[
        bool, Query(description="Include per-cycle detector inputs and z-scores.")
    ] = False,
    algorithm: AlgorithmQuery = "v1",
    mode: ModeQuery = "retrospective",
) -> AnomaliesResponse:
    if algorithm == "v2":
        analysis_v2 = await service.analyze_v2(repo, battery_id, DEFAULT_EOL_PCT)
        return mappers.anomalies_response_v2(analysis_v2, include_scores, mode)
    if mode != "retrospective":
        raise ApiError(422, "unsupported_mode", "mode=causal is only available with algorithm=v2")
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
    # Cycle data, not v1 records: a real battery may lack temperature or voltage on some cycles.
    data = await repo.load_cycle_data(battery_id)
    if not data:
        raise ApiError(422, "insufficient_data", "The battery has no cycle data")
    by_cycle = {d.cycle: d for d in data}
    last = data[-1]
    row = last if cycle is None else by_cycle.get(cycle)
    if row is None:
        raise ApiError(
            422,
            "cycle_out_of_range",
            f"Cycle {cycle} not found (cycles {data[0].cycle}..{last.cycle})",
        )
    if row.temp_c is None or row.voltage_v is None:
        raise ApiError(
            422,
            "missing_measurement",
            f"Cycle {row.cycle} has no temperature or voltage measurement; the pack view "
            "needs both and never fills them in",
        )
    record = CycleRecord(row.cycle, row.capacity_ah, row.soh_pct, row.temp_c, row.voltage_v)
    return mappers.twin_response(battery, record, last.cycle)
