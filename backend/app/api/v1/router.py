"""Aggregate router for ``/api/v1``."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import datasets, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(datasets.router)
