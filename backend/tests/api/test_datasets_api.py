"""Datasets, batteries and cycles endpoints (in-memory repository)."""

from __future__ import annotations

import uuid

import pytest

from app.analytics.synthetic import generate_synthetic_v1
from tests.support.api import client_for, memory_app

pytestmark = pytest.mark.anyio


async def test_datasets_never_expose_internal_ground_truth() -> None:
    app, _ = memory_app()
    async with client_for(app) as client:
        listing = await client.get("/api/v1/datasets")
        single = await client.get("/api/v1/datasets/synthetic-v1")
        missing = await client.get("/api/v1/datasets/nope")
    assert listing.status_code == single.status_code == 200
    item = listing.json()["items"][0]
    assert item == single.json()
    assert (item["slug"], item["source"], item["synthetic"], item["battery_count"]) == (
        "synthetic-v1",
        "synthetic",
        True,
        1,
    )
    for text in (listing.text, single.text):
        assert "meta" not in text and "injected" not in text and "temp_spike" not in text
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "dataset_not_found"


async def test_batteries() -> None:
    app, repo = memory_app()
    async with client_for(app) as client:
        listing = (await client.get("/api/v1/batteries")).json()["items"]
        single = (await client.get(f"/api/v1/batteries/{repo.battery.id}")).json()
        missing = await client.get(f"/api/v1/batteries/{uuid.uuid4()}")
        malformed = await client.get("/api/v1/batteries/not-a-uuid")
    assert listing == [single]
    assert single["id"] == str(repo.battery.id)
    assert (single["external_id"], single["dataset"], single["cycle_count"]) == (
        "SYN-001",
        "synthetic-v1",
        320,
    )
    assert (single["is_synthetic"], single["data_provenance"]) == (True, "simulated")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "battery_not_found"
    assert malformed.status_code == 422


async def test_cycles_are_exact_and_filterable() -> None:
    app, repo = memory_app()
    url = f"/api/v1/batteries/{repo.battery.id}/cycles"
    async with client_for(app) as client:
        full = (await client.get(url)).json()
        window = (await client.get(url, params={"from_cycle": 10, "to_cycle": 12})).json()
        bad = await client.get(url, params={"from_cycle": 5, "to_cycle": 4})
        negative = await client.get(url, params={"from_cycle": -1})
    expected = generate_synthetic_v1()
    assert len(full["items"]) == 320
    for got, want in zip(full["items"], expected, strict=True):
        assert got == {
            "cycle": want.cycle,
            "capacity_ah": want.capacity_ah,
            "soh_pct": want.soh_pct,
            "temp_c": want.temp_c,
            "voltage_v": want.voltage_v,
        }
    assert [c["cycle"] for c in window["items"]] == [10, 11, 12]
    assert full["provenance"] == "simulated" and full["context"]["data_provenance"] == "simulated"
    assert full["units"]["temp_c"] == "°C"
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_range"
    assert negative.status_code == 422


async def test_no_database_gives_503() -> None:
    from app.main import create_app
    from tests.support.api import make_settings

    async with client_for(create_app(make_settings())) as client:
        r = await client.get("/api/v1/batteries")
    assert r.status_code == 503 and r.json()["error"]["code"] == "database_unavailable"
