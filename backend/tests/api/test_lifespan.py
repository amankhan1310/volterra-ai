"""Lifespan wiring of the database (no real connection is opened)."""

from __future__ import annotations

import pytest

from app.db.session import Database
from app.main import create_app
from tests.support.api import make_settings

pytestmark = pytest.mark.anyio

UNREACHABLE = "postgresql+asyncpg://nobody:not-a-secret@127.0.0.1:1/none"


async def test_lifespan_creates_and_disposes_the_configured_database() -> None:
    app = create_app(make_settings(database_url=UNREACHABLE))
    before: object = app.state.database
    async with app.router.lifespan_context(app):
        during: object = app.state.database
        assert isinstance(during, Database)
        assert "not-a-secret" not in repr(during.engine.url)
    after: object = app.state.database
    assert before is None and after is None


async def test_lifespan_keeps_an_injected_database() -> None:
    injected = Database(UNREACHABLE)
    app = create_app(make_settings(database_url=UNREACHABLE), database=injected)
    async with app.router.lifespan_context(app):
        assert app.state.database is injected
    assert app.state.database is injected
    await injected.dispose()


async def test_lifespan_without_database_url() -> None:
    app = create_app(make_settings())
    async with app.router.lifespan_context(app):
        assert app.state.database is None
