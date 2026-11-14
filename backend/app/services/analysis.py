"""Runs ``legacy_v1.analyze()`` (or, opt-in, ``analysis_v2.analyze_v2()``) for a battery, cached.

The API never re-implements analytics: it loads the stored records, calls the unchanged v1
entry point in a worker thread (it is CPU-bound), and hands the immutable result to mappers that
only copy values. Cache keys include a checksum of the records loaded for *this* request, so any
data change invalidates cached results automatically, and the algorithm version, so v1 and v2
results never mix.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from dataclasses import dataclass

from starlette.concurrency import run_in_threadpool

from app.analytics.analysis_v2 import AnalysisV2, analyze_v2
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
    algorithm: str = "v1"


@dataclass(frozen=True)
class BatteryAnalysis:
    battery: BatteryInfo
    records: tuple[CycleRecord, ...]
    analysis: LegacyV1Analysis


@dataclass(frozen=True)
class BatteryAnalysisV2:
    battery: BatteryInfo
    records: tuple[CycleRecord, ...]
    analysis: AnalysisV2


Cached = LegacyV1Analysis | AnalysisV2


class AnalysisCache:
    """Least-recently-used cache with a fixed maximum number of entries."""

    def __init__(self, max_entries: int) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self.max_entries = max_entries
        self.hits = 0
        self.misses = 0
        self._entries: OrderedDict[AnalysisKey, Cached] = OrderedDict()

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: AnalysisKey) -> Cached | None:
        value = self._entries.get(key)
        if value is None:
            self.misses += 1
            return None
        self.hits += 1
        self._entries.move_to_end(key)
        return value

    def put(self, key: AnalysisKey, value: Cached) -> None:
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

    async def _load(
        self, repo: Repository, battery_id: uuid.UUID, version: str
    ) -> tuple[BatteryInfo, tuple[CycleRecord, ...]]:
        battery = await self.battery(repo, battery_id)
        records = await repo.load_records(battery_id)
        if len(records) < MIN_CYCLES_V1:
            raise ApiError(
                422,
                "insufficient_data",
                f"{version} analysis needs at least {MIN_CYCLES_V1} cycles; "
                f"battery has {len(records)}",
            )
        return battery, records

    async def analyze(
        self, repo: Repository, battery_id: uuid.UUID, eol_pct: float
    ) -> BatteryAnalysis:
        battery, records = await self._load(repo, battery_id, "v1")
        key = AnalysisKey(battery_id, cycles_checksum(records), eol_pct)
        cached = self.cache.get(key)
        if isinstance(cached, LegacyV1Analysis):
            return BatteryAnalysis(battery=battery, records=records, analysis=cached)
        result = await run_in_threadpool(
            analyze, records, eol_pct=eol_pct, dataset_id=battery.dataset_slug
        )
        self.cache.put(key, result)
        return BatteryAnalysis(battery=battery, records=records, analysis=result)

    async def analyze_v2(
        self, repo: Repository, battery_id: uuid.UUID, eol_pct: float
    ) -> BatteryAnalysisV2:
        """The opt-in v2 analysis (corrected methods for F1-F8); same data and cache rules."""
        battery, records = await self._load(repo, battery_id, "v2")
        key = AnalysisKey(battery_id, cycles_checksum(records), eol_pct, "v2")
        cached = self.cache.get(key)
        if isinstance(cached, AnalysisV2):
            return BatteryAnalysisV2(battery=battery, records=records, analysis=cached)
        result = await run_in_threadpool(
            analyze_v2, records, eol_pct=eol_pct, dataset_id=battery.dataset_slug
        )
        self.cache.put(key, result)
        return BatteryAnalysisV2(battery=battery, records=records, analysis=result)
