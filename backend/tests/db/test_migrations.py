"""Migrations against real PostgreSQL 16: round trip and model/migration drift."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import Base
from tests.support.database import assert_disposable
from tests.support.migrations import alembic_config

pytestmark = pytest.mark.db

PHASE_3_TABLES = {"alembic_version", "batteries", "cycles", "datasets", "scenarios"}
T = TypeVar("T")


def run(url: str, fn: Callable[[Connection], T]) -> T:
    """Run a synchronous inspection function on a connection to ``url``."""

    async def main() -> T:
        engine = create_async_engine(url, hide_parameters=True)
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(fn)
        finally:
            await engine.dispose()

    return asyncio.run(main())


def table_names(conn: Connection) -> set[str]:
    return set(inspect(conn).get_table_names())


def schema_diff(conn: Connection) -> list[object]:
    return list(compare_metadata(MigrationContext.configure(conn), Base.metadata))


def test_upgrade_downgrade_upgrade_round_trip(empty_database_url: str) -> None:
    assert_disposable(empty_database_url)
    config = alembic_config(empty_database_url)
    command.upgrade(config, "head")
    assert run(empty_database_url, table_names) == PHASE_3_TABLES
    command.downgrade(config, "base")
    assert run(empty_database_url, table_names) == {"alembic_version"}
    command.upgrade(config, "head")
    assert run(empty_database_url, table_names) == PHASE_3_TABLES


def test_migrated_schema_matches_the_models(migrated_database_url: str) -> None:
    assert run(migrated_database_url, schema_diff) == []


def test_constraint_and_index_names_in_the_database(migrated_database_url: str) -> None:
    def names(conn: Connection) -> dict[str, set[str]]:
        insp = inspect(conn)
        return {
            "uq": {u["name"] for u in insp.get_unique_constraints("cycles") if u["name"]},
            "fk": {f["name"] for f in insp.get_foreign_keys("cycles") if f["name"]},
            "ix": {i["name"] for i in insp.get_indexes("cycles") if i["name"]},
            "ck": {c["name"] for c in insp.get_check_constraints("datasets") if c["name"]},
        }

    found = run(migrated_database_url, names)
    assert "uq_cycles_battery_id_cycle_index_cycle_type" in found["uq"]
    assert "fk_cycles_battery_id_batteries" in found["fk"]
    assert "ix_cycles_start_time" in found["ix"]
    assert {"ck_datasets_source", "ck_datasets_status"} <= found["ck"]
