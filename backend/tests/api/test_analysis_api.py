"""Summary, forecast, backtest and insights endpoints return exactly the v1 results."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.analytics.legacy_v1 import analyze
from app.analytics.synthetic import generate_synthetic_v1
from tests.support.api import client_for, memory_app

pytestmark = pytest.mark.anyio


async def get(path: str, **params: Any) -> tuple[dict[str, Any], str]:
    app, repo = memory_app()
    async with client_for(app) as client:
        r = await client.get(f"/api/v1/batteries/{repo.battery.id}/{path}", params=params)
    assert r.status_code == 200, r.text
    return r.json(), str(repo.battery.id)


async def test_summary_copies_the_v1_analysis_exactly() -> None:
    body, battery_id = await get("summary", eol_pct=85)
    a = analyze(generate_synthetic_v1(), eol_pct=85.0)
    assert body["context"] == {
        "battery_id": battery_id,
        "dataset": "synthetic-v1",
        "is_synthetic": True,
        "data_provenance": "simulated",
        "algorithm_version": "v1",
        "eol_pct": 85.0,
    }
    assert body["soh_now"] == {"value": a.trend.soh_now_pct, "unit": "%", "provenance": "fitted"}
    assert body["fade_rate"]["value"] == a.trend.fade_pct_per_cycle
    assert body["rul"] == {
        "point": a.rul_cycles,
        "lower": a.rul_interval.lower,
        "upper": a.rul_interval.upper,
        "level": 0.95,
        "method": "slope_se",
        "unit": "cycles",
        "provenance": "predicted",
    }
    assert (body["health_level"], body["condition"]) == (a.health_level, a.condition)
    assert body["life_used_fraction"]["value"] == a.life_used_fraction
    assert body["observed_last_soh"]["provenance"] == "simulated"
    assert body["latest"]["cycle"] == 319 and body["cycle_count"] == 320
    assert body["latest"]["temperature"] == {
        "value": a.records[-1].temp_c,
        "unit": "°C",
        "provenance": "simulated",
    }
    assert body["anomalies"] == {"total": 8, "high": 2, "medium": 6}
    assert body["acceleration"]["accelerated"] is True
    assert body["trend"]["slope"] == a.trend.fit.slope and body["trend"]["fit_from_cycle"] == 200


async def test_forecast_series_and_boundary() -> None:
    body, _ = await get("forecast")
    a = analyze()
    assert body["observed"]["values"] == [r.soh_pct for r in a.records]
    assert body["observed"]["provenance"] == "simulated"
    assert body["forecast"]["values"] == list(a.forecast)
    assert body["forecast"]["cycles"][0] == 319 and len(body["forecast"]["cycles"]) == 159
    assert body["forecast"]["provenance"] == "predicted"
    assert (body["extent_cycles"], body["prediction_boundary_cycle"]) == (478, 319)


async def test_backtest_and_insights() -> None:
    backtest, _ = await get("backtest")
    insights, _ = await get("insights")
    a = analyze()
    assert backtest["mae"] == {
        "value": a.backtest.mae,
        "unit": "SOH points",
        "provenance": "fitted",
    }
    assert (backtest["train"], backtest["test"]) == (
        {"from_cycle": 100, "to_cycle": 219},
        {"from_cycle": 220, "to_cycle": 319},
    )
    assert len(backtest["points"]) == 100 and backtest["context"]["eol_pct"] is None
    assert [i["text"] for i in insights["insights"]] == [i.text for i in a.insights]
    assert [i["kind"] for i in insights["insights"]] == ["observation", "watch", "note", "model"]
    assert insights["insights"][2]["values"] == {"temp_events": 1, "volt_events": 2}


@pytest.mark.parametrize("eol", [59.9, 90.5, "nan", "inf", "abc"])
async def test_eol_outside_the_slider_range_is_rejected(eol: Any) -> None:
    app, repo = memory_app()
    async with client_for(app) as client:
        r = await client.get(
            f"/api/v1/batteries/{repo.battery.id}/summary", params={"eol_pct": eol}
        )
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


async def test_unknown_battery_is_404_on_every_analytics_route() -> None:
    app, _ = memory_app()
    async with client_for(app) as client:
        for path in ("summary", "forecast", "backtest", "insights"):
            r = await client.get(f"/api/v1/batteries/{uuid.uuid4()}/{path}")
            assert r.status_code == 404, path


async def test_repeated_requests_reuse_the_cached_analysis() -> None:
    app, repo = memory_app()
    async with client_for(app) as client:
        for _ in range(3):
            await client.get(f"/api/v1/batteries/{repo.battery.id}/summary")
    cache = app.state.analysis_service.cache
    assert (cache.misses, cache.hits) == (1, 2)
