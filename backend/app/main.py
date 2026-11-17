"""FastAPI application factory.

Run locally with::

    uv run uvicorn --factory app.main:create_app --reload

The factory has no import-time side effects: settings are read and connections opened only when
an application is created and started.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import API_PREFIX, API_VERSION, Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.guard import RequestGuard
from app.core.sessions import CSRF_HEADER, SessionSigner
from app.db.session import Database
from app.services.analysis import AnalysisCache, AnalysisService

DESCRIPTION = (
    "VOLTERRA AI battery analytics API. Analytical values carry provenance "
    "(measured, simulated, fitted, predicted, assumed); algorithm version v1 reproduces the "
    "legacy prototype exactly, including its documented defects F1–F8."
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the database configured in settings (unless one was injected); close it on exit."""
    owned: Database | None = None
    dsn = app.state.settings.database_dsn()
    if app.state.database is None and dsn:
        owned = app.state.database = Database(dsn)
    try:
        yield
    finally:
        if owned is not None:
            await owned.dispose()
            app.state.database = None


def create_app(settings: Settings | None = None, *, database: Database | None = None) -> FastAPI:
    """Build the application. ``database`` lets tests inject an already-open database."""
    settings = settings or get_settings()
    app = FastAPI(
        title="VOLTERRA AI API",
        version=API_VERSION,
        description=DESCRIPTION,
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.analysis_service = AnalysisService(AnalysisCache(settings.analysis_cache_size))
    app.state.session_signer = SessionSigner.from_settings(settings)
    # The browser app calls the API on its own origin (Vite proxy locally, Vercel rewrite in
    # production), so CORS only governs direct cross-origin callers: no credentials, and only
    # the headers the app sends.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", CSRF_HEADER],
        allow_credentials=False,
    )
    # Outermost: rejects oversized bodies and rate-limited requests before any other work.
    app.add_middleware(RequestGuard, settings=settings, signer=app.state.session_signer)
    register_error_handlers(app)
    app.include_router(api_router, prefix=API_PREFIX)
    return app
