"""Alembic configuration for tests (URL passed via attributes, never via alembic.ini)."""

from __future__ import annotations

import io
from pathlib import Path

from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config(database_url: str, *, output: io.StringIO | None = None) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"), output_buffer=output)
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    return config
