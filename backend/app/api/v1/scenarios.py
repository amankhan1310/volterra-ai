"""Saved what-if scenarios: create, list, read, rename/re-parameterise, delete."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_analysis_service, get_repository
from app.core.errors import error_responses, not_found
from app.db.repositories import Repository
from app.schemas.scenarios import ScenarioCreate, ScenarioList, ScenarioOut, ScenarioUpdate
from app.services import mappers
from app.services.analysis import AnalysisService

router = APIRouter(tags=["scenarios"])

RepoDep = Annotated[Repository, Depends(get_repository)]
ServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]


@router.get(
    "/batteries/{battery_id}/scenarios",
    response_model=ScenarioList,
    responses=error_responses(404),
    summary="List saved scenarios for a battery",
)
async def list_scenarios(battery_id: uuid.UUID, repo: RepoDep, service: ServiceDep) -> ScenarioList:
    await service.battery(repo, battery_id)
    return ScenarioList(
        items=[mappers.scenario_out(s) for s in await repo.list_scenarios(battery_id)]
    )


@router.post(
    "/batteries/{battery_id}/scenarios",
    response_model=ScenarioOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(404, 422),
    summary="Save a scenario",
)
async def create_scenario(
    battery_id: uuid.UUID, body: ScenarioCreate, repo: RepoDep, service: ServiceDep
) -> ScenarioOut:
    await service.battery(repo, battery_id)
    created = await repo.create_scenario(battery_id, body.name, body.params.model_dump())
    return mappers.scenario_out(created)


@router.get(
    "/scenarios/{scenario_id}",
    response_model=ScenarioOut,
    responses=error_responses(404),
    summary="Get a saved scenario",
)
async def get_scenario(scenario_id: uuid.UUID, repo: RepoDep) -> ScenarioOut:
    scenario = await repo.get_scenario(scenario_id)
    if scenario is None:
        raise not_found("scenario", scenario_id)
    return mappers.scenario_out(scenario)


@router.patch(
    "/scenarios/{scenario_id}",
    response_model=ScenarioOut,
    responses=error_responses(404, 422),
    summary="Rename and/or change a scenario's parameters",
)
async def update_scenario(
    scenario_id: uuid.UUID, body: ScenarioUpdate, repo: RepoDep
) -> ScenarioOut:
    updated = await repo.update_scenario(
        scenario_id,
        name=body.name,
        params=body.params.model_dump() if body.params is not None else None,
    )
    if updated is None:
        raise not_found("scenario", scenario_id)
    return mappers.scenario_out(updated)


@router.delete(
    "/scenarios/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(404),
    summary="Delete a scenario",
)
async def delete_scenario(scenario_id: uuid.UUID, repo: RepoDep) -> Response:
    if not await repo.delete_scenario(scenario_id):
        raise not_found("scenario", scenario_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
