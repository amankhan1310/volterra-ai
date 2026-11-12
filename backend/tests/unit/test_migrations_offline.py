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


def test_single_linear_history_with_head_0001() -> None:
    script = ScriptDirectory.from_config(alembic_config(OFFLINE_URL))
    assert script.get_heads() == ["0001"]
    assert [r.revision for r in script.walk_revisions()] == ["0001"]


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
