"""The CI write-only import path may only ever reach the local ``volterra_ci`` service database."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.support.database import UnsafeDatabaseError
from tests.support.fixture_bundles import CI_DATABASE, assert_ci_target, ci_import, main

GHA = {"CI": "true", "GITHUB_ACTIONS": "true"}
CI_DSN = f"postgresql+asyncpg://volterra:secret@localhost:5432/{CI_DATABASE}"


def test_accepts_only_the_local_ci_database_in_github_actions() -> None:
    assert assert_ci_target(CI_DSN, GHA) == CI_DSN
    loopback = CI_DSN.replace("localhost", "127.0.0.1")
    assert assert_ci_target(loopback, GHA) == loopback


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql+asyncpg://volterra:secret@localhost:5432/volterra",  # the development database
        "postgresql+asyncpg://volterra:secret@localhost:5432/postgres",
        "postgresql+asyncpg://volterra:secret@localhost:5432/volterra_test_0123abcd",
        "postgresql+asyncpg://volterra:secret@localhost:5432/volterra_ci_copy",
        "postgresql+asyncpg://volterra:secret@localhost:5432/VOLTERRA_CI",
        "postgresql+asyncpg://volterra:secret@localhost:5432/",
        "postgresql+asyncpg://volterra:secret@db.example.com:5432/volterra_ci",  # not local
        "postgresql+asyncpg://volterra:secret@/volterra_ci",  # no host
        "not a url",
        "",
        None,
    ],
)
def test_refuses_every_other_database(dsn: str | None) -> None:
    with pytest.raises(UnsafeDatabaseError):
        assert_ci_target(dsn, GHA)


@pytest.mark.parametrize(
    "env",
    [{}, {"CI": "true"}, {"GITHUB_ACTIONS": "true"}, {"CI": "1", "GITHUB_ACTIONS": "true"}],
)
def test_refuses_outside_github_actions(env: dict[str, str]) -> None:
    with pytest.raises(UnsafeDatabaseError, match="GitHub Actions"):
        assert_ci_target(CI_DSN, env)


def test_refused_target_writes_nothing(tmp_path: Path) -> None:
    dev = "postgresql+asyncpg://volterra:secret@localhost:5432/volterra"
    with pytest.raises(UnsafeDatabaseError):
        asyncio.run(ci_import(dev, tmp_path / "data", GHA))
    with pytest.raises(UnsafeDatabaseError):
        asyncio.run(ci_import(CI_DSN, tmp_path / "data", {}))
    assert list(tmp_path.iterdir()) == []


def test_command_line_rejects_unknown_modes(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ci-import"]) == 2
    assert main(["import", "volterra"]) == 2
    assert "ci-import" in capsys.readouterr().err


def test_command_line_ci_import_refuses_outside_ci(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(UnsafeDatabaseError):
        main(["ci-import", str(tmp_path / "data")])
    assert list(tmp_path.iterdir()) == []
