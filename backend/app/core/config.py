"""Application settings, read from environment variables and ``backend/.env``.

Secrets (the database URL contains the password) are held as :class:`~pydantic.SecretStr`, so
they never appear in ``repr``, logs or error messages. Use :meth:`Settings.database_dsn` to
obtain the plain value when connecting.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

API_VERSION = "0.3.0"
API_PREFIX = "/api/v1"
BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    environment: Literal["development", "test", "production"] = Field(
        default="development", validation_alias="VOLTERRA_ENV"
    )
    database_url: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")
    cors_origins: str = Field(
        default="http://localhost:5173", validation_alias="VOLTERRA_CORS_ORIGINS"
    )
    analysis_cache_size: int = Field(
        default=32, ge=1, le=1024, validation_alias="VOLTERRA_ANALYSIS_CACHE_SIZE"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        """Comma-separated ``VOLTERRA_CORS_ORIGINS`` as a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def database_dsn(self) -> str | None:
        """The plain database URL (contains credentials: never log it)."""
        return self.database_url.get_secret_value() if self.database_url else None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
