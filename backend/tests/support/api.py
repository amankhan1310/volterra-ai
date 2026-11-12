"""Helpers for API tests: isolated settings and an in-process HTTP client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI

from app.core.config import Settings


def make_settings(**overrides: Any) -> Settings:
    """Settings built only from the given values (no ``backend/.env``, no environment).

    ``model_validate`` skips the settings sources that ``Settings()`` would read, so tests are
    isolated from developer and CI configuration.
    """
    values: dict[str, Any] = {"database_url": None, "environment": "test", **overrides}
    return Settings.model_validate(values)


@asynccontextmanager
async def client_for(
    app: FastAPI, *, raise_app_exceptions: bool = True
) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
