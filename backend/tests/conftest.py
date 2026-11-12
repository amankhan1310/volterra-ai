"""Shared pytest fixtures and the golden-parity tolerance report."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from alembic import command

from tests.support import golden as golden_support
from tests.support.database import (
    DbTestSettings,
    assert_disposable,
    disposable_database,
    run_isolated,
    seed_database,
)
from tests.support.migrations import alembic_config


@pytest.fixture(scope="session")
def golden() -> Callable[[str], dict[str, Any]]:
    """Return a loader for golden fixtures: ``golden("dataset")`` (read-only, cached)."""
    return golden_support.load_golden


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    # Labels starting with "_" belong to the harness's own self-tests and are not reported.
    stats = {k: v for k, v in golden_support.STATS.items() if not k.startswith("_")}
    if not stats:
        return
    tr = terminalreporter
    tr.section("golden parity: numeric comparisons")
    header = ("label", "numeric", "exact", "tol.allowed", "tol.needed", "maxULP")
    tr.write_line(f"{header[0]:42s} " + " ".join(f"{h:>11s}" for h in header[1:]))
    total = golden_support.ComparisonStats()
    for label in sorted(stats):
        s = stats[label]
        total.merge(s)
        values = (s.numeric, s.exact, s.tolerance_allowed, s.tolerance_needed, s.max_ulp)
        tr.write_line(f"{label:42s} " + " ".join(f"{v:11d}" for v in values))
    tr.write_line(
        f"TOTAL: {total.numeric} numeric comparisons, {total.exact} bit-exact, "
        f"{total.tolerance_needed} needed the 1e-12 tolerance "
        f"(of {total.tolerance_allowed} on tolerance-allowed fields), max {total.max_ulp} ULP"
    )


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Run async tests on asyncio only (the API and database stack is asyncio-based)."""
    return "asyncio"


# --- PostgreSQL (tests marked `db`) -------------------------------------------------------------


@pytest.fixture(scope="session")
def admin_database_url() -> str:
    """Maintenance-database URL used only to create/drop disposable test databases.

    Skips when ``TEST_DATABASE_URL`` is unset, unless ``VOLTERRA_REQUIRE_DB=1`` (CI), in which
    case the session fails instead of silently skipping database tests.
    """
    settings = DbTestSettings()
    if settings.test_database_url is None:
        if settings.require_db:
            pytest.fail("VOLTERRA_REQUIRE_DB=1 but TEST_DATABASE_URL is not set")
        pytest.skip("PostgreSQL tests need TEST_DATABASE_URL (see backend/.env.example)")
    return settings.test_database_url.get_secret_value()


@pytest.fixture(scope="session")
def migrated_database_url(admin_database_url: str) -> Iterator[str]:
    """A disposable database migrated to head, shared by the session."""
    with disposable_database(admin_database_url) as url:
        assert_disposable(url)
        run_isolated(lambda: command.upgrade(alembic_config(url), "head"))
        yield url


@pytest.fixture(scope="session")
def seeded_database_url(admin_database_url: str) -> Iterator[str]:
    """A disposable database migrated to head and seeded with synthetic-v1 (session-wide)."""
    with disposable_database(admin_database_url) as url:
        assert_disposable(url)
        run_isolated(lambda: command.upgrade(alembic_config(url), "head"))
        run_isolated(lambda: asyncio.run(seed_database(url)))
        yield url


@pytest.fixture
def empty_database_url(admin_database_url: str) -> Iterator[str]:
    """A fresh, empty disposable database for one test (e.g. migration round trips)."""
    with disposable_database(admin_database_url) as url:
        yield url
