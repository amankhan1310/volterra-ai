"""The disposable-database guard refuses anything that is not a volterra_test_* database."""

from __future__ import annotations

import pytest

from tests.support.database import (
    UnsafeDatabaseError,
    assert_disposable,
    assert_disposable_name,
    create_database,
    disposable_url,
    drop_database,
    new_disposable_name,
)

ADMIN = "postgresql+asyncpg://volterra:not-a-secret@127.0.0.1:1/postgres"


@pytest.mark.parametrize(
    "name",
    [None, "", "volterra", "postgres", "template1", "volterra_test_", "volterra_test_xyz"]
    + ["volterra_test_0123456789ab; DROP DATABASE volterra", "Volterra_test_0123456789ab"],
)
def test_non_disposable_names_are_refused(name: str | None) -> None:
    with pytest.raises(UnsafeDatabaseError):
        assert_disposable_name(name)


def test_generated_names_are_disposable_and_unique() -> None:
    names = {new_disposable_name() for _ in range(50)}
    assert len(names) == 50
    assert all(assert_disposable_name(n) == n for n in names)


def test_urls_are_checked_by_database_name() -> None:
    name = new_disposable_name()
    url = disposable_url(ADMIN, name)
    assert assert_disposable(url) == name
    with pytest.raises(UnsafeDatabaseError):
        assert_disposable(ADMIN)
    with pytest.raises(UnsafeDatabaseError):
        disposable_url(ADMIN, "volterra")


@pytest.mark.anyio
@pytest.mark.parametrize("operation", [create_database, drop_database])
async def test_create_and_drop_refuse_before_connecting(operation) -> None:
    # ADMIN points at an unreachable port: reaching the server would raise a different error.
    with pytest.raises(UnsafeDatabaseError):
        await operation(ADMIN, "volterra")
