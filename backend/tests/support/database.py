"""Disposable PostgreSQL databases for tests.

Safety rules (never touch a development or production database):

* Tests connect to ``TEST_DATABASE_URL`` (a maintenance database such as ``postgres``) only to
  ``CREATE`` / ``DROP`` databases named ``volterra_test_<12 hex chars>``.
* :func:`assert_disposable` guards every destructive operation and every URL handed to tests;
  any other database name raises :class:`UnsafeDatabaseError` before a connection is opened.
* Credentials are read from the environment or ``backend/.env`` and never printed.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import ENV_FILE

DISPOSABLE_PREFIX = "volterra_test_"
_DISPOSABLE_NAME = re.compile(r"volterra_test_[0-9a-f]{12}")


class UnsafeDatabaseError(RuntimeError):
    """Raised when a test would operate on a database that is not disposable."""


class DbTestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    test_database_url: SecretStr | None = Field(default=None, validation_alias="TEST_DATABASE_URL")
    require_db: bool = Field(default=False, validation_alias="VOLTERRA_REQUIRE_DB")

    @field_validator("test_database_url", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value


def new_disposable_name() -> str:
    return DISPOSABLE_PREFIX + uuid.uuid4().hex[:12]


def assert_disposable_name(name: str | None) -> str:
    if name is None or not _DISPOSABLE_NAME.fullmatch(name):
        raise UnsafeDatabaseError(f"refusing to use non-disposable database {name!r}")
    return name


def assert_disposable(url: str) -> str:
    """Return the database name of ``url`` if it is a disposable test database, else raise."""
    return assert_disposable_name(make_url(url).database)


def disposable_url(admin_url: str, name: str) -> str:
    assert_disposable_name(name)
    return make_url(admin_url).set(database=name).render_as_string(hide_password=False)


async def create_database(admin_url: str, name: str) -> None:
    assert_disposable_name(name)
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text(f"CREATE DATABASE \"{name}\" ENCODING 'UTF8' TEMPLATE template0")
            )
    finally:
        await engine.dispose()


async def drop_database(admin_url: str, name: str) -> None:
    assert_disposable_name(name)
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    finally:
        await engine.dispose()


@contextmanager
def disposable_database(admin_url: str) -> Iterator[str]:
    """Create a fresh ``volterra_test_*`` database, yield its URL, then drop it."""
    name = new_disposable_name()
    asyncio.run(create_database(admin_url, name))
    try:
        yield disposable_url(admin_url, name)
    finally:
        asyncio.run(drop_database(admin_url, name))
