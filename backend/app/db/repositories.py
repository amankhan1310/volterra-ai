"""Data access behind a small protocol, so the API can be tested without a database.

:class:`SqlRepository` is the PostgreSQL implementation. Results are immutable value objects;
measurement columns are passed through untouched (``float8`` -> Python ``float`` is exact), so
:meth:`Repository.load_records` returns exactly the records that were stored.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.synthetic import CycleRecord
from app.db.models import Battery, Cycle, Dataset, Scenario

V1_CYCLE_TYPE = "discharge"


@dataclass(frozen=True)
class DatasetInfo:
    id: uuid.UUID
    slug: str
    name: str
    source: str
    version: str
    licence: str | None
    citation: str | None
    description: str | None
    status: str
    checksum: str | None
    battery_count: int
    #: Internal metadata (e.g. synthetic ground truth). Never returned by public endpoints.
    meta: Mapping[str, Any]


@dataclass(frozen=True)
class BatteryInfo:
    id: uuid.UUID
    external_id: str
    dataset_slug: str
    dataset_name: str
    chemistry: str | None
    form_factor: str | None
    nominal_capacity_ah: float
    nominal_voltage_v: float | None
    eol_threshold_pct: float
    is_synthetic: bool
    cycles_checksum: str | None
    cycle_count: int


@dataclass(frozen=True)
class ScenarioInfo:
    id: uuid.UUID
    battery_id: uuid.UUID
    name: str
    params: Mapping[str, Any]
    simulator_version: str
    created_at: datetime
    updated_at: datetime


class Repository(Protocol):
    async def list_datasets(self) -> list[DatasetInfo]: ...
    async def get_dataset(self, slug: str) -> DatasetInfo | None: ...
    async def list_batteries(self) -> list[BatteryInfo]: ...
    async def get_battery(self, battery_id: uuid.UUID) -> BatteryInfo | None: ...
    async def load_records(self, battery_id: uuid.UUID) -> tuple[CycleRecord, ...]: ...
    async def list_scenarios(self, battery_id: uuid.UUID) -> list[ScenarioInfo]: ...
    async def get_scenario(self, scenario_id: uuid.UUID) -> ScenarioInfo | None: ...
    async def create_scenario(
        self, battery_id: uuid.UUID, name: str, params: Mapping[str, Any]
    ) -> ScenarioInfo: ...
    async def update_scenario(
        self,
        scenario_id: uuid.UUID,
        *,
        name: str | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> ScenarioInfo | None: ...
    async def delete_scenario(self, scenario_id: uuid.UUID) -> bool: ...


def _scenario_info(s: Scenario) -> ScenarioInfo:
    return ScenarioInfo(
        id=s.id,
        battery_id=s.battery_id,
        name=s.name,
        params=dict(s.params),
        simulator_version=s.simulator_version,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


class SqlRepository:
    """PostgreSQL implementation of :class:`Repository` (one instance per session)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_datasets(self) -> list[DatasetInfo]:
        counts = (
            select(Battery.dataset_id, func.count(Battery.id).label("n"))
            .group_by(Battery.dataset_id)
            .subquery()
        )
        rows = await self.session.execute(
            select(Dataset, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.dataset_id == Dataset.id)
            .order_by(Dataset.slug)
        )
        return [self._dataset_info(d, int(n)) for d, n in rows.all()]

    async def get_dataset(self, slug: str) -> DatasetInfo | None:
        return next((d for d in await self.list_datasets() if d.slug == slug), None)

    async def list_batteries(self) -> list[BatteryInfo]:
        return await self._batteries()

    async def get_battery(self, battery_id: uuid.UUID) -> BatteryInfo | None:
        found = await self._batteries(battery_id)
        return found[0] if found else None

    async def load_records(self, battery_id: uuid.UUID) -> tuple[CycleRecord, ...]:
        rows = await self.session.execute(
            select(
                Cycle.cycle_index,
                Cycle.capacity_ah,
                Cycle.soh_pct,
                Cycle.temp_mean_c,
                Cycle.voltage_mean_v,
            )
            .where(Cycle.battery_id == battery_id, Cycle.cycle_type == V1_CYCLE_TYPE)
            .order_by(Cycle.cycle_index)
        )
        return tuple(CycleRecord(*row) for row in rows.all())

    async def list_scenarios(self, battery_id: uuid.UUID) -> list[ScenarioInfo]:
        rows = await self.session.scalars(
            select(Scenario)
            .where(Scenario.battery_id == battery_id)
            .order_by(Scenario.created_at, Scenario.id)
        )
        return [_scenario_info(s) for s in rows.all()]

    async def get_scenario(self, scenario_id: uuid.UUID) -> ScenarioInfo | None:
        scenario = await self.session.get(Scenario, scenario_id)
        return _scenario_info(scenario) if scenario else None

    async def create_scenario(
        self, battery_id: uuid.UUID, name: str, params: Mapping[str, Any]
    ) -> ScenarioInfo:
        scenario = Scenario(battery_id=battery_id, name=name, params=dict(params))
        self.session.add(scenario)
        await self.session.commit()
        await self.session.refresh(scenario)
        return _scenario_info(scenario)

    async def update_scenario(
        self,
        scenario_id: uuid.UUID,
        *,
        name: str | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> ScenarioInfo | None:
        scenario = await self.session.get(Scenario, scenario_id)
        if scenario is None:
            return None
        if name is not None:
            scenario.name = name
        if params is not None:
            scenario.params = dict(params)
        await self.session.commit()
        await self.session.refresh(scenario)
        return _scenario_info(scenario)

    async def delete_scenario(self, scenario_id: uuid.UUID) -> bool:
        scenario = await self.session.get(Scenario, scenario_id)
        if scenario is None:
            return False
        await self.session.delete(scenario)
        await self.session.commit()
        return True

    async def _batteries(self, battery_id: uuid.UUID | None = None) -> list[BatteryInfo]:
        counts = (
            select(Cycle.battery_id, func.count(Cycle.id).label("n"))
            .where(Cycle.cycle_type == V1_CYCLE_TYPE)
            .group_by(Cycle.battery_id)
            .subquery()
        )
        query = (
            select(Battery, Dataset.slug, Dataset.name, func.coalesce(counts.c.n, 0))
            .join(Dataset, Dataset.id == Battery.dataset_id)
            .outerjoin(counts, counts.c.battery_id == Battery.id)
            .order_by(Dataset.slug, Battery.external_id)
        )
        if battery_id is not None:
            query = query.where(Battery.id == battery_id)
        rows = await self.session.execute(query)
        return [
            BatteryInfo(
                id=b.id,
                external_id=b.external_id,
                dataset_slug=slug,
                dataset_name=dname,
                chemistry=b.chemistry,
                form_factor=b.form_factor,
                nominal_capacity_ah=b.nominal_capacity_ah,
                nominal_voltage_v=b.nominal_voltage_v,
                eol_threshold_pct=b.eol_threshold_pct,
                is_synthetic=b.is_synthetic,
                cycles_checksum=b.cycles_checksum,
                cycle_count=int(n),
            )
            for b, slug, dname, n in rows.all()
        ]

    @staticmethod
    def _dataset_info(d: Dataset, battery_count: int) -> DatasetInfo:
        return DatasetInfo(
            id=d.id,
            slug=d.slug,
            name=d.name,
            source=d.source,
            version=d.version,
            licence=d.licence,
            citation=d.citation,
            description=d.description,
            status=d.status,
            checksum=d.checksum,
            battery_count=battery_count,
            meta=dict(d.meta),
        )
