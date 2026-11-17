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

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.synthetic import CycleRecord
from app.db.models import Battery, Cycle, Dataset, DatasetFile, MlModel, MlPrediction, Scenario

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
    #: Cycles whose temperature or voltage was not measured (null, never filled in; D3).
    incomplete_cycle_count: int = 0
    #: Cycles carrying at least one data-quality flag.
    flagged_cycle_count: int = 0
    #: Battery-level notes from the source, ``(code, detail)`` (e.g. Severson ``paper_excluded``).
    dataset_flags: tuple[tuple[str, str], ...] = ()
    #: SOH reference stated for the battery (``rated_capacity``) and its value; null when the
    #: source states none (the synthetic seed uses its nominal capacity).
    soh_reference: str | None = None
    soh_reference_capacity_ah: float | None = None


@dataclass(frozen=True)
class CycleData:
    """One stored cycle for data views: measurements as stored (null when not measured)."""

    cycle: int
    capacity_ah: float
    soh_pct: float
    temp_c: float | None
    voltage_v: float | None
    internal_resistance_ohm: float | None
    charge_time_s: float | None
    quality_flags: tuple[str, ...]
    source_cycle_index: int | None


@dataclass(frozen=True)
class MlModelInfo:
    """One task of an imported Phase 7 run, with its evaluation as the run reported it."""

    id: uuid.UUID
    run_id: str
    task: str
    kind: str
    selected_model: str
    status: str
    trained_at: datetime
    artifact_sha256: str | None
    metrics: Mapping[str, Any]
    run_meta: Mapping[str, Any]


@dataclass(frozen=True)
class RulPoint:
    cycle: int
    soh_pct: float
    rul: float
    lower: float
    upper: float
    actual_rul: float | None
    past_eol: bool


@dataclass(frozen=True)
class RulPredictionSet:
    """The latest run's stored RUL predictions for one battery."""

    model: MlModelInfo
    split: str
    interval_basis: str
    eol_cycle: float | None
    censored: bool
    points: tuple[RulPoint, ...]


class IncompleteCycleError(ValueError):
    """A v1 analytics record was requested for a cycle without temperature or voltage."""


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
    async def load_cycle_data(self, battery_id: uuid.UUID) -> tuple[CycleData, ...]: ...
    async def sample_files(self, battery_id: uuid.UUID) -> tuple[str, ...]: ...
    async def latest_ml_models(self) -> list[MlModelInfo]: ...
    async def rul_predictions(self, battery_id: uuid.UUID) -> RulPredictionSet | None: ...
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
            .order_by((Dataset.source == "synthetic").desc(), Dataset.slug)
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
        records = []
        for cycle, capacity, soh, temp, voltage in rows.all():
            if temp is None or voltage is None:
                raise IncompleteCycleError(
                    f"cycle {cycle} has no temperature or voltage measurement; "
                    "load_cycle_data serves batteries with incomplete cycles"
                )
            records.append(CycleRecord(cycle, capacity, soh, temp, voltage))
        return tuple(records)

    async def load_cycle_data(self, battery_id: uuid.UUID) -> tuple[CycleData, ...]:
        rows = await self.session.execute(
            select(
                Cycle.cycle_index,
                Cycle.capacity_ah,
                Cycle.soh_pct,
                Cycle.temp_mean_c,
                Cycle.voltage_mean_v,
                Cycle.internal_resistance_ohm,
                Cycle.charge_time_s,
                Cycle.quality_flags,
                Cycle.source_cycle_index,
            )
            .where(Cycle.battery_id == battery_id, Cycle.cycle_type == V1_CYCLE_TYPE)
            .order_by(Cycle.cycle_index)
        )
        return tuple(
            CycleData(i, cap, soh, temp, volt, ir, ct, tuple(sorted(flags)), src)
            for i, cap, soh, temp, volt, ir, ct, flags, src in rows.all()
        )

    async def latest_ml_models(self) -> list[MlModelInfo]:
        """Every task of the most recently imported run (empty when none was imported)."""
        latest = await self.session.scalar(
            select(MlModel.run_id).order_by(MlModel.created_at.desc(), MlModel.run_id).limit(1)
        )
        if latest is None:
            return []
        models = await self.session.scalars(
            select(MlModel).where(MlModel.run_id == latest).order_by(MlModel.task)
        )
        return [_ml_model_info(m) for m in models]

    async def rul_predictions(self, battery_id: uuid.UUID) -> RulPredictionSet | None:
        model = next((m for m in await self.latest_ml_models() if m.task == "rul"), None)
        if model is None:
            return None
        rows = (
            await self.session.scalars(
                select(MlPrediction)
                .where(MlPrediction.model_id == model.id, MlPrediction.battery_id == battery_id)
                .order_by(MlPrediction.cycle_index)
            )
        ).all()
        if not rows:
            return None
        first = rows[0]
        return RulPredictionSet(
            model=model,
            split=first.split,
            interval_basis=first.interval_basis,
            eol_cycle=first.eol_cycle,
            censored=first.censored,
            points=tuple(
                RulPoint(
                    r.cycle_index,
                    r.soh_pct,
                    r.rul,
                    r.lower_rul,
                    r.upper_rul,
                    r.actual_rul,
                    r.past_eol,
                )
                for r in rows
            ),
        )

    async def sample_files(self, battery_id: uuid.UUID) -> tuple[str, ...]:
        """Paths (relative to the data directory) of the battery's sample files."""
        rows = await self.session.scalars(
            select(DatasetFile.path)
            .where(DatasetFile.battery_id == battery_id, DatasetFile.kind == "samples")
            .order_by(DatasetFile.path)
        )
        return tuple(rows.all())

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
        incomplete = or_(Cycle.temp_mean_c.is_(None), Cycle.voltage_mean_v.is_(None))
        counts = (
            select(
                Cycle.battery_id,
                func.count(Cycle.id).label("n"),
                func.count(Cycle.id).filter(incomplete).label("incomplete"),
                func.count(Cycle.id).filter(Cycle.quality_flags != {}).label("flagged"),
            )
            .where(Cycle.cycle_type == V1_CYCLE_TYPE)
            .group_by(Cycle.battery_id)
            .subquery()
        )
        query = (
            select(
                Battery,
                Dataset.slug,
                Dataset.name,
                func.coalesce(counts.c.n, 0),
                func.coalesce(counts.c.incomplete, 0),
                func.coalesce(counts.c.flagged, 0),
            )
            .join(Dataset, Dataset.id == Battery.dataset_id)
            .outerjoin(counts, counts.c.battery_id == Battery.id)
            # Synthetic first: the frontend opens the first battery by default (decision D11).
            .order_by(Battery.is_synthetic.desc(), Dataset.slug, Battery.external_id)
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
                incomplete_cycle_count=int(n_incomplete),
                flagged_cycle_count=int(n_flagged),
                dataset_flags=tuple(
                    sorted((b.test_conditions or {}).get("dataset_flags", {}).items())
                ),
                soh_reference=b.soh_reference,
                soh_reference_capacity_ah=b.soh_reference_capacity_ah,
            )
            for b, slug, dname, n, n_incomplete, n_flagged in rows.all()
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


def _ml_model_info(m: MlModel) -> MlModelInfo:
    return MlModelInfo(
        id=m.id,
        run_id=m.run_id,
        task=m.task,
        kind=m.kind,
        selected_model=m.selected_model,
        status=m.status,
        trained_at=m.trained_at,
        artifact_sha256=m.artifact_sha256,
        metrics=m.metrics,
        run_meta=m.run_meta,
    )
