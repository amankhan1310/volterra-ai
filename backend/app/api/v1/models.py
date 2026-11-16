"""Phase 7 models: the latest imported run's evaluation and stored RUL predictions."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_repository
from app.core.errors import ApiError, error_responses, not_found
from app.db.repositories import Repository
from app.schemas.models import ModelsResponse, RulPredictionsResponse
from app.services import mappers

router = APIRouter(tags=["models"])

RepoDep = Annotated[Repository, Depends(get_repository)]


@router.get(
    "/models",
    response_model=ModelsResponse,
    responses=error_responses(503),
    summary="Model evaluations of the latest imported run",
    description="Battery-wise cross-validation and held-out test metrics per dataset, as the "
    "offline run reported them. `run` is null and `tasks` empty when no run was imported.",
)
async def list_models(repo: RepoDep) -> ModelsResponse:
    return mappers.models_response(await repo.latest_ml_models())


@router.get(
    "/batteries/{battery_id}/rul-predictions",
    response_model=RulPredictionsResponse,
    responses=error_responses(404, 503),
    summary="Stored RUL predictions for a battery",
    description="Predicted remaining useful life at each prediction point with its conformal "
    "interval, next to the battery's actual RUL when its EOL is known. 404 "
    "`predictions_not_found` when the latest run has none for this battery (for example the "
    "synthetic battery, or a battery that was not in the run).",
)
async def get_rul_predictions(battery_id: uuid.UUID, repo: RepoDep) -> RulPredictionsResponse:
    battery = await repo.get_battery(battery_id)
    if battery is None:
        raise not_found("battery", battery_id)
    predictions = await repo.rul_predictions(battery_id)
    if predictions is None:
        raise ApiError(
            404,
            "predictions_not_found",
            f"No model predictions for battery {battery.external_id} in the latest imported run",
        )
    return mappers.rul_predictions_response(battery, predictions)
