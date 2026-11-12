"""AnalysisService: exact pass-through of legacy_v1.analyze, bounded cache, invalidation."""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from app.analytics.legacy_v1 import analyze
from app.analytics.synthetic import generate_synthetic_v1
from app.api.deps import get_analysis_service, get_repository
from app.core.errors import ApiError
from app.db.repositories import SqlRepository
from app.services.analysis import MIN_CYCLES_V1, AnalysisCache, AnalysisKey, AnalysisService
from tests.support.api import memory_app
from tests.support.memory_repository import InMemoryRepository

pytestmark = pytest.mark.anyio


def key(n: int) -> AnalysisKey:
    return AnalysisKey(uuid.UUID(int=n), "c" * 64, 80.0)


def test_cache_is_bounded_lru() -> None:
    cache = AnalysisCache(2)
    result = analyze()
    cache.put(key(1), result)
    cache.put(key(2), result)
    assert cache.get(key(1)) is result  # 1 becomes most recent
    cache.put(key(3), result)  # evicts 2
    assert len(cache) == 2
    assert cache.get(key(2)) is None
    assert cache.get(key(1)) is result and cache.get(key(3)) is result
    assert (cache.hits, cache.misses) == (3, 1)
    with pytest.raises(ValueError):
        AnalysisCache(0)


async def test_service_returns_exactly_what_analyze_returns() -> None:
    repo = InMemoryRepository()
    service = AnalysisService(AnalysisCache(4))
    got = await service.analyze(repo, repo.battery.id, 85.0)
    assert got.analysis == analyze(generate_synthetic_v1(), eol_pct=85.0, dataset_id="synthetic-v1")
    assert got.records == generate_synthetic_v1()
    assert got.battery == repo.battery


async def test_repeat_requests_hit_the_cache_per_eol() -> None:
    repo = InMemoryRepository()
    service = AnalysisService(AnalysisCache(4))
    first = await service.analyze(repo, repo.battery.id, 80.0)
    second = await service.analyze(repo, repo.battery.id, 80.0)
    other = await service.analyze(repo, repo.battery.id, 70.0)
    assert second.analysis is first.analysis
    assert other.analysis is not first.analysis
    assert (service.cache.hits, service.cache.misses, len(service.cache)) == (1, 2, 2)


async def test_data_change_invalidates_cached_results() -> None:
    repo = InMemoryRepository()
    service = AnalysisService(AnalysisCache(4))
    before = await service.analyze(repo, repo.battery.id, 80.0)
    records = list(generate_synthetic_v1())
    records[-1] = dataclasses.replace(records[-1], soh_pct=records[-1].soh_pct - 1.0)
    repo.replace_records(records)
    after = await service.analyze(repo, repo.battery.id, 80.0)
    assert after.analysis is not before.analysis
    assert after.analysis.trend.observed_last_soh_pct != before.analysis.trend.observed_last_soh_pct
    assert service.cache.misses == 2


async def test_unknown_battery_and_insufficient_data() -> None:
    service = AnalysisService(AnalysisCache(4))
    repo = InMemoryRepository()
    with pytest.raises(ApiError) as missing:
        await service.analyze(repo, uuid.uuid4(), 80.0)
    assert (missing.value.status_code, missing.value.code) == (404, "battery_not_found")
    short = InMemoryRepository(generate_synthetic_v1()[: MIN_CYCLES_V1 - 1])
    with pytest.raises(ApiError) as too_short:
        await service.analyze(short, short.battery.id, 80.0)
    assert (too_short.value.status_code, too_short.value.code) == (422, "insufficient_data")


async def test_dependencies() -> None:
    app, _ = memory_app()

    class Request:
        def __init__(self, database: object) -> None:
            self.app = type("App", (), {"state": type("State", (), {"database": database})()})()

    with pytest.raises(ApiError) as unavailable:
        async for _ in get_repository(Request(None)):  # type: ignore[arg-type]
            pass
    assert unavailable.value.status_code == 503

    class FakeDatabase:
        @asynccontextmanager
        async def session(self) -> AsyncIterator[object]:
            yield object()

    repos = [r async for r in get_repository(Request(FakeDatabase()))]  # type: ignore[arg-type]
    assert isinstance(repos[0], SqlRepository)
    assert get_analysis_service(type("R", (), {"app": app})()) is app.state.analysis_service
