"""One contract, two implementations: InMemoryRepository and SqlRepository (PostgreSQL)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest

from app.analytics.synthetic import SYNTHETIC_V1, generate_synthetic_v1
from app.db.repositories import Repository, SqlRepository
from app.db.seed import SYNTHETIC_BATTERY_ID, cycles_checksum, synthetic_ground_truth
from app.db.session import Database
from tests.support.database import assert_disposable
from tests.support.memory_repository import InMemoryRepository

pytestmark = pytest.mark.anyio

PARAMS = {"temp_c": 30.0, "c_rate": 1.5, "dod_pct": 80.0, "horizon_cycles": 600}


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.db)])
async def repository(request: pytest.FixtureRequest) -> AsyncIterator[Repository]:
    if request.param == "memory":
        yield InMemoryRepository()
        return
    url: str = request.getfixturevalue("seeded_database_url")
    assert_disposable(url)
    database = Database(url)
    try:
        async with database.session() as session:
            repo = SqlRepository(session)
            yield repo
            for battery in await repo.list_batteries():  # leave the shared database clean
                for scenario in await repo.list_scenarios(battery.id):
                    await repo.delete_scenario(scenario.id)
    finally:
        await database.dispose()


async def test_dataset_listing_and_internal_meta(repository: Repository) -> None:
    datasets = await repository.list_datasets()
    assert [d.slug for d in datasets] == [SYNTHETIC_V1.dataset_id]
    d = datasets[0]
    assert (d.source, d.status, d.battery_count) == ("synthetic", "ready", 1)
    assert d.meta["injected_anomalies"] == synthetic_ground_truth()
    assert await repository.get_dataset(SYNTHETIC_V1.dataset_id) == d
    assert await repository.get_dataset("missing") is None


async def test_battery_listing(repository: Repository) -> None:
    batteries = await repository.list_batteries()
    assert len(batteries) == 1
    b = batteries[0]
    assert (b.external_id, b.dataset_slug, b.cycle_count) == (
        SYNTHETIC_BATTERY_ID,
        "synthetic-v1",
        320,
    )
    assert (b.nominal_capacity_ah, b.eol_threshold_pct, b.is_synthetic) == (2.0, 80.0, True)
    assert b.cycles_checksum == cycles_checksum(generate_synthetic_v1())
    assert await repository.get_battery(b.id) == b
    assert await repository.get_battery(uuid.uuid4()) is None


async def test_records_round_trip_bit_exactly(repository: Repository) -> None:
    battery = (await repository.list_batteries())[0]
    records = await repository.load_records(battery.id)
    expected = generate_synthetic_v1()
    assert records == expected
    for got, want in zip(records, expected, strict=True):
        for field in ("capacity_ah", "soh_pct", "temp_c", "voltage_v"):
            assert getattr(got, field).hex() == getattr(want, field).hex()
    assert await repository.load_records(uuid.uuid4()) == ()


async def test_scenario_crud(repository: Repository) -> None:
    battery = (await repository.list_batteries())[0]
    assert await repository.list_scenarios(battery.id) == []
    a = await repository.create_scenario(battery.id, "Hot climate", PARAMS)
    b = await repository.create_scenario(battery.id, "Second", {**PARAMS, "temp_c": 15.0})
    assert [s.name for s in await repository.list_scenarios(battery.id)] == [
        "Hot climate",
        "Second",
    ]
    assert a.params == PARAMS and a.simulator_version == "v1"
    assert await repository.get_scenario(a.id) == a

    renamed = await repository.update_scenario(a.id, name="Renamed")
    assert renamed is not None and renamed.name == "Renamed" and renamed.params == PARAMS
    assert renamed.updated_at >= a.updated_at
    reparam = await repository.update_scenario(a.id, params={**PARAMS, "c_rate": 2.0})
    assert reparam is not None and reparam.params["c_rate"] == 2.0 and reparam.name == "Renamed"

    assert await repository.delete_scenario(b.id) is True
    assert await repository.delete_scenario(b.id) is False
    assert await repository.get_scenario(b.id) is None
    assert await repository.update_scenario(uuid.uuid4(), name="x") is None
    assert [s.id for s in await repository.list_scenarios(battery.id)] == [a.id]
