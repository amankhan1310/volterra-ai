"""Application settings, read from environment variables and ``backend/.env``.

Secrets (the database URL contains the password) are held as :class:`~pydantic.SecretStr`, so
they never appear in ``repr``, logs or error messages. Use :meth:`Settings.database_dsn` to
obtain the plain value when connecting.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
        # Validation errors must never echo raw input: it can hold the database URL.
        hide_input_in_errors=True,
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
    #: Root of the local dataset store (raw/ and processed/); sample-level data of imported real
    #: datasets is read from there. Unset: sample endpoints answer 503 ``samples_unavailable``.
    data_dir: Path | None = Field(default=None, validation_alias="VOLTERRA_DATA_DIR")

    #: Who may read and change saved scenarios:
    #: ``session`` - each browser session owns its scenarios (anonymous HttpOnly cookie);
    #: ``shared`` - one shared list per battery (local single-user development only);
    #: ``disabled`` - scenarios are read-only (writes answer 403).
    #: Unset: ``session`` in production, ``shared`` otherwise. ``shared`` is refused in production.
    scenario_access: Literal["session", "shared", "disabled"] | None = Field(
        default=None, validation_alias="VOLTERRA_SCENARIO_ACCESS"
    )
    #: Saved scenarios per battery and owner (session, or the shared list).
    scenario_limit: int = Field(default=4, ge=1, le=100, validation_alias="VOLTERRA_SCENARIO_LIMIT")
    #: Upper bound on all saved scenarios in the database (protects a public deployment).
    scenario_total_limit: int = Field(
        default=1000, ge=1, le=1_000_000, validation_alias="VOLTERRA_SCENARIO_TOTAL_LIMIT"
    )
    #: Per-client request rate limiting. Unset: on in production, off otherwise.
    rate_limit_enabled: bool | None = Field(default=None, validation_alias="VOLTERRA_RATE_LIMIT")
    rate_limit_reads_per_minute: int = Field(
        default=1200, ge=1, validation_alias="VOLTERRA_RATE_LIMIT_READS"
    )
    rate_limit_writes_per_minute: int = Field(
        default=30, ge=1, validation_alias="VOLTERRA_RATE_LIMIT_WRITES"
    )
    #: All clients together (writes only): a ceiling that client-key spoofing cannot bypass.
    rate_limit_global_writes_per_minute: int = Field(
        default=120, ge=1, validation_alias="VOLTERRA_RATE_LIMIT_GLOBAL_WRITES"
    )
    #: Trusted proxies that append to X-Forwarded-For in front of the app. 0 uses the right-most
    #: entry (the address the hosting provider's proxy saw), which a client cannot forge.
    trusted_proxy_hops: int = Field(
        default=0, ge=0, le=5, validation_alias="VOLTERRA_TRUSTED_PROXY_HOPS"
    )
    #: Largest accepted request body in bytes; larger bodies answer 413.
    max_body_bytes: int = Field(
        default=16_384, ge=1024, le=1_048_576, validation_alias="VOLTERRA_MAX_BODY_BYTES"
    )

    #: HMAC key that signs the anonymous scenario-session cookie (at least 32 characters).
    #: Required in production with session access; elsewhere a random per-process key is used
    #: when unset (sessions then end when the process restarts).
    session_secret: SecretStr | None = Field(
        default=None, validation_alias="VOLTERRA_SESSION_SECRET"
    )

    @model_validator(mode="after")
    def _production_rules(self) -> Settings:
        if self.environment == "production" and self.scenario_access == "shared":
            raise ValueError(
                "VOLTERRA_SCENARIO_ACCESS=shared is not allowed in production "
                "(anyone could change everyone's scenarios); use session or disabled"
            )
        secret = self.session_secret.get_secret_value() if self.session_secret else ""
        if secret and len(secret) < 32:
            raise ValueError("VOLTERRA_SESSION_SECRET must be at least 32 characters")
        if (
            self.environment == "production"
            and self.effective_scenario_access == "session"
            and not secret
        ):
            raise ValueError("VOLTERRA_SESSION_SECRET is required in production")
        return self

    @property
    def effective_scenario_access(self) -> Literal["session", "shared", "disabled"]:
        if self.scenario_access is not None:
            return self.scenario_access
        return "session" if self.environment == "production" else "shared"

    @property
    def effective_rate_limit(self) -> bool:
        if self.rate_limit_enabled is not None:
            return self.rate_limit_enabled
        return self.environment == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        """Comma-separated ``VOLTERRA_CORS_ORIGINS`` as a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def database_dsn(self) -> str | None:
        """The plain database URL (contains credentials: never log it), for asyncpg."""
        return normalise_dsn(self.database_url.get_secret_value()) if self.database_url else None


def normalise_dsn(url: str) -> str:
    """Accept the ``postgres://`` / ``postgresql://`` URLs hosting providers issue (Render).

    The scheme becomes ``postgresql+asyncpg://`` and libpq's ``sslmode`` query parameter, which
    asyncpg does not understand, becomes asyncpg's ``ssl``. Other URLs pass through unchanged.
    """
    for scheme in ("postgres://", "postgresql://"):
        if url.startswith(scheme):
            url = "postgresql+asyncpg://" + url[len(scheme) :]
            break
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("?sslmode=", "?ssl=").replace("&sslmode=", "&ssl=")
    return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
