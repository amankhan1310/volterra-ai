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
from app.core.guard import FixedWindowCounter, client_key, request_class
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


SECRET = "g" * 40
CSRF = {"X-Volterra-Client": "web"}
SIM_PARAMS = {
    "temp_c": 25,
    "c_rate": 1,
    "dod_pct": 80,
    "horizon_cycles": 100,
    "start_soh_pct": 90,
    "eol_pct": 80,
}
SCENARIO = {"name": "S", "params": {**SIM_PARAMS, "horizon_cycles": 600}}


@pytest.fixture
async def guarded_app(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[Any, Clock, Any]]:
    """Session scenarios, rate limiting on, tiny limits, a fake clock."""
    clock = Clock()
    monkeypatch.setattr("app.core.guard.time.monotonic", clock)
    app, repo = memory_app(
        scenario_access="session",
        session_secret=SECRET,
        rate_limit_enabled=True,
        rate_limit_reads_per_minute=3,
        rate_limit_writes_per_minute=2,
        rate_limit_global_writes_per_minute=3,
        rate_limit_calc_per_minute=4,
        rate_limit_global_calc_per_minute=6,
    )
    yield app, clock, repo


@pytest.fixture
async def guarded(
    guarded_app: tuple[Any, Clock, Any],
) -> AsyncIterator[tuple[httpx.AsyncClient, Clock, Any]]:
    app, clock, repo = guarded_app
    async with client_for(app) as client:
        yield client, clock, repo


async def visitor(app: Any, address: str) -> AsyncIterator[httpx.AsyncClient]:
    """A browser (keeps cookies) behind ``address``; its first request obtains a session."""
    async with client_for(app) as client:
        client.headers["X-Forwarded-For"] = address
        first = await client.get("/api/v1/datasets")
        assert first.status_code == 200 and "volterra_session" in client.cookies
        yield client


def test_request_classes() -> None:
    sim = "/api/v1/batteries/0f0e/simulate"
    assert request_class("POST", sim) == "calc"
    assert request_class("GET", sim) == "read"
    assert request_class("POST", "/api/v1/batteries/0f0e/scenarios") == "write"
    assert request_class("PATCH", "/api/v1/scenarios/1") == "write"
    assert request_class("DELETE", "/api/v1/scenarios/1") == "write"
    assert request_class("POST", "/api/v1/batteries/0f0e/simulate/x") == "write"
    assert request_class("OPTIONS", "/api/v1/batteries/0f0e/scenarios") == "read"


async def test_the_first_api_response_issues_a_session_cookie(
    guarded_app: tuple[Any, Clock, Any],
) -> None:
    app, _, repo = guarded_app
    async with client_for(app) as client:
        health = await client.get("/api/v1/health/live")
        assert "set-cookie" not in health.headers  # health checks never get sessions
        first = await client.get("/api/v1/datasets")
        cookie = first.headers["set-cookie"]
        assert cookie.startswith("volterra_session=") and "HttpOnly" in cookie
        assert "SameSite=lax" in cookie and "Path=/api/v1" in cookie
        assert first.headers["cache-control"] == "no-store"
        again = await client.get("/api/v1/datasets")
        assert "set-cookie" not in again.headers  # a valid cookie is kept, not replaced
    # A save as the very first request belongs to the session issued with that response.
    async with client_for(app) as fresh:
        saved = await fresh.post(
            f"/api/v1/batteries/{repo.battery.id}/scenarios", json=SCENARIO, headers=CSRF
        )
        assert saved.status_code == 201
        assert len(saved.headers.get_list("set-cookie")) == 1
        listed = (await fresh.get(f"/api/v1/batteries/{repo.battery.id}/scenarios")).json()
        assert [s["id"] for s in listed["items"]] == [saved.json()["id"]]


async def test_sessions_behind_one_shared_address_have_independent_allowances(
    guarded_app: tuple[Any, Clock, Any],
) -> None:
    """Many visitors behind one proxy address (e.g. a Vercel edge): one cannot exhaust another."""
    app, clock, _ = guarded_app
    shared = "203.0.113.50"
    async for alice in visitor(app, shared):
        async for bob in visitor(app, shared):
            for _ in range(3):
                assert (await alice.get("/api/v1/datasets")).status_code == 200
            limited = await alice.get("/api/v1/datasets")
            assert limited.status_code == 429
            assert limited.json() == {
                "error": {
                    "code": "rate_limited",
                    "message": "Too many requests; please retry later",
                }
            }
            assert 1 <= int(limited.headers["retry-after"]) <= 60
            # Bob shares Alice's address but not her allowance.
            for _ in range(3):
                assert (await bob.get("/api/v1/datasets")).status_code == 200
            assert (await alice.get("/api/v1/health/ready")).status_code in (200, 503)  # exempt
            clock.now += 60
            assert (await alice.get("/api/v1/datasets")).status_code == 200


