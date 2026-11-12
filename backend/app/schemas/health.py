"""Health check response."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DatabaseHealth(BaseModel):
    status: Literal["ok", "unavailable", "not_configured"]
    latency_ms: float | None = None
    error: str | None = Field(default=None, description="Exception type only; never a message.")


class HealthResponse(BaseModel):
    status: Literal["ok"] = Field(description="Application health; independent of the database.")
    service: str = "volterra-api"
    version: str
    api_version: str = "v1"
    algorithm_version: str = "v1"
    database: DatabaseHealth
