"""Saved scenario CRUD over HTTP: in-memory and the full PostgreSQL stack."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from app.db.session import Database
from app.main import create_app
from tests.support.api import client_for, make_settings, memory_app
from tests.support.database import assert_disposable

pytestmark = pytest.mark.anyio

PARAMS = {
    "temp_c": 35.0,
    "c_rate": 2.0,
    "dod_pct": 80.0,
    "horizon_cycles": 600,
    "start_soh_pct": 86.1,
    "eol_pct": 80.0,
}


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.db)])
async def api(request: pytest.FixtureRequest) -> AsyncIterator[tuple[httpx.AsyncClient, str]]:
    if request.param == "memory":
        app, repo = memory_app()
        async with client_for(app) as client:
            yield client, str(repo.battery.id)
        return
    url: str = request.getfixturevalue("seeded_database_url")
    assert_disposable(url)
    database = Database(url)
    try:
        async with client_for(create_app(make_settings(), database=database)) as client:
            battery_id = (await client.get("/api/v1/batteries")).json()["items"][0]["id"]
            yield client, battery_id
            for s in (await client.get(f"/api/v1/batteries/{battery_id}/scenarios")).json()[
                "items"
            ]:
                await client.delete(f"/api/v1/scenarios/{s['id']}")
    finally:
        await database.dispose()


async def test_scenario_lifecycle(api: tuple[httpx.AsyncClient, str]) -> None:
    client, battery_id = api
    base = f"/api/v1/batteries/{battery_id}/scenarios"
    assert (await client.get(base)).json() == {"items": []}

    created = await client.post(base, json={"name": "  Hot climate  ", "params": PARAMS})
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Hot climate" and body["params"] == PARAMS
    assert body["battery_id"] == battery_id and body["simulator_version"] == "v1"
    sid = body["id"]

    second = await client.post(base, json={"name": "Gentle", "params": {**PARAMS, "c_rate": 0.5}})
    assert [s["name"] for s in (await client.get(base)).json()["items"]] == [
        "Hot climate",
        "Gentle",
    ]

    renamed = await client.patch(f"/api/v1/scenarios/{sid}", json={"name": "Renamed"})
    assert renamed.status_code == 200 and renamed.json()["params"] == PARAMS
    reparam = await client.patch(
        f"/api/v1/scenarios/{sid}", json={"params": {**PARAMS, "temp_c": 15.0}}
    )
    assert reparam.json()["name"] == "Renamed" and reparam.json()["params"]["temp_c"] == 15.0
    assert (await client.get(f"/api/v1/scenarios/{sid}")).json() == reparam.json()

    deleted = await client.delete(f"/api/v1/scenarios/{second.json()['id']}")
    assert deleted.status_code == 204 and deleted.content == b""
    assert [s["id"] for s in (await client.get(base)).json()["items"]] == [sid]


async def test_more_than_four_scenarios_are_allowed(api: tuple[httpx.AsyncClient, str]) -> None:
    client, battery_id = api
    base = f"/api/v1/batteries/{battery_id}/scenarios"
    for i in range(6):
        assert (
            await client.post(base, json={"name": f"S{i}", "params": PARAMS})
        ).status_code == 201
    assert len((await client.get(base)).json()["items"]) == 6


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "params": PARAMS},
        {"name": "   ", "params": PARAMS},
        {"name": "x" * 61, "params": PARAMS},
        {"name": "ok", "params": {**PARAMS, "temp_c": 60}},
        {"name": "ok", "params": PARAMS, "owner": "someone"},
        {"params": PARAMS},
    ],
)
async def test_invalid_scenarios_are_rejected(
    api: tuple[httpx.AsyncClient, str], body: dict[str, Any]
) -> None:
    client, battery_id = api
    r = await client.post(f"/api/v1/batteries/{battery_id}/scenarios", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


async def test_sixty_character_names_and_errors(api: tuple[httpx.AsyncClient, str]) -> None:
    client, battery_id = api
    base = f"/api/v1/batteries/{battery_id}/scenarios"
    long_name = "n" * 60
    created = await client.post(base, json={"name": long_name, "params": PARAMS})
    assert created.status_code == 201 and created.json()["name"] == long_name
    sid = created.json()["id"]
    assert (await client.patch(f"/api/v1/scenarios/{sid}", json={})).status_code == 422
    unknown = uuid.uuid4()
    assert (await client.get(f"/api/v1/scenarios/{unknown}")).status_code == 404
    assert (
        await client.patch(f"/api/v1/scenarios/{unknown}", json={"name": "x"})
    ).status_code == 404
    assert (await client.delete(f"/api/v1/scenarios/{unknown}")).status_code == 404
    missing_battery = f"/api/v1/batteries/{unknown}/scenarios"
    assert (await client.get(missing_battery)).status_code == 404
    assert (
        await client.post(missing_battery, json={"name": "x", "params": PARAMS})
    ).status_code == 404