async def test_spoofed_forwarded_headers_and_forged_cookies_do_not_bypass_limits(
    guarded_app: tuple[Any, Clock, Any],
) -> None:
    """Without a valid session, the key is the right-most X-Forwarded-For entry (appended by
    the hosting proxy): rotating the client-supplied entries or sending forged cookies gives
    no new allowance."""
    app, _, _ = guarded_app
    codes = []
    async with client_for(app) as client:
        for i in range(4):
            client.cookies.clear()  # a script that discards cookies
            forged = {"Cookie": f"volterra_session={'0' * 32}.forged"} if i % 2 else {}
            r = await client.get(
                "/api/v1/datasets",
                headers={"X-Forwarded-For": f"6.6.6.{i}, 198.51.100.7", **forged},
            )
            codes.append(r.status_code)
    assert codes == [200, 200, 200, 429]  # 3 reads per network address


async def test_simulations_use_the_calculation_budget_not_the_write_budget(
    guarded_app: tuple[Any, Clock, Any],
) -> None:
    app, _, repo = guarded_app
    sim = f"/api/v1/batteries/{repo.battery.id}/simulate"
    body = {"params": SIM_PARAMS, "include_trajectories": False}
    scenarios = f"/api/v1/batteries/{repo.battery.id}/scenarios"
    async for alice in visitor(app, "198.51.100.1"):
        sims = [(await alice.post(sim, json=body, headers=CSRF)).status_code for _ in range(5)]
        assert sims == [200, 200, 200, 200, 429]  # 4 calculations per client
        # The write allowance is untouched by those calculations ...
        saves = [
            (await alice.post(scenarios, json=SCENARIO, headers=CSRF)).status_code for _ in range(3)
        ]
        assert saves == [201, 201, 429]  # ... and still limited (2 writes per client)
        async for bob in visitor(app, "198.51.100.2"):
            # All clients together: 6 calculations (Alice used 4) and 3 writes (Alice used 2).
            more = [(await bob.post(sim, json=body, headers=CSRF)).status_code for _ in range(3)]
            assert more == [200, 200, 429]
            writes = [
                (await bob.post(scenarios, json=SCENARIO, headers=CSRF)).status_code
                for _ in range(2)
            ]
            assert writes == [201, 429]


async def test_scenario_mutations_share_the_per_client_write_limit(
    guarded_app: tuple[Any, Clock, Any],
) -> None:
    app, _, repo = guarded_app
    scenarios = f"/api/v1/batteries/{repo.battery.id}/scenarios"
    async for alice in visitor(app, "198.51.100.3"):
        created = await alice.post(scenarios, json=SCENARIO, headers=CSRF)
        assert created.status_code == 201
        sid = created.json()["id"]
        renamed = await alice.patch(f"/api/v1/scenarios/{sid}", json={"name": "R"}, headers=CSRF)
        assert renamed.status_code == 200
        deleted = await alice.delete(f"/api/v1/scenarios/{sid}", headers=CSRF)
        assert deleted.status_code == 429  # create + rename used the 2 writes


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


def test_calculation_budget_covers_continuous_simulator_use() -> None:
    """The simulator re-runs 150 ms after the last change (frontend SIMULATE_DEBOUNCE_MS), so a
    user dragging a slider sends at most ~400 calculations a minute; the default budget must
    exceed that, and the write budgets must stay stricter."""
    s = make_settings()
    max_per_minute = 60_000 / 150
    assert s.rate_limit_calc_per_minute > max_per_minute
    assert s.rate_limit_global_calc_per_minute >= s.rate_limit_calc_per_minute
    assert s.rate_limit_writes_per_minute < s.rate_limit_calc_per_minute
    assert s.rate_limit_global_writes_per_minute < s.rate_limit_global_calc_per_minute
