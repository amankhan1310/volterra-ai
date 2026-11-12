"""Seed idempotency, conflict detection, ground truth and database constraints (PostgreSQL)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from alembic import command
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.synthetic import generate_synthetic_v1
from app.db.models import Battery, Cycle, Dataset
from app.db.seed import SeedConflictError, seed_synthetic_v1
from app.db.seed import _main as seed_cli_main
from app.db.session import Database
from tests.support.api import make_settings
from tests.support.database import assert_disposable, run_isolated
from tests.support.migrations import alembic_config

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
async def fresh_session(empty_database_url: str) -> AsyncIterator[AsyncSession]:
    """A session on a fresh, migrated, *unseeded* disposable database."""
    assert_disposable(empty_database_url)
    run_isolated(lambda: command.upgrade(alembic_config(empty_database_url), "head"))
    database = Database(empty_database_url)
    try:
        async with database.session() as session:
            yield session
    finally:
        await database.dispose()


async def count(session: AsyncSession, model: type) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_seed_is_idempotent(fresh_session: AsyncSession) -> None:
    first = await seed_synthetic_v1(fresh_session)
    second = await seed_synthetic_v1(fresh_session)
    assert first.created and not second.created
    assert (first.dataset_id, first.battery_id) == (second.dataset_id, second.battery_id)
    assert first.cycles == second.cycles == 320
    assert await count(fresh_session, Cycle) == 320
    assert await count(fresh_session, Dataset) == await count(fresh_session, Battery) == 1


async def test_seed_refuses_to_overwrite_different_data(fresh_session: AsyncSession) -> None:
    await seed_synthetic_v1(fresh_session)
    await fresh_session.execute(update(Battery).values(cycles_checksum="0" * 64))
    await fresh_session.commit()
    with pytest.raises(SeedConflictError):
        await seed_synthetic_v1(fresh_session)


async def test_ground_truth_is_stored_like_the_golden_fixture(
    fresh_session: AsyncSession, golden
) -> None:
    await seed_synthetic_v1(fresh_session)
    meta = await fresh_session.scalar(select(Dataset.meta))
    assert meta is not None
    assert meta["injected_anomalies"] == golden("dataset")["parameters"]["injected_anomalies"]


async def test_deleting_a_dataset_cascades(fresh_session: AsyncSession) -> None:
    await seed_synthetic_v1(fresh_session)
    await fresh_session.execute(delete(Dataset))
    await fresh_session.commit()
    assert await count(fresh_session, Battery) == await count(fresh_session, Cycle) == 0


async def test_constraints_are_enforced(fresh_session: AsyncSession) -> None:
    result = await seed_synthetic_v1(fresh_session)
    r = generate_synthetic_v1()[0]
    duplicate = {
        "battery_id": result.battery_id,
        "cycle_index": r.cycle,
        "capacity_ah": r.capacity_ah,
        "soh_pct": r.soh_pct,
        "temp_mean_c": r.temp_c,
        "voltage_mean_v": r.voltage_v,
    }
    with pytest.raises(IntegrityError):
        await fresh_session.execute(insert(Cycle).values(**duplicate))
    await fresh_session.rollback()
    with pytest.raises(IntegrityError):
        await fresh_session.execute(
            insert(Dataset).values(slug="bad", name="Bad", source="unknown", version="1")
        )
    await fresh_session.rollback()
    with pytest.raises(IntegrityError):
        await fresh_session.execute(
            insert(Cycle).values(**{**duplicate, "cycle_index": 999, "capacity_ah": -1.0})
        )
    await fresh_session.rollback()


async def test_seed_cli_reports_without_revealing_the_url(
    seeded_database_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert_disposable(seeded_database_url)
    settings = make_settings(database_url=seeded_database_url)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    assert await seed_cli_main() == 0
    out = capsys.readouterr().out
    assert out.startswith("Already seeded synthetic-v1: battery ") and "320 cycles" in out
    assert "postgresql" not in out and "@" not in out
