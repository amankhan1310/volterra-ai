"""Migrations against real PostgreSQL 16: round trip and model/migration drift."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import Base
from tests.support.database import assert_disposable
from tests.support.migrations import alembic_config

pytestmark = pytest.mark.db

PHASE_3_TABLES = {"alembic_version", "batteries", "cycles", "datasets", "scenarios"}
HEAD_TABLES = PHASE_3_TABLES | {"dataset_files"}  # 0002 (Phase 6 M3); 0003 adds a column
PHASE_6_COLUMNS = {
    "datasets": {"publisher", "landing_url", "doi"},
    "batteries": {
        "chemistry_basis",
        "soh_reference",
        "soh_reference_capacity_ah",
        "first_capacity_ah",
        "first_capacity_cycle_index",
    },
    "cycles": {"source_cycle_index"},
}
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
    assert run(empty_database_url, table_names) == HEAD_TABLES
    command.downgrade(config, "base")
    assert run(empty_database_url, table_names) == {"alembic_version"}
    command.upgrade(config, "head")
    assert run(empty_database_url, table_names) == HEAD_TABLES


def columns(conn: Connection) -> dict[str, set[str]]:
    insp = inspect(conn)
    return {
        t: {c["name"] for c in insp.get_columns(t)} for t in ("datasets", "batteries", "cycles")
    }


def test_0002_is_additive_and_downgrades_to_the_exact_phase_3_schema(
    empty_database_url: str,
) -> None:
    assert_disposable(empty_database_url)
    config = alembic_config(empty_database_url)
    command.upgrade(config, "0001")
    phase_3 = run(empty_database_url, columns)
    command.upgrade(config, "0002")
    phase_6_m3 = run(empty_database_url, columns)
    command.upgrade(config, "0003")
    head = run(empty_database_url, columns)
    for table, added in PHASE_6_COLUMNS.items():
        assert phase_6_m3[table] == phase_3[table] | added, table
    # 0003 (schema v2) adds exactly cycles.source_ref
    assert head["cycles"] == phase_6_m3["cycles"] | {"source_ref"}
    assert {t: head[t] for t in ("datasets", "batteries")} == {
        t: phase_6_m3[t] for t in ("datasets", "batteries")
    }
    command.downgrade(config, "0002")
    assert run(empty_database_url, columns) == phase_6_m3
    command.downgrade(config, "0001")
    assert run(empty_database_url, table_names) == PHASE_3_TABLES
    assert run(empty_database_url, columns) == phase_3


def nullability(conn: Connection) -> dict[str, bool]:
    return {c["name"]: c["nullable"] for c in inspect(conn).get_columns("cycles")}


def test_0004_relaxes_only_temperature_and_voltage_and_refuses_a_lossy_downgrade(
    empty_database_url: str,
) -> None:
    assert_disposable(empty_database_url)
    config = alembic_config(empty_database_url)
    command.upgrade(config, "0003")
    before = run(empty_database_url, nullability)
    command.upgrade(config, "0004")
    after = run(empty_database_url, nullability)
    assert {k for k in after if after[k] != before[k]} == {"temp_mean_c", "voltage_mean_v"}
    assert after["temp_mean_c"] and after["voltage_mean_v"]
    assert not (after["capacity_ah"] or after["soh_pct"])

    def add_null_cycle(conn: Connection) -> None:
        for statement in (
            "INSERT INTO datasets (slug, name, source, version, status) "
            "VALUES ('t', 't', 'calce', '1', 'ready')",
            "INSERT INTO batteries (dataset_id, external_id, nominal_capacity_ah) "
            "SELECT id, 'c', 1.1 FROM datasets",
            "INSERT INTO cycles (battery_id, cycle_index, capacity_ah, soh_pct, voltage_mean_v) "
            "SELECT id, 0, 1.0, 90.9, 3.7 FROM batteries",
        ):
            conn.execute(text(statement))
        conn.commit()

    run(empty_database_url, add_null_cycle)
    with pytest.raises(RuntimeError, match="1 cycles have no temperature or voltage"):
        command.downgrade(config, "0003")
    assert run(empty_database_url, nullability) == after  # nothing changed, nothing deleted

    def remove_dataset(conn: Connection) -> None:
        conn.execute(text("DELETE FROM datasets"))
        conn.commit()

    run(empty_database_url, remove_dataset)
    command.downgrade(config, "0003")
    assert run(empty_database_url, nullability) == before


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
