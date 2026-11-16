"""Migration scripts without a database: history shape and offline SQL generation."""

from __future__ import annotations

import io
from contextlib import redirect_stdout

from alembic import command
from alembic.script import ScriptDirectory

from tests.support.migrations import alembic_config

OFFLINE_URL = "postgresql+asyncpg://offline@localhost/offline"  # never connected to


def offline_sql(revision: str, *, downgrade: bool = False) -> str:
    config = alembic_config(OFFLINE_URL)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        if downgrade:
            command.downgrade(config, revision, sql=True)
        else:
            command.upgrade(config, revision, sql=True)
    return buffer.getvalue()


def test_single_linear_history_with_head_0005() -> None:
    script = ScriptDirectory.from_config(alembic_config(OFFLINE_URL))
    assert script.get_heads() == ["0005"]
    assert [r.revision for r in script.walk_revisions()] == [
        "0005",
        "0004",
        "0003",
        "0002",
        "0001",
    ]


def test_offline_0002_is_additive_only() -> None:
    sql = offline_sql("0001:0002")
    assert "CREATE TABLE dataset_files" in sql
    assert sql.count("ALTER TABLE") >= 9 and "ADD COLUMN" in sql
    # Only Alembic's own version bookkeeping may update a row; no existing data is touched.
    lines = [s.strip() for s in sql.splitlines()]
    data_changes = [
        s
        for s in lines
        if s.startswith(("UPDATE ", "DELETE FROM", "DROP ", "TRUNCATE"))
        and not s.startswith("UPDATE alembic_version ")
    ]
    assert data_changes == []
    assert "ALTER COLUMN" not in sql and "SET NOT NULL" not in sql
    down = offline_sql("0002:0001", downgrade=True)
    assert "DROP TABLE dataset_files" in down and "CREATE TABLE" not in down


def test_offline_upgrade_emits_the_phase_3_schema() -> None:
    sql = offline_sql("head")
    for table in ("datasets", "batteries", "cycles", "scenarios"):
        assert f"CREATE TABLE {table}" in sql
    assert "DOUBLE PRECISION" in sql and "NUMERIC" not in sql
    assert "USING brin" in sql
    assert "ON DELETE CASCADE" in sql
    assert "gen_random_uuid()" in sql
    assert "INSERT INTO alembic_version" in sql


def test_offline_downgrade_drops_everything() -> None:
    sql = offline_sql("0001:base", downgrade=True)
    for table in ("scenarios", "cycles", "batteries", "datasets"):
        assert f"DROP TABLE {table}" in sql


def test_offline_0003_adds_only_cycles_source_ref() -> None:
    sql = offline_sql("0002:0003")
    assert "ALTER TABLE cycles ADD COLUMN source_ref JSONB" in sql
    changes = [
        s.strip()
        for s in sql.splitlines()
        if s.strip().startswith(("ALTER", "CREATE", "DROP", "UPDATE ", "DELETE"))
    ]
    assert [c for c in changes if not c.startswith("UPDATE alembic_version ")] == [
        "ALTER TABLE cycles ADD COLUMN source_ref JSONB;"
    ]
    assert "ALTER TABLE cycles DROP COLUMN source_ref" in offline_sql("0003:0002", downgrade=True)


def test_offline_0004_only_drops_not_null_on_temperature_and_voltage() -> None:
    sql = offline_sql("0003:0004")
    changes = [
        s.strip()
        for s in sql.splitlines()
        if s.strip().startswith(("ALTER", "CREATE", "DROP", "UPDATE ", "DELETE"))
    ]
    assert [c for c in changes if not c.startswith("UPDATE alembic_version ")] == [
        "ALTER TABLE cycles ALTER COLUMN temp_mean_c DROP NOT NULL;",
        "ALTER TABLE cycles ALTER COLUMN voltage_mean_v DROP NOT NULL;",
    ]
    down = offline_sql("0004:0003", downgrade=True)
    assert "ALTER COLUMN temp_mean_c SET NOT NULL" in down
    assert "ALTER COLUMN voltage_mean_v SET NOT NULL" in down


def test_offline_0005_only_creates_the_two_ml_tables() -> None:
    sql = offline_sql("0004:0005")
    statements = [
        s.strip()
        for s in sql.splitlines()
        if s.strip().startswith(("ALTER", "CREATE", "DROP", "DELETE"))
    ]
    assert statements == [
        "CREATE TABLE ml_models (",
        "CREATE INDEX ix_ml_models_run_id ON ml_models (run_id);",
        "CREATE TABLE ml_predictions (",
        "CREATE INDEX ix_ml_predictions_battery_id ON ml_predictions (battery_id);",
    ]
    down = offline_sql("0005:0004", downgrade=True)
    drops = [s.strip() for s in down.splitlines() if s.strip().startswith("DROP")]
    assert drops == [
        "DROP INDEX ix_ml_predictions_battery_id;",
        "DROP TABLE ml_predictions;",
        "DROP INDEX ix_ml_models_run_id;",
        "DROP TABLE ml_models;",
    ]
