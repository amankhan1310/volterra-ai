"""Runs ``legacy_v1.analyze()`` for a battery, with a bounded cache.

The API never re-implements analytics: it loads the stored records, calls the unchanged v1
entry point in a worker thread (it is CPU-bound), and hands the immutable result to mappers that
only copy values. Cache keys include a checksum of the records loaded for *this* request, so any
data change invalidates cached results automatically.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from dataclasses import dataclass

from starlette.concurrency import run_in_threadpool

from app.analytics.backtest import TEST_FROM_CYCLE
from app.analytics.legacy_v1 import LegacyV1Analysis, analyze
from app.analytics.synthetic import CycleRecord
from app.core.errors import ApiError, not_found
from app.db.repositories import BatteryInfo, Repository
from app.db.seed import cycles_checksum

#: v1 needs the backtest window (cycles 100-219) plus at least one test cycle.
MIN_CYCLES_V1 = TEST_FROM_CYCLE + 1


@dataclass(frozen=True)
class AnalysisKey:
    battery_id: uuid.UUID
    data_checksum: str
    eol_pct: float


@dataclass(frozen=True)
class BatteryAnalysis:
    battery: BatteryInfo
    records: tuple[CycleRecord, ...]
    analysis: LegacyV1Analysis


class AnalysisCache:
    """Least-recently-used cache with a fixed maximum number of entries."""

    def __init__(self, max_entries: int) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self.max_entries = max_entries
        self.hits = 0
        self.misses = 0
        self._entries: OrderedDict[AnalysisKey, LegacyV1Analysis] = OrderedDict()

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: AnalysisKey) -> LegacyV1Analysis | None:
        value = self._entries.get(key)
        if value is None:
            self.misses += 1
            return None
        self.hits += 1
        self._entries.move_to_end(key)
        return value

    def put(self, key: AnalysisKey, value: LegacyV1Analysis) -> None:
        self._entries[key] = value
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)


class AnalysisService:
    def __init__(self, cache: AnalysisCache) -> None:
        self.cache = cache

    async def battery(self, repo: Repository, battery_id: uuid.UUID) -> BatteryInfo:
        battery = await repo.get_battery(battery_id)
        if battery is None:
            raise not_found("battery", battery_id)
        return battery

    async def analyze(
        self, repo: Repository, battery_id: uuid.UUID, eol_pct: float
    ) -> BatteryAnalysis:
        battery = await self.battery(repo, battery_id)
        records = await repo.load_records(battery_id)
        if len(records) < MIN_CYCLES_V1:
            raise ApiError(
                422,
                "insufficient_data",
                f"v1 analysis needs at least {MIN_CYCLES_V1} cycles; battery has {len(records)}",
            )
        key = AnalysisKey(battery_id, cycles_checksum(records), eol_pct)
        result = self.cache.get(key)
        if result is None:
            result = await run_in_threadpool(
                analyze, records, eol_pct=eol_pct, dataset_id=battery.dataset_slug
            )
            self.cache.put(key, result)
        return BatteryAnalysis(battery=battery, records=records, analysis=result)
