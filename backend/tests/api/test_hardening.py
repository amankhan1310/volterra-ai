"""Deployment hardening: health probes, request guard (rate limits, body size, headers),
production configuration rules and the session signer."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.guard import FixedWindowCounter, client_key
from app.core.sessions import SessionSigner
from tests.support.api import client_for, make_settings, memory_app

pytestmark = pytest.mark.anyio


class FakeDatabase:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def ping(self) -> float:
        if self.error is not None:
            raise self.error
        return 1.5


# --- health ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("database", "ready_status", "db_status"),
    [
        (FakeDatabase(), 200, "ok"),
        (
            FakeDatabase(OSError("connect to postgresql://user:secret@db:5432 failed")),
            503,
            "unavailable",
        ),
        (None, 503, "not_configured"),
    ],
)
async def test_liveness_and_readiness(
    database: FakeDatabase | None, ready_status: int, db_status: str
) -> None:
    app, _ = memory_app()
    app.state.database = database
    async with client_for(app) as client:
        live = await client.get("/api/v1/health/live")
        assert live.status_code == 200 and live.json() == {"status": "ok"}
        ready = await client.get("/api/v1/health/ready")
        assert ready.status_code == ready_status
        assert ready.json()["database"] == db_status
        health = await client.get("/api/v1/health")
        assert health.status_code == 200 and health.json()["database"]["status"] == db_status
        for r in (ready, health):
            assert (
                "secret" not in r.text and "postgresql://" not in r.text and "failed" not in r.text
            )


# --- request guard --------------------------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
async def guarded(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[httpx.AsyncClient, Clock, Any]]:
    """An app with rate limiting on and tiny limits, driven by a fake clock."""
    clock = Clock()
    monkeypatch.setattr("app.core.guard.time.monotonic", clock)
    app, repo = memory_app(
        rate_limit_enabled=True,
        rate_limit_reads_per_minute=3,
        rate_limit_writes_per_minute=2,
        rate_limit_global_writes_per_minute=3,
    )
    async with client_for(app) as client:
        yield client, clock, repo


async def test_reads_are_rate_limited_per_client(
    guarded: tuple[httpx.AsyncClient, Clock, Any],
) -> None:
    client, clock, _ = guarded
    a = {"X-Forwarded-For": "203.0.113.1"}
    for _ in range(3):
        assert (await client.get("/api/v1/datasets", headers=a)).status_code == 200
    limited = await client.get("/api/v1/datasets", headers=a)
    assert limited.status_code == 429
    assert limited.json() == {
        "error": {"code": "rate_limited", "message": "Too many requests; please retry later"}
    }
    assert 1 <= int(limited.headers["retry-after"]) <= 60
    # Another client is unaffected; health is exempt; the next window resets.
    assert (
        await client.get("/api/v1/datasets", headers={"X-Forwarded-For": "203.0.113.2"})
    ).status_code == 200
    assert (await client.get("/api/v1/health/live", headers=a)).status_code == 200
    clock.now += 60
    assert (await client.get("/api/v1/datasets", headers=a)).status_code == 200


async def test_writes_have_per_client_and_global_limits(
    guarded: tuple[httpx.AsyncClient, Clock, Any],
) -> None:
    client, _, repo = guarded
    url = f"/api/v1/batteries/{repo.battery.id}/simulate"
    params = {
        "temp_c": 25,
        "c_rate": 1,
        "dod_pct": 80,
        "horizon_cycles": 100,
        "start_soh_pct": 90,
        "eol_pct": 80,
    }
    body = {"params": params, "include_trajectories": False}
    codes = [
        (await client.post(url, json=body, headers={"X-Forwarded-For": "198.51.100.1"})).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]  # 2 per client
    # Global ceiling (3 writes/min) holds even when each request claims a new address.
    spoofed = [
        (await client.post(url, json=body, headers={"X-Forwarded-For": f"10.0.0.{i}"})).status_code
        for i in range(3)
    ]
    assert spoofed == [200, 429, 429]  # 3 per minute in total


async def test_oversized_bodies_are_rejected(guarded: tuple[httpx.AsyncClient, Clock, Any]) -> None:
    client, _, repo = guarded
    url = f"/api/v1/batteries/{repo.battery.id}/scenarios"
    big = b'{"name": "' + b"x" * 20_000 + b'"}'
    r = await client.post(url, content=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"

    async def chunks() -> AsyncIterator[bytes]:  # no Content-Length (chunked)
        for _ in range(20):
            yield b"x" * 1000

    r = await client.post(url, content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


async def test_security_headers_and_no_store() -> None:
    app, repo = memory_app()
    async with client_for(app) as client:
        r = await client.get("/api/v1/datasets")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "no-referrer"
        s = await client.get(f"/api/v1/batteries/{repo.battery.id}/scenarios")
        assert s.headers["cache-control"] == "no-store"


async def test_cors_allows_only_listed_origins_without_credentials() -> None:
    app, _ = memory_app(cors_origins="https://demo.example")
    async with client_for(app) as client:
        pre = {
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-volterra-client",
        }
        ok = await client.options(
            "/api/v1/datasets", headers={"Origin": "https://demo.example", **pre}
        )
        assert ok.status_code == 200
        assert ok.headers["access-control-allow-origin"] == "https://demo.example"
        assert "access-control-allow-credentials" not in ok.headers
        bad = await client.options(
            "/api/v1/datasets", headers={"Origin": "https://evil.example", **pre}
        )
        assert bad.status_code == 400
        assert "access-control-allow-origin" not in bad.headers


def test_client_key() -> None:
    scope: dict[str, Any] = {
        "headers": [(b"x-forwarded-for", b"6.6.6.6, 1.2.3.4")],
        "client": ("9.9.9.9", 1),
    }
    assert client_key(scope, 0) == "1.2.3.4"  # appended by the platform proxy
    assert client_key(scope, 1) == "6.6.6.6"
    assert client_key(scope, 5) == "6.6.6.6"
    assert client_key({"headers": [], "client": ("9.9.9.9", 1)}, 0) == "9.9.9.9"
    assert client_key({"headers": []}, 0) == "unknown"


def test_counter_memory_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.guard.MAX_TRACKED_KEYS", 3)
    now = [0.0]
    counter = FixedWindowCounter(1, clock=lambda: now[0])
    for k in "abc":
        assert counter.hit(k) is None
    now[0] = 61.0  # new window: old entries are dropped before adding a fourth key
    assert counter.hit("d") is None
    assert set(counter._counts) == {"d"}


# --- configuration --------------------------------------------------------------------------


def test_defaults_keep_local_development_unchanged() -> None:
    s = make_settings(environment="development")
    assert s.effective_scenario_access == "shared" and s.effective_rate_limit is False


def test_production_requires_session_secret_and_refuses_shared_scenarios() -> None:
    with pytest.raises(ValidationError, match="VOLTERRA_SESSION_SECRET is required"):
        make_settings(environment="production")
    with pytest.raises(ValidationError, match="not allowed in production"):
        make_settings(environment="production", scenario_access="shared", session_secret="s" * 32)
    with pytest.raises(ValidationError, match="at least 32"):
        make_settings(session_secret="short")
    s = make_settings(environment="production", session_secret="s" * 32)
    assert s.effective_scenario_access == "session" and s.effective_rate_limit is True
    assert "s" * 32 not in repr(s)
    # Read-only scenarios need no secret.
    assert (
        make_settings(environment="production", scenario_access="disabled").session_secret is None
    )


def test_configuration_errors_never_echo_the_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOLTERRA_ENV", "production")  # no session secret: invalid
    monkeypatch.setenv("DATABASE_URL", "postgresql://volterra:hunter2@db.internal:5432/volterra")
    with pytest.raises(ValidationError) as info:
        Settings(_env_file=None)  # type: ignore[call-arg]
    message = str(info.value)
    assert "VOLTERRA_SESSION_SECRET is required" in message
    assert "hunter2" not in message and "db.internal" not in message


def test_settings_read_the_new_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in {
        "VOLTERRA_ENV": "production",
        "VOLTERRA_SESSION_SECRET": "x" * 48,
        "VOLTERRA_SCENARIO_LIMIT": "4",
        "VOLTERRA_RATE_LIMIT_READS": "600",
        "VOLTERRA_TRUSTED_PROXY_HOPS": "1",
    }.items():
        monkeypatch.setenv(k, v)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert (
        s.environment,
        s.scenario_limit,
        s.rate_limit_reads_per_minute,
        s.trusted_proxy_hops,
    ) == (
        "production",
        4,
        600,
        1,
    )


# --- signer ---------------------------------------------------------------------------------


def test_signer_round_trip_and_rejections() -> None:
    signer = SessionSigner(b"a" * 32)
    sid, value = signer.issue()
    assert isinstance(sid, uuid.UUID) and sid.version == 4
    assert signer.verify(value) == sid
    other_sid, _ = signer.issue()
    assert other_sid != sid
    for bad in (
        None,
        "",
        "x",
        value + "x",
        value.upper(),
        "a.b.c",
        "z" * 200,
        SessionSigner(b"b" * 32).issue()[1],
    ):
        assert signer.verify(bad) is None
    with pytest.raises(ValueError):
        SessionSigner(b"short")


async def test_database_outage_is_a_retryable_503_without_details() -> None:
    from app.api.deps import get_repository

    class DownRepository:
        def __getattr__(self, name: str) -> Any:
            async def fail(*_: Any, **__: Any) -> Any:
                raise ConnectionRefusedError("connect to postgresql://u:hunter2@db:5432 refused")

            return fail

    app, _ = memory_app()
    app.dependency_overrides[get_repository] = lambda: DownRepository()
    async with client_for(app, raise_app_exceptions=False) as client:
        r = await client.get("/api/v1/batteries")
    assert r.status_code == 503 and r.headers["retry-after"] == "10"
    assert r.json() == {
        "error": {
            "code": "database_unavailable",
            "message": "The database is temporarily unavailable",
        }
    }
    assert "hunter2" not in r.text
