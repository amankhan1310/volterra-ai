"""The models API without a database: no run imported, unknown batteries, synthetic battery."""

from __future__ import annotations

import uuid

import pytest

from tests.support.api import client_for, memory_app

pytestmark = pytest.mark.anyio


async def test_no_run_imported() -> None:
    app, repo = memory_app()
    async with client_for(app) as client:
        models = await client.get("/api/v1/models")
        synthetic = await client.get(f"/api/v1/batteries/{repo.battery.id}/rul-predictions")
        unknown = await client.get(f"/api/v1/batteries/{uuid.uuid4()}/rul-predictions")
    assert models.status_code == 200
    body = models.json()
    assert body["run"] is None and body["tasks"] == [] and "Experimental" in body["note"]
    assert synthetic.status_code == 404
    assert synthetic.json()["error"]["code"] == "predictions_not_found"
    assert "SYN-001" in synthetic.json()["error"]["message"]
    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "battery_not_found"
