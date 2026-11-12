"""FastAPI dependencies: repository (per-request session) and the analysis service."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from app.core.errors import ApiError
from app.db.repositories import Repository, SqlRepository
from app.services.analysis import AnalysisService


async def get_repository(request: Request) -> AsyncIterator[Repository]:
    database = request.app.state.database
    if database is None:
        raise ApiError(503, "database_unavailable", "The database is not configured")
    async with database.session() as session:
        yield SqlRepository(session)


def get_analysis_service(request: Request) -> AnalysisService:
    service: AnalysisService = request.app.state.analysis_service
    return service
