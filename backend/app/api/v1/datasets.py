"""Datasets, batteries and cycle data."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_analysis_service, get_repository
from app.core.errors import ApiError, error_responses, not_found
from app.db.repositories import Repository
from app.schemas.datasets import (
    BatteryList,
    BatteryOut,
    CycleSamplesResponse,
    CyclesResponse,
    DatasetList,
    DatasetOut,
)
from app.services import mappers
from app.services.analysis import AnalysisService, analysis_availability
from app.services.samples import (
    DEFAULT_MAX_POINTS,
    MAX_POINTS_LIMIT,
    SamplesUnavailableError,
    read_cycle_samples,
)

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
    return BatteryList(
        items=[
            mappers.battery_out(b, analysis_availability(b)) for b in await repo.list_batteries()
        ]
    )


@router.get(
    "/batteries/{battery_id}",
    response_model=BatteryOut,
    responses=error_responses(404),
    summary="Get a battery",
    tags=["batteries"],
)
async def get_battery(battery_id: uuid.UUID, repo: RepoDep, service: ServiceDep) -> BatteryOut:
    battery = await service.battery(repo, battery_id)
    return mappers.battery_out(battery, analysis_availability(battery))


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
    cycles = [
        c
        for c in await repo.load_cycle_data(battery_id)
        if (from_cycle is None or c.cycle >= from_cycle)
        and (to_cycle is None or c.cycle <= to_cycle)
    ]
    return mappers.cycles_response(battery, cycles)


@router.get(
    "/batteries/{battery_id}/cycles/{cycle}/samples",
    response_model=CycleSamplesResponse,
    responses=error_responses(404, 422, 503),
    summary="Measured samples of one cycle (downsampled for charts)",
    tags=["batteries"],
)
async def get_cycle_samples(
    battery_id: uuid.UUID,
    cycle: int,
    request: Request,
    repo: RepoDep,
    service: ServiceDep,
    max_points: Annotated[
        int,
        Query(
            ge=2,
            le=MAX_POINTS_LIMIT,
            description="Most samples to return; longer series are evenly downsampled, always "
            "keeping the first and last sample.",
        ),
    ] = DEFAULT_MAX_POINTS,
) -> CycleSamplesResponse:
    battery = await service.battery(repo, battery_id)
    if battery.is_synthetic:
        raise ApiError(
            422, "no_samples", "The synthetic dataset has cycle summaries only, no samples"
        )
    found = next((c for c in await repo.load_cycle_data(battery_id) if c.cycle == cycle), None)
    if found is None:
        raise ApiError(404, "cycle_not_found", f"Cycle {cycle} not found")
    data_dir = request.app.state.settings.data_dir
    files = await repo.sample_files(battery_id)
    if data_dir is None or not files:
        raise ApiError(503, "samples_unavailable", "Sample data is not available on this server")
    try:
        samples = await run_in_threadpool(
            read_cycle_samples,
            data_dir,
            files,
            cycle_index=cycle,
            source_cycle_index=found.source_cycle_index,
            max_points=max_points,
        )
    except SamplesUnavailableError:
        raise ApiError(
            503, "samples_unavailable", "Sample data is not available on this server"
        ) from None
    return mappers.samples_response(battery, cycle, samples)
