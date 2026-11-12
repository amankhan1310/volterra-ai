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

DESCRIPTION = (
    "VOLTERRA AI battery analytics API. Analytical values carry provenance "
    "(measured, simulated, fitted, predicted, assumed); algorithm version v1 reproduces the "
    "legacy prototype exactly, including its documented defects F1–F8."
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
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
    app.state.database = None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(api_router, prefix=API_PREFIX)
    return app
