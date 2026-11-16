"""Hosting providers issue ``postgres://`` URLs; the app connects with asyncpg."""

from __future__ import annotations

import pytest

from app.core.config import normalise_dsn


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        ("postgresql://u:p@h/db?sslmode=require", "postgresql+asyncpg://u:p@h/db?ssl=require"),
        ("postgresql+asyncpg://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        (
            "postgresql+asyncpg://u:p@h/db?a=1&sslmode=require",
            "postgresql+asyncpg://u:p@h/db?a=1&ssl=require",
        ),
        ("sqlite:///x.db", "sqlite:///x.db"),
    ],
)
def test_normalise_dsn(given: str, expected: str) -> None:
    assert normalise_dsn(given) == expected
