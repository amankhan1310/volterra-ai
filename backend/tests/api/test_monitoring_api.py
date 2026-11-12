"""Anomalies and digital twin endpoints."""

from __future__ import annotations

import uuid

import pytest

from app.analytics.legacy_v1 import analyze
from app.analytics.synthetic import generate_synthetic_v1
from tests.support.api import client_for, memory_app
from tests.support.memory_repository import InMemoryRepository

pytestmark = pytest.mark.anyio


async def test_anomalies_without_and_with_scores() -> None:
    app, repo = memory_app()
    url = f"/api/v1/batteries/{repo.battery.id}/anomalies"
    async with client_for(app) as client:
        plain = (await client.get(url)).json()
        scored = (await client.get(url, params={"include_scores": "true"})).json()
    report = analyze().anomalies
    assert plain["channels"] is None
    assert plain["detector"] == {"name": "robust_z", "version": "v1", "mode": "retrospective"}
    assert plain["summary"] == {"total": 8, "high": 2, "medium": 6}
    assert [e["cycle"] for e in plain["events"]] == [e.cycle for e in report.events]
    assert plain["events"][2] == {
        "cycle": 130,
        "channel": "volt",
        "type": "Voltage dip/spike",
        "value": report.events[2].value,
        "unit": "V",
        "expected_low": report.events[2].expected_low,
        "expected_high": report.events[2].expected_high,
        "z": report.events[2].z,
        "severity": "high",
    }
    assert plain["known_issues"] == ["F1", "F2", "F7"]
    assert plain["method"]["flag_threshold_abs_z"] == 3.5
    assert [c["channel"] for c in scored["channels"]] == ["temp", "volt", "soh"]
    assert scored["channels"][0]["z"] == list(report.channels[0].z)
    assert scored["channels"][2]["values"] == list(report.channels[2].values)
    for body in (plain, scored):
        assert "injected" not in str(body) and "ground_truth" not in str(body)


async def test_twin_latest_and_selected_cycle() -> None:
    app, repo = memory_app()
    url = f"/api/v1/batteries/{repo.battery.id}/twin"
    async with client_for(app) as client:
        latest = (await client.get(url)).json()
        at_90 = (await client.get(url, params={"cycle": 90})).json()
        missing = await client.get(url, params={"cycle": 320})
    records = generate_synthetic_v1()
    assert (latest["cycle"], latest["last_cycle"]) == (319, 319)
    assert latest["pack"]["soh"] == {
        "value": records[-1].soh_pct,
        "unit": "%",
        "provenance": "simulated",
    }
    assert latest["health_level"] == "healthy"
    assert at_90["pack"]["temperature"]["value"] == records[90].temp_c
    assert at_90["temperature_band"] == "warm"  # injected +9 °C spike
    assert latest["temperature_band"] == "normal"
    assert latest["modules"]["count"] == 24 and latest["modules"]["illustrative"] is True
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "cycle_out_of_range"


async def test_twin_errors() -> None:
    app, _ = memory_app()
    empty_app, empty_repo = memory_app(InMemoryRepository(records=()))
    async with client_for(app) as client:
        unknown = await client.get(f"/api/v1/batteries/{uuid.uuid4()}/twin")
    async with client_for(empty_app) as client:
        empty = await client.get(f"/api/v1/batteries/{empty_repo.battery.id}/twin")
    assert unknown.status_code == 404
    assert empty.status_code == 422 and empty.json()["error"]["code"] == "insufficient_data"
