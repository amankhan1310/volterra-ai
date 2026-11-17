"""Scenario access control: anonymous signed sessions, CSRF, read-only mode and atomic limits.

Runs against the in-memory repository and (marked ``db``) a disposable PostgreSQL database.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.core.sessions import COOKIE_NAME, SessionSigner
from app.db.session import Database
from app.main import create_app
from tests.support.api import client_for, make_settings, memory_app
from tests.support.database import assert_disposable

pytestmark = pytest.mark.anyio

SECRET = "s" * 40
CSRF = {"X-Volterra-Client": "web"}
PARAMS = {
    "temp_c": 25.0,
    "c_rate": 1.0,
    "dod_pct": 80.0,
    "horizon_cycles": 600,
    "start_soh_pct": 86.1,
    "eol_pct": 80.0,
}
AppFactory = Callable[..., AbstractAsyncContextManager[tuple[FastAPI, str]]]


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.db)])
def app_factory(request: pytest.FixtureRequest) -> AppFactory:
    """Builds an app in session mode (settings overridable) plus the synthetic battery id."""

    @asynccontextmanager
    async def build(**settings: Any) -> AsyncIterator[tuple[FastAPI, str]]:
        values = {"scenario_access": "session", "session_secret": SECRET, **settings}
        if request.param == "memory":
            app, repo = memory_app(**values)
            yield app, str(repo.battery.id)
            return
        url: str = request.getfixturevalue("seeded_database_url")
        assert_disposable(url)
        database = Database(url)
        try:
            app = create_app(make_settings(**values), database=database)
            async with client_for(app) as c:
                battery_id = (await c.get("/api/v1/batteries")).json()["items"][0]["id"]
            yield app, battery_id
        finally:
            async with database.engine.begin() as conn:
                await conn.execute(text("DELETE FROM scenarios"))
            await database.dispose()

    return build


def base(battery_id: str) -> str:
    return f"/api/v1/batteries/{battery_id}/scenarios"


async def save(client: httpx.AsyncClient, battery_id: str, name: str) -> httpx.Response:
    return await client.post(base(battery_id), json={"name": name, "params": PARAMS}, headers=CSRF)


async def test_sessions_only_see_and_change_their_own_scenarios(app_factory: AppFactory) -> None:
    async with app_factory() as (app, battery_id), client_for(app) as alice, client_for(app) as bob:
        listed = await alice.get(base(battery_id))
        assert listed.json() == {"items": []}
        # The session cookie arrives with the browser's first API response.
        cookie = listed.headers["set-cookie"]
        assert f"{COOKIE_NAME}=" in cookie and "HttpOnly" in cookie
        assert "SameSite=lax" in cookie and "Path=/api/v1" in cookie
        assert "Secure" not in cookie  # not production
        created = await save(alice, battery_id, "Alice's")
        assert created.status_code == 201 and "set-cookie" not in created.headers
        sid = created.json()["id"]
        assert [s["id"] for s in (await alice.get(base(battery_id))).json()["items"]] == [sid]

        # Another browser (no cookie) sees nothing and cannot read, change or delete it.
        assert (await bob.get(base(battery_id))).json() == {"items": []}
        assert (await bob.get(f"/api/v1/scenarios/{sid}")).status_code == 404
        assert (
            await bob.patch(f"/api/v1/scenarios/{sid}", json={"name": "x"}, headers=CSRF)
        ).status_code == 404
        assert (await bob.delete(f"/api/v1/scenarios/{sid}", headers=CSRF)).status_code == 404
        # Bob's own session is separate, with its own limit.
        assert (await save(bob, battery_id, "Bob's")).status_code == 201
        assert [s["name"] for s in (await bob.get(base(battery_id))).json()["items"]] == ["Bob's"]

        # The owner can still read, rename and delete.
        assert (await alice.get(f"/api/v1/scenarios/{sid}")).status_code == 200
        renamed = await alice.patch(
            f"/api/v1/scenarios/{sid}", json={"name": "Renamed"}, headers=CSRF
        )
        assert renamed.status_code == 200 and renamed.json()["name"] == "Renamed"
        assert (await alice.delete(f"/api/v1/scenarios/{sid}", headers=CSRF)).status_code == 204


async def test_forged_or_tampered_cookies_are_not_sessions(app_factory: AppFactory) -> None:
    async with app_factory() as (app, battery_id), client_for(app) as owner:
        sid = (await save(owner, battery_id, "Mine")).json()["id"]
        value = owner.cookies[COOKIE_NAME]
        session_hex, signature = value.split(".")
        other_key = SessionSigner(b"k" * 32).issue()[1]  # signed with a different key
        flipped = "1" if session_hex[-1] == "0" else "0"  # always a different id
        forged = [
            f"{session_hex}.{'A' * len(signature)}",  # right id, wrong signature
            f"{session_hex[:-1]}{flipped}.{signature}",  # changed id, old signature
            other_key,
            session_hex,
            "garbage",
        ]
        assert value not in forged  # every variant really differs from the genuine cookie
        for bad in forged:
            async with client_for(app) as attacker:
                attacker.cookies.set(COOKIE_NAME, bad)
                assert (await attacker.get(base(battery_id))).json() == {"items": []}
                assert (await attacker.get(f"/api/v1/scenarios/{sid}")).status_code == 404
                assert (
                    await attacker.delete(f"/api/v1/scenarios/{sid}", headers=CSRF)
                ).status_code == 404
        assert (await owner.get(f"/api/v1/scenarios/{sid}")).status_code == 200


async def test_writes_need_the_csrf_header_and_an_allowed_origin(app_factory: AppFactory) -> None:
    async with (
        app_factory(cors_origins="https://demo.example") as (app, battery_id),
        client_for(app) as client,
    ):
        body = {"name": "x", "params": PARAMS}
        missing = await client.post(base(battery_id), json=body)
        assert missing.status_code == 403
        assert missing.json()["error"]["code"] == "csrf_rejected"
        wrong = await client.post(base(battery_id), json=body, headers={"X-Volterra-Client": "1"})
        assert wrong.status_code == 403
        evil = await client.post(
            base(battery_id), json=body, headers={**CSRF, "Origin": "https://evil.example"}
        )
        assert evil.status_code == 403
        for origin in ("http://test", "https://demo.example"):  # own origin, allow-listed
            ok = await client.post(base(battery_id), json=body, headers={**CSRF, "Origin": origin})
            assert ok.status_code == 201
        assert len((await client.get(base(battery_id))).json()["items"]) == 2


async def test_production_cookie_is_secure(app_factory: AppFactory) -> None:
    async with (
        app_factory(environment="production", rate_limit_enabled=False) as (app, battery_id),
        client_for(app) as client,
    ):
        created = await save(client, battery_id, "x")
        assert created.status_code == 201 and "Secure" in created.headers["set-cookie"]


async def test_read_only_mode(app_factory: AppFactory) -> None:
    async with (
        app_factory(scenario_access="disabled") as (app, battery_id),
        client_for(app) as client,
    ):
        r = await save(client, battery_id, "x")
        assert r.status_code == 403 and r.json()["error"]["code"] == "scenarios_read_only"
        assert (await client.get(base(battery_id))).json() == {"items": []}


async def test_total_limit_across_sessions(app_factory: AppFactory) -> None:
    async with app_factory(scenario_total_limit=3) as (app, battery_id):
        results = []
        for i in range(5):
            async with client_for(app) as client:
                results.append((await save(client, battery_id, f"S{i}")).status_code)
        assert results == [201, 201, 201, 409, 409]


@pytest.mark.db
async def test_concurrent_creates_cannot_exceed_the_limits(
    seeded_database_url: str,
) -> None:
    """Many simultaneous requests, each on its own database session: the advisory lock makes
    count-and-insert atomic, so exactly the limit succeeds."""
    assert_disposable(seeded_database_url)
    database = Database(seeded_database_url)
    try:
        app = create_app(
            make_settings(scenario_access="session", session_secret=SECRET), database=database
        )
        async with client_for(app) as client:
            battery_id = (await client.get("/api/v1/batteries")).json()["items"][0]["id"]
            await save(client, battery_id, "first")  # establishes the session cookie
            results = await asyncio.gather(*(save(client, battery_id, f"S{i}") for i in range(12)))
            codes = sorted(r.status_code for r in results)
            assert codes == [201] * 3 + [409] * 9
            assert len((await client.get(base(battery_id))).json()["items"]) == 4

        total_app = create_app(
            make_settings(
                scenario_access="session", session_secret=SECRET, scenario_total_limit=10
            ),
            database=database,
        )
        clients = [client_for(total_app) for _ in range(15)]
        opened = [await c.__aenter__() for c in clients]
        try:
            results = await asyncio.gather(*(save(c, battery_id, "T") for c in opened))
        finally:
            for c in clients:
                await c.__aexit__(None, None, None)
        assert sorted(r.status_code for r in results) == [201] * 6 + [409] * 9  # 4 + 6 = 10
        async with database.engine.connect() as conn:
            assert (await conn.execute(text("SELECT count(*) FROM scenarios"))).scalar_one() == 10
    finally:
        async with database.engine.begin() as conn:
            await conn.execute(text("DELETE FROM scenarios"))
        await database.dispose()
