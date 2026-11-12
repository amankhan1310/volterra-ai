"""Schema definition tests (no database needed): tables, types, constraints and names."""

from __future__ import annotations

import pytest
from sqlalchemy import ForeignKeyConstraint, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.base import Base
from app.db.models import Battery, Cycle, Dataset, Scenario

TABLES = Base.metadata.tables
PG = postgresql.dialect()  # type: ignore[no-untyped-call]  # SQLAlchemy dialect factory is untyped


def ddl(table: Table) -> str:
    return str(CreateTable(table).compile(dialect=PG))


def test_exactly_the_four_phase_3_tables() -> None:
    assert sorted(TABLES) == ["batteries", "cycles", "datasets", "scenarios"]
    assert {m.__tablename__ for m in (Dataset, Battery, Cycle, Scenario)} == set(TABLES)


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("batteries", "nominal_capacity_ah"),
        ("batteries", "eol_threshold_pct"),
        ("cycles", "capacity_ah"),
        ("cycles", "soh_pct"),
        ("cycles", "temp_mean_c"),
        ("cycles", "voltage_mean_v"),
        ("cycles", "dod_pct"),
    ],
)
def test_numeric_measurements_are_double_precision(table: str, column: str) -> None:
    compiled = TABLES[table].c[column].type.compile(dialect=PG)
    assert compiled == "DOUBLE PRECISION"


def test_no_numeric_or_generated_columns() -> None:
    for table in TABLES.values():
        text = ddl(table)
        assert "NUMERIC" not in text and "GENERATED ALWAYS AS (" not in text, table.name


def test_v1_inputs_are_not_null_and_extras_are_nullable() -> None:
    cycles = TABLES["cycles"].c
    for name in ("capacity_ah", "soh_pct", "temp_mean_c", "voltage_mean_v", "cycle_index"):
        assert not cycles[name].nullable, name
    for name in ("temp_max_c", "internal_resistance_ohm", "start_time", "c_rate"):
        assert cycles[name].nullable, name


def test_constraint_names_follow_the_naming_convention() -> None:
    names = {c.name for t in TABLES.values() for c in t.constraints}
    for expected in (
        "pk_datasets",
        "uq_datasets_slug",
        "ck_datasets_source",
        "ck_datasets_status",
        "uq_batteries_dataset_id_external_id",
        "ck_batteries_nominal_capacity_positive",
        "fk_batteries_dataset_id_datasets",
        "uq_cycles_battery_id_cycle_index_cycle_type",
        "ck_cycles_cycle_type",
        "fk_cycles_battery_id_batteries",
        "fk_scenarios_battery_id_batteries",
        "ck_scenarios_name_not_blank",
    ):
        assert expected in names, expected


def test_foreign_keys_cascade_on_delete() -> None:
    fks = [c for t in TABLES.values() for c in t.constraints if isinstance(c, ForeignKeyConstraint)]
    assert len(fks) == 3
    assert all(fk.ondelete == "CASCADE" for fk in fks)


def test_indexes() -> None:
    brin = next(i for i in TABLES["cycles"].indexes if i.name == "ix_cycles_start_time")
    assert "USING brin" in str(CreateIndex(brin).compile(dialect=PG))
    assert {i.name for i in TABLES["batteries"].indexes} == {"ix_batteries_dataset_id"}
    assert {i.name for i in TABLES["scenarios"].indexes} == {"ix_scenarios_battery_id"}


def test_scenario_name_limit_and_server_defaults() -> None:
    assert TABLES["scenarios"].c["name"].type.length == 60  # type: ignore[attr-defined]
    assert "gen_random_uuid()" in ddl(TABLES["datasets"])
    assert "'{}'::jsonb" in ddl(TABLES["cycles"])
