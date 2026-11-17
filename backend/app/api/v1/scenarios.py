"""Saved what-if scenarios: create, list, read, rename/re-parameterise, delete.

Access (``VOLTERRA_SCENARIO_ACCESS``, see :mod:`app.core.config`):

* ``session`` (production default): each browser session owns its scenarios. The session is an
  anonymous, signed, HttpOnly cookie issued on the first save (:mod:`app.core.sessions`). Every
  read, update and delete is filtered by the owner; another session's scenario answers 404, the
  same as a missing one. Writes also need the CSRF header.
* ``shared`` (local development default): one shared list per battery, as before.
* ``disabled``: lists are empty and writes answer 403.

Limits: at most ``scenario_limit`` scenarios per battery and owner, and ``scenario_total_limit``
overall, both enforced atomically by the database (409 ``scenario_limit_reached``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import get_analysis_service, get_repository
from app.core.config import Settings
from app.core.errors import ApiError, error_responses, not_found
from app.core.sessions import COOKIE_NAME, SessionSigner, check_csrf, set_session_cookie
from app.db.repositories import Repository, ScenarioLimitError
from app.schemas.scenarios import ScenarioCreate, ScenarioList, ScenarioOut, ScenarioUpdate
from app.services import mappers
from app.services.analysis import AnalysisService

router = APIRouter(tags=["scenarios"])

RepoDep = Annotated[Repository, Depends(get_repository)]
ServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]


@dataclass(frozen=True)
class Owner:
    """Whose scenarios a request may see. ``known`` is False when a session has none yet."""

    mode: str
    owner_id: uuid.UUID | None
    known: bool


def get_owner(request: Request) -> Owner:
    settings: Settings = request.app.state.settings
    mode = settings.effective_scenario_access
    if mode != "session":
        return Owner(mode, None, mode == "shared")
    signer: SessionSigner = request.app.state.session_signer
    session_id = signer.verify(request.cookies.get(COOKIE_NAME))
    return Owner(mode, session_id, session_id is not None)


def require_write(request: Request) -> None:
    """403 when writes are disabled; CSRF check for cookie-authenticated writes."""
    settings: Settings = request.app.state.settings
    mode = settings.effective_scenario_access
    if mode == "disabled":
        raise ApiError(403, "scenarios_read_only", "Saving scenarios is disabled on this server")
    if mode == "session":
        check_csrf(request, settings)


OwnerDep = Annotated[Owner, Depends(get_owner)]
WRITE = [Depends(require_write)]


@router.get(
    "/batteries/{battery_id}/scenarios",
    response_model=ScenarioList,
    responses=error_responses(404),
    summary="List saved scenarios for a battery",
)
async def list_scenarios(
    battery_id: uuid.UUID, repo: RepoDep, service: ServiceDep, owner: OwnerDep
) -> ScenarioList:
    await service.battery(repo, battery_id)
    if not owner.known:
        return ScenarioList(items=[])
    items = await repo.list_scenarios(battery_id, owner_id=owner.owner_id)
    return ScenarioList(items=[mappers.scenario_out(s) for s in items])


@router.post(
    "/batteries/{battery_id}/scenarios",
    response_model=ScenarioOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(403, 404, 409, 422),
    dependencies=WRITE,
    summary="Save a scenario",
)
async def create_scenario(
    battery_id: uuid.UUID,
    body: ScenarioCreate,
    request: Request,
    response: Response,
    repo: RepoDep,
    service: ServiceDep,
    owner: OwnerDep,
) -> ScenarioOut:
    settings: Settings = request.app.state.settings
    await service.battery(repo, battery_id)
    owner_id = owner.owner_id
    if owner.mode == "session" and owner_id is None:
        signer: SessionSigner = request.app.state.session_signer
        owner_id, cookie = signer.issue()
        set_session_cookie(response, cookie, secure=settings.environment == "production")
    try:
        created = await repo.create_scenario(
            battery_id,
            body.name,
            body.params.model_dump(),
            owner_id=owner_id,
            limit=settings.scenario_limit,
            total_limit=settings.scenario_total_limit,
        )
    except ScenarioLimitError as exc:
        message = (
            f"Delete a scenario first (max {exc.limit} per battery)."
            if exc.scope == "owner"
            else "The server's scenario storage is full; please try again later."
        )
        raise ApiError(409, "scenario_limit_reached", message) from None
    return mappers.scenario_out(created)


@router.get(
    "/scenarios/{scenario_id}",
    response_model=ScenarioOut,
    responses=error_responses(404),
    summary="Get a saved scenario",
)
async def get_scenario(scenario_id: uuid.UUID, repo: RepoDep, owner: OwnerDep) -> ScenarioOut:
    scenario = (
        await repo.get_scenario(scenario_id, owner_id=owner.owner_id) if owner.known else None
    )
    if scenario is None:
        raise not_found("scenario", scenario_id)
    return mappers.scenario_out(scenario)


@router.patch(
    "/scenarios/{scenario_id}",
    response_model=ScenarioOut,
    responses=error_responses(403, 404, 422),
    dependencies=WRITE,
    summary="Rename and/or change a scenario's parameters",
)
async def update_scenario(
    scenario_id: uuid.UUID, body: ScenarioUpdate, repo: RepoDep, owner: OwnerDep
) -> ScenarioOut:
    updated = (
        await repo.update_scenario(
            scenario_id,
            owner_id=owner.owner_id,
            name=body.name,
            params=body.params.model_dump() if body.params is not None else None,
        )
        if owner.known
        else None
    )
    if updated is None:
        raise not_found("scenario", scenario_id)
    return mappers.scenario_out(updated)


@router.delete(
    "/scenarios/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(403, 404),
    dependencies=WRITE,
    summary="Delete a scenario",
)
async def delete_scenario(scenario_id: uuid.UUID, repo: RepoDep, owner: OwnerDep) -> Response:
    deleted = owner.known and await repo.delete_scenario(scenario_id, owner_id=owner.owner_id)
    if not deleted:
        raise not_found("scenario", scenario_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
