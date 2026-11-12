"""``GET /health``: application health, reported separately from database connectivity."""

from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, Request

from app.core.config import API_VERSION
from app.schemas.health import DatabaseHealth, HealthResponse

router = APIRouter(tags=["health"])


class Pingable(Protocol):
    async def ping(self) -> float:
        """Round-trip the database; return latency in milliseconds."""
        ...


@router.get("/health", response_model=HealthResponse, summary="Application and database health")
async def health(request: Request) -> HealthResponse:
    """Always ``200`` while the application runs; ``database.status`` reports connectivity."""
    database: Pingable | None = getattr(request.app.state, "database", None)
    if database is None:
        db = DatabaseHealth(status="not_configured")
    else:
        try:
            db = DatabaseHealth(status="ok", latency_ms=await database.ping())
        except Exception as exc:  # report connectivity, never crash the health check
            db = DatabaseHealth(status="unavailable", error=type(exc).__name__)
    return HealthResponse(status="ok", version=API_VERSION, database=db)
