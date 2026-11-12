"""Datasets, batteries and cycle data."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_analysis_service, get_repository
from app.core.errors import ApiError, error_responses, not_found
from app.db.repositories import Repository
from app.schemas.datasets import BatteryList, BatteryOut, CyclesResponse, DatasetList, DatasetOut
from app.services import mappers
from app.services.analysis import AnalysisService

router = APIRouter(tags=["datasets"])

RepoDep = Annotated[Repository, Depends(get_repository)]
ServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]


@router.get("/datasets", response_model=DatasetList, summary="List datasets")
async def list_datasets(repo: RepoDep) -> DatasetList:
    return DatasetList(items=[mappers.dataset_out(d) for d in await repo.list_datasets()])


@router.get(
    "/datasets/{slug}",
    response_model=DatasetOut,
    responses=error_responses(404),
    summary="Get a dataset",
)
async def get_dataset(slug: str, repo: RepoDep) -> DatasetOut:
    dataset = await repo.get_dataset(slug)
    if dataset is None:
        raise not_found("dataset", slug)
    return mappers.dataset_out(dataset)


@router.get("/batteries", response_model=BatteryList, summary="List batteries", tags=["batteries"])
async def list_batteries(repo: RepoDep) -> BatteryList:
    return BatteryList(items=[mappers.battery_out(b) for b in await repo.list_batteries()])


@router.get(
    "/batteries/{battery_id}",
    response_model=BatteryOut,
    responses=error_responses(404),
    summary="Get a battery",
    tags=["batteries"],
)
async def get_battery(battery_id: uuid.UUID, repo: RepoDep, service: ServiceDep) -> BatteryOut:
    return mappers.battery_out(await service.battery(repo, battery_id))


@router.get(
    "/batteries/{battery_id}/cycles",
    response_model=CyclesResponse,
    responses=error_responses(404, 422),
    summary="Per-cycle measurements",
    tags=["batteries"],
)
async def get_cycles(
    battery_id: uuid.UUID,
    repo: RepoDep,
    service: ServiceDep,
    from_cycle: Annotated[int | None, Query(ge=0, description="First cycle (inclusive).")] = None,
    to_cycle: Annotated[int | None, Query(ge=0, description="Last cycle (inclusive).")] = None,
) -> CyclesResponse:
    if from_cycle is not None and to_cycle is not None and from_cycle > to_cycle:
        raise ApiError(422, "invalid_range", "from_cycle must not exceed to_cycle")
    battery = await service.battery(repo, battery_id)
    records = [
        r
        for r in await repo.load_records(battery_id)
        if (from_cycle is None or r.cycle >= from_cycle)
        and (to_cycle is None or r.cycle <= to_cycle)
    ]
    return mappers.cycles_response(battery, records)
