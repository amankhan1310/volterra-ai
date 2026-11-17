"""In-memory :class:`~app.db.repositories.Repository` holding synthetic-v1, for API tests.

It is built from the same seed value builders as the database seed, and the repository contract
test runs identical assertions against it and against PostgreSQL, so the two cannot drift.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from app.analytics.synthetic import CycleRecord, generate_synthetic_v1
from app.db.repositories import (
    BatteryInfo,
    CycleData,
    DatasetInfo,
    MlModelInfo,
    RulPredictionSet,
    ScenarioInfo,
    ScenarioLimitError,
)
from app.db.seed import cycles_checksum, synthetic_battery_values, synthetic_dataset_values


class InMemoryRepository:
    def __init__(self, records: Sequence[CycleRecord] | None = None) -> None:
        data = tuple(records) if records is not None else generate_synthetic_v1()
        checksum = cycles_checksum(data)
        dv = synthetic_dataset_values(checksum)
        bv = synthetic_battery_values(checksum)
        self.dataset = DatasetInfo(id=uuid.uuid4(), battery_count=1, **dv)
        self.battery = BatteryInfo(
            id=uuid.uuid4(),
            dataset_slug=self.dataset.slug,
            dataset_name=self.dataset.name,
            cycle_count=len(data),
            **{k: v for k, v in bv.items() if k != "test_conditions"},
        )
        self._records: dict[uuid.UUID, tuple[CycleRecord, ...]] = {self.battery.id: data}
        self._scenarios: dict[uuid.UUID, ScenarioInfo] = {}
        self._owners: dict[uuid.UUID, uuid.UUID | None] = {}
        self.load_calls = 0
        self.ml_models: list[MlModelInfo] = []
        self.predictions: dict[uuid.UUID, RulPredictionSet] = {}

    def replace_records(self, records: Sequence[CycleRecord]) -> None:
        """Swap the battery's data (and checksum), as a re-import would."""
        data = tuple(records)
        self._records[self.battery.id] = data
        self.battery = BatteryInfo(
            **{**vars(self.battery), "cycles_checksum": cycles_checksum(data)}
        )

    async def list_datasets(self) -> list[DatasetInfo]:
        return [self.dataset]

    async def get_dataset(self, slug: str) -> DatasetInfo | None:
        return self.dataset if slug == self.dataset.slug else None

    async def list_batteries(self) -> list[BatteryInfo]:
        return [self.battery]

    async def get_battery(self, battery_id: uuid.UUID) -> BatteryInfo | None:
        return self.battery if battery_id == self.battery.id else None

    async def load_records(self, battery_id: uuid.UUID) -> tuple[CycleRecord, ...]:
        self.load_calls += 1
        return self._records.get(battery_id, ())

    async def load_cycle_data(self, battery_id: uuid.UUID) -> tuple[CycleData, ...]:
        return tuple(
            CycleData(
                r.cycle, r.capacity_ah, r.soh_pct, r.temp_c, r.voltage_v, None, None, (), None
            )
            for r in self._records.get(battery_id, ())
        )

    async def latest_ml_models(self) -> list[MlModelInfo]:
        return list(self.ml_models)

    async def rul_predictions(self, battery_id: uuid.UUID) -> RulPredictionSet | None:
        return self.predictions.get(battery_id)

    async def sample_files(self, battery_id: uuid.UUID) -> tuple[str, ...]:
        return ()  # synthetic data has cycle summaries only

    def _owned(self, scenario_id: uuid.UUID, owner_id: uuid.UUID | None) -> ScenarioInfo | None:
        scenario = self._scenarios.get(scenario_id)
        if scenario is None or self._owners.get(scenario_id) != owner_id:
            return None
        return scenario

    async def list_scenarios(
        self, battery_id: uuid.UUID, *, owner_id: uuid.UUID | None = None
    ) -> list[ScenarioInfo]:
        return [
            s
            for s in self._scenarios.values()
            if s.battery_id == battery_id and self._owners.get(s.id) == owner_id
        ]

    async def get_scenario(
        self, scenario_id: uuid.UUID, *, owner_id: uuid.UUID | None = None
    ) -> ScenarioInfo | None:
        return self._owned(scenario_id, owner_id)

    async def create_scenario(
        self,
        battery_id: uuid.UUID,
        name: str,
        params: Mapping[str, Any],
        *,
        owner_id: uuid.UUID | None = None,
        limit: int | None = None,
        total_limit: int | None = None,
    ) -> ScenarioInfo:
        # No await between the checks and the insert: atomic within the event loop.
        if (
            limit is not None
            and len(await self.list_scenarios(battery_id, owner_id=owner_id)) >= limit
        ):
            raise ScenarioLimitError("owner", limit)
        if total_limit is not None and len(self._scenarios) >= total_limit:
            raise ScenarioLimitError("total", total_limit)
        now = datetime.now(timezone.utc)
        scenario = ScenarioInfo(uuid.uuid4(), battery_id, name, dict(params), "v1", now, now)
        self._scenarios[scenario.id] = scenario
        self._owners[scenario.id] = owner_id
        return scenario

    async def update_scenario(
        self,
        scenario_id: uuid.UUID,
        *,
        owner_id: uuid.UUID | None = None,
        name: str | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> ScenarioInfo | None:
        current = self._owned(scenario_id, owner_id)
        if current is None:
            return None
        updated = ScenarioInfo(
            id=current.id,
            battery_id=current.battery_id,
            name=current.name if name is None else name,
            params=current.params if params is None else dict(params),
            simulator_version=current.simulator_version,
            created_at=current.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self._scenarios[scenario_id] = updated
        return updated

    async def delete_scenario(
        self, scenario_id: uuid.UUID, *, owner_id: uuid.UUID | None = None
    ) -> bool:
        if self._owned(scenario_id, owner_id) is None:
            return False
        del self._scenarios[scenario_id]
        del self._owners[scenario_id]
        return True
