"""The generated real-style bundles, for fixture recording and E2E (never real data).

    uv run python -m tests.support.fixture_bundles write <data-dir>
    uv run python -m tests.support.fixture_bundles import <volterra_test_name> <data-dir>
    uv run python -m tests.support.fixture_bundles ci-import <data-dir>

``write`` writes the two generated bundles of ``tests/db/test_real_data_api.py`` (NASA-style and
CALCE-style) under ``<data-dir>`` and prints their paths; ``import`` and ``ci-import`` also import
the generated model run of ``tests/support/model_runs.py`` (made-up values). ``import`` loads
them into a local disposable ``volterra_test_*`` database (credentials come from the test
settings and are never printed). ``ci-import`` is the GitHub Actions E2E path: it refuses unless
it runs in GitHub Actions (``CI=true``, ``GITHUB_ACTIONS=true``) and ``DATABASE_URL`` names
exactly the CI service database ``volterra_ci`` on localhost, so it can never write to the
development database or any other one. It checks the target before writing any file, then
imports both bundles with the standard importer (``import_bundle``: every validation and
provenance check, one transaction per bundle) and re-imports everything to prove the imports
are idempotent. Serve the API with
``VOLTERRA_DATA_DIR=<data-dir>`` so their samples can be read.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.db.import_dataset import import_bundle
from app.db.import_models import import_run
from app.db.session import Database
from tests.db.test_real_data_api import calce_bundle, nasa_samples
from tests.support import bundles as b
from tests.support.database import (
    DbTestSettings,
    UnsafeDatabaseError,
    assert_disposable_name,
    disposable_url,
)
from tests.support.model_runs import write_run

CI_DATABASE = "volterra_ci"
_CI_HOSTS = frozenset({"localhost", "127.0.0.1"})


def write(data_dir: Path) -> list[Path]:
    return [b.write_bundle(data_dir, tamper=nasa_samples), calce_bundle(data_dir)]


def assert_ci_target(dsn: str | None, env: Mapping[str, str]) -> str:
    """Return ``dsn`` only in GitHub Actions and only if it names the local ``volterra_ci``."""
    if env.get("CI") != "true" or env.get("GITHUB_ACTIONS") != "true":
        raise UnsafeDatabaseError("ci-import runs only in GitHub Actions (CI=true)")
    if not dsn:
        raise UnsafeDatabaseError("ci-import needs DATABASE_URL")
    try:
        url = make_url(dsn)
    except ArgumentError as exc:
        raise UnsafeDatabaseError("ci-import refuses an unparsable DATABASE_URL") from exc
    if url.database != CI_DATABASE:
        raise UnsafeDatabaseError(f"ci-import writes only to {CI_DATABASE!r}, not {url.database!r}")
    if url.host not in _CI_HOSTS:
        raise UnsafeDatabaseError("ci-import writes only to the local CI service database")
    return dsn


async def _import_all(dsn: str, data_dir: Path, *, expect_unchanged: bool = False) -> None:
    database = Database(dsn)
    try:
        for bundle in write(data_dir):
            async with database.session() as session:
                result = await import_bundle(session, bundle, data_dir)
            if expect_unchanged and not result.unchanged:
                raise SystemExit(f"re-import of {result.slug} was not a no-op")
            print(f"{result.slug}: {result.batteries} battery, {result.cycles_imported} cycles")
        run_dir = data_dir / "runs" / "generated"
        if not run_dir.exists():
            write_run(run_dir)
        async with database.session() as session:
            run = await import_run(session, run_dir)
        if expect_unchanged and not run.unchanged:
            raise SystemExit(f"re-import of model run {run.run_id} was not a no-op")
        print(f"model run {run.run_id}: {run.predictions} predictions (generated values)")
    finally:
        await database.dispose()


async def ci_import(dsn: str | None, data_dir: Path, env: Mapping[str, str]) -> None:
    """Guarded CI import (checked before anything is written), then a no-op re-import."""
    target = assert_ci_target(dsn, env)
    await _import_all(target, data_dir)
    await _import_all(target, data_dir, expect_unchanged=True)
    print("re-import unchanged (idempotent)")


async def load(name: str, data_dir: Path) -> None:
    admin = DbTestSettings().test_database_url
    if admin is None:
        raise SystemExit("TEST_DATABASE_URL is not set")
    await _import_all(
        disposable_url(admin.get_secret_value(), assert_disposable_name(name)), data_dir
    )


def main(argv: list[str]) -> int:
    from app.core.config import get_settings

    match argv:
        case ["write", data_dir]:
            for path in write(Path(data_dir)):
                print(path)
        case ["import", name, data_dir]:
            asyncio.run(load(name, Path(data_dir)))
        case ["ci-import", data_dir]:
            asyncio.run(ci_import(get_settings().database_dsn(), Path(data_dir), os.environ))
        case _:
            print(__doc__, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":  # pragma: no cover - developer tool
    sys.exit(main(sys.argv[1:]))
