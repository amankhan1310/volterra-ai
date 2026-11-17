"""Health endpoints.

* ``GET /health`` - application health with database connectivity in the body; always ``200``
  while the process runs (used by the frontend's status indicator; unchanged).
* ``GET /health/live`` - liveness: ``200`` whenever the process can answer. Never touches the
  database, so a database outage does not make the platform restart a healthy process.
* ``GET /health/ready`` - readiness: ``200`` only when PostgreSQL answers ``SELECT 1`` within the
  timeout, otherwise ``503``. Hosting health checks should use this one.

No endpoint reveals connection details or exception messages; ``/health`` reports at most the
exception type, the readiness probe only a status word.
"""

from __future__ import annotations

import asyncio
from typing import Literal, Protocol

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import API_VERSION
from app.schemas.health import DatabaseHealth, HealthResponse

router = APIRouter(tags=["health"])

READY_TIMEOUT_SECONDS = 5.0


class Pingable(Protocol):
    async def ping(self) -> float:
        """Round-trip the database; return latency in milliseconds."""
        ...


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    database: Literal["ok", "unavailable", "not_configured"]


async def _database_health(request: Request) -> DatabaseHealth:
    database: Pingable | None = getattr(request.app.state, "database", None)
    if database is None:
        return DatabaseHealth(status="not_configured")
    try:
        latency = await asyncio.wait_for(database.ping(), READY_TIMEOUT_SECONDS)
        return DatabaseHealth(status="ok", latency_ms=latency)
    except Exception as exc:  # report connectivity, never crash the health check
        return DatabaseHealth(status="unavailable", error=type(exc).__name__)


@router.get("/health", response_model=HealthResponse, summary="Application and database health")
async def health(request: Request) -> HealthResponse:
    """Always ``200`` while the application runs; ``database.status`` reports connectivity."""
    return HealthResponse(
        status="ok", version=API_VERSION, database=await _database_health(request)
    )


@router.get("/health/live", response_model=LivenessResponse, summary="Liveness probe")
async def live() -> LivenessResponse:
    """``200`` while the process can serve requests (does not check dependencies)."""
    return LivenessResponse()


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse, "description": "A dependency is unavailable"}},
    summary="Readiness probe (PostgreSQL)",
)
async def ready(request: Request) -> JSONResponse:
    """``200`` when the database answers, otherwise ``503``."""
    db = await _database_health(request)
    ok = db.status == "ok"
    body = ReadinessResponse(status="ready" if ok else "not_ready", database=db.status)
    return JSONResponse(body.model_dump(), status_code=200 if ok else 503)
