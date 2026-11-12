"""Aggregate router for ``/api/v1``."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import analysis, datasets, health, monitoring, simulator

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(datasets.router)
api_router.include_router(analysis.router)
api_router.include_router(monitoring.router)
api_router.include_router(simulator.router)
