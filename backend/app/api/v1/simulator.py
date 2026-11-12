"""What-if simulator and Charging Advisor (v1, assumed stress coefficients)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from starlette.concurrency import run_in_threadpool

from app.analytics.health import DEFAULT_EOL_PCT
from app.analytics.simulator import SLIDERS
from app.api.deps import get_analysis_service, get_repository
from app.core.errors import error_responses
from app.db.repositories import Repository
from app.schemas.analysis import EOL_MAX_PCT, EOL_MIN_PCT
from app.schemas.simulator import (
    AdvisorResponse,
    SimulateRequest,
    SimulateResponse,
    SimulatorConfigResponse,
)
from app.services import mappers
from app.services.analysis import AnalysisService
from app.services.simulation import advisor_table, simulate

router = APIRouter(prefix="/batteries/{battery_id}", tags=["simulator"])
ERRORS = error_responses(404, 422)
START_SOH = next(s for s in SLIDERS if s.key == "S")

RepoDep = Annotated[Repository, Depends(get_repository)]
ServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]


@router.get(
    "/simulator",
    response_model=SimulatorConfigResponse,
    responses=ERRORS,
    summary="Simulator defaults, slider ranges and coefficient provenance",
)
async def get_simulator(
    battery_id: uuid.UUID, repo: RepoDep, service: ServiceDep
) -> SimulatorConfigResponse:
    return mappers.simulator_config_response(
        await service.analyze(repo, battery_id, DEFAULT_EOL_PCT)
    )


@router.post(
    "/simulate",
    response_model=SimulateResponse,
    responses=ERRORS,
    summary="Simulate a scenario against the 25 °C / 1C / 80% DoD baseline",
)
async def post_simulate(
    battery_id: uuid.UUID, body: SimulateRequest, repo: RepoDep, service: ServiceDep
) -> SimulateResponse:
    analysis = await service.analyze(repo, battery_id, body.params.eol_pct)
    result = await run_in_threadpool(
        simulate,
        mappers.scenario_params(body.params),
        analysis.analysis.trend.fade_pct_per_cycle,
        body.include_trajectories,
    )
    return mappers.simulate_response(analysis.battery, result)


@router.get(
    "/advisor",
    response_model=AdvisorResponse,
    responses=ERRORS,
    summary="Charging Advisor: one-factor sensitivity (v1, includes known defect F8)",
)
async def get_advisor(
    battery_id: uuid.UUID,
    repo: RepoDep,
    service: ServiceDep,
    eol_pct: Annotated[float, Query(ge=EOL_MIN_PCT, le=EOL_MAX_PCT)] = DEFAULT_EOL_PCT,
    start_soh_pct: Annotated[
        float | None,
        Query(
            ge=START_SOH.min,
            le=START_SOH.max,
            description="Initial SOH; default is the simulator default (current SOH, rounded).",
        ),
    ] = None,
) -> AdvisorResponse:
    analysis = await service.analyze(repo, battery_id, eol_pct)
    table = await run_in_threadpool(
        advisor_table,
        analysis.analysis.simulator_defaults,
        analysis.analysis.trend.fade_pct_per_cycle,
        start_soh_pct,
    )
    return mappers.advisor_response(analysis.battery, table)
