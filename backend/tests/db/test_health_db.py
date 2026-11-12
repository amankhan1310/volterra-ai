"""/health against a real PostgreSQL database."""

from __future__ import annotations

import pytest

from app.db.session import Database
from app.main import create_app
from tests.support.api import client_for, make_settings
from tests.support.database import assert_disposable

pytestmark = [pytest.mark.db, pytest.mark.anyio]


async def test_health_reports_a_reachable_database(migrated_database_url: str) -> None:
    assert_disposable(migrated_database_url)
    database = Database(migrated_database_url)
    try:
        async with client_for(create_app(make_settings(), database=database)) as client:
            body = (await client.get("/api/v1/health")).json()
    finally:
        await database.dispose()
    assert body["status"] == "ok"
    assert body["database"]["status"] == "ok"
    assert body["database"]["latency_ms"] >= 0
