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
from app.db.repositories import BatteryInfo, DatasetInfo, ScenarioInfo
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
        self.load_calls = 0

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

    async def list_scenarios(self, battery_id: uuid.UUID) -> list[ScenarioInfo]:
        return [s for s in self._scenarios.values() if s.battery_id == battery_id]

    async def get_scenario(self, scenario_id: uuid.UUID) -> ScenarioInfo | None:
        return self._scenarios.get(scenario_id)

    async def create_scenario(
        self, battery_id: uuid.UUID, name: str, params: Mapping[str, Any]
    ) -> ScenarioInfo:
        now = datetime.now(timezone.utc)
        scenario = ScenarioInfo(uuid.uuid4(), battery_id, name, dict(params), "v1", now, now)
        self._scenarios[scenario.id] = scenario
        return scenario

    async def update_scenario(
        self,
        scenario_id: uuid.UUID,
        *,
        name: str | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> ScenarioInfo | None:
        current = self._scenarios.get(scenario_id)
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

    async def delete_scenario(self, scenario_id: uuid.UUID) -> bool:
        return self._scenarios.pop(scenario_id, None) is not None
