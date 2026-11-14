"""Opt-in ``?algorithm=v2``: v2 endpoints copy ``analyze_v2()``; v1 responses are unchanged.

v1 (the default) is covered by the existing API and golden-parity tests; these tests add the v2
path and prove the change is additive: the default and ``?algorithm=v1`` responses are
identical and carry no v2-only keys.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.analytics.analysis_v2 import analyze_v2
from app.analytics.synthetic import generate_synthetic_v1
from app.main import create_app
from app.services.analysis import AnalysisCache, AnalysisService
from tests.support.api import client_for, make_settings, memory_app
from tests.support.memory_repository import InMemoryRepository

pytestmark = pytest.mark.anyio

V2 = analyze_v2(generate_synthetic_v1(), dataset_id="synthetic-v1")

#: Keys only v2 responses may carry anywhere. (v2 also adds ``Interval.label`` and
#: ``ChannelStatsOut.cycles``; v1 uses those names elsewhere, so they are checked in place.)
V2_ONLY_KEYS = {
    "curvature",
    "origin_cycle",
    "max_calibrated_horizon_cycles",
    "mean_signed_error",
    "step_window",
    "min_step_soh_pct",
    "causal_fit_window",
    "causal_min_history",
    "change_pct",
    "comparison",
}


def keys(value: Any) -> set[str]:
    """Every dictionary key anywhere in a JSON value."""
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys(v)}
    return set()


async def call(method: str, path: str, **kwargs: Any) -> tuple[int, Any]:
    app, repo = memory_app()
    async with client_for(app) as client:
        r = await client.request(method, f"/api/v1/batteries/{repo.battery.id}/{path}", **kwargs)
    return r.status_code, r.json()


SIMULATE_BODY = {
    "params": {
        "temp_c": 35,
        "c_rate": 1,
        "dod_pct": 80,
        "horizon_cycles": 200,
        "start_soh_pct": 86,
        "eol_pct": 80,
    },
    "include_trajectories": True,
}

V1_REQUESTS: list[tuple[str, str, dict[str, Any]]] = [
    ("GET", "summary", {"params": {"eol_pct": 80}}),
    ("GET", "forecast", {}),
    ("GET", "backtest", {}),
    ("GET", "insights", {}),
    ("GET", "anomalies", {"params": {"include_scores": "true"}}),
    ("GET", "simulator", {}),
    ("POST", "simulate", {"json": SIMULATE_BODY}),
    ("GET", "advisor", {}),
    ("GET", "advisor", {"params": {"eol_pct": 90, "start_soh_pct": 85}}),
]


@pytest.mark.parametrize(("method", "path", "kwargs"), V1_REQUESTS)
async def test_v1_is_the_default_and_unchanged(method, path, kwargs) -> None:
    app, repo = memory_app()  # one app: both requests see the same battery
    url = f"/api/v1/batteries/{repo.battery.id}/{path}"
    params = {**kwargs.get("params", {}), "algorithm": "v1"}
    async with client_for(app) as client:
        r_default = await client.request(method, url, **kwargs)
        r_explicit = await client.request(method, url, **{**kwargs, "params": params})
    assert r_default.status_code == r_explicit.status_code == 200
    default, explicit = r_default.json(), r_explicit.json()
    assert default == explicit
    assert default["context"]["algorithm_version"] == "v1"
    assert keys(default) & V2_ONLY_KEYS == set()
    if path == "summary":
        assert "label" not in default["rul"]
    if path == "anomalies":
        assert all("cycles" not in c for c in default["channels"])


async def test_summary_v2() -> None:
    status, body = await call("GET", "summary", params={"algorithm": "v2"})
    assert status == 200
    assert body["context"]["algorithm_version"] == "v2"
    assert body["soh_now"]["value"] == V2.trend.soh_now_pct
    assert body["fade_rate"]["value"] == V2.trend.fade_pct_per_cycle
    assert body["rul"] == {
        "point": V2.rul_cycles,
        "lower": 92.0,
        "upper": 101.0,
        "level": 0.9,
        "method": "rolling_origin_backtest_quantiles",
        "unit": "cycles",
        "provenance": "predicted",
        "label": "90% prediction interval",
        "max_calibrated_horizon_cycles": 171,
    }
    assert body["anomalies"] == {
        "total": V2.anomalies.count(),
        "high": V2.anomalies.count("high"),
        "medium": V2.anomalies.count("medium"),
    }
    assert V2.anomalies.count() == 5  # exactly the injected anomalies (F1, F2)
    assert body["trend"]["curvature"] == V2.trend.fit.c2
    assert body["trend"]["origin_cycle"] == 319
    assert body["trend"]["slope"] == V2.trend.fit.c1
    assert body["acceleration"]["accelerated"] is True


async def test_forecast_backtest_and_insights_v2() -> None:
    _, forecast = await call("GET", "forecast", params={"algorithm": "v2"})
    assert forecast["method"] == "quadratic_recent_120_cycles_interim"
    assert forecast["forecast"]["values"] == list(V2.forecast)
    _, backtest = await call("GET", "backtest", params={"algorithm": "v2"})
    assert backtest["mae"]["value"] == V2.backtest.mae
    assert backtest["mean_signed_error"]["value"] == V2.backtest.mean_signed_error
    assert abs(backtest["mean_signed_error"]["value"]) < 0.1  # F6
    _, insights = await call("GET", "insights", params={"algorithm": "v2"})
    assert [i["text"] for i in insights["insights"]] == [i.text for i in V2.insights]


async def test_anomalies_v2_both_modes() -> None:
    _, retro = await call("GET", "anomalies", params={"algorithm": "v2", "include_scores": "true"})
    assert retro["detector"] == {
        "name": "robust_z_detrended",
        "version": "v2",
        "mode": "retrospective",
    }
    assert [e["cycle"] for e in retro["events"] if e["channel"] == "temp"] == [90, 170, 251]
    assert [e["channel"] for e in retro["events"]].count("soh") == 0
    assert retro["known_issues"] == []
    assert retro["method"]["min_step_soh_pct"] == 0.5
    temp = retro["channels"][0]
    assert len(temp["cycles"]) == len(temp["values"]) == len(temp["z"])
    _, causal = await call("GET", "anomalies", params={"algorithm": "v2", "mode": "causal"})
    assert causal["detector"]["mode"] == "causal"
    assert [e["cycle"] for e in causal["events"]] == [e.cycle for e in V2.anomalies_causal.events]


async def test_causal_mode_needs_v2() -> None:
    status, body = await call("GET", "anomalies", params={"mode": "causal"})
    assert status == 422
    assert body["error"]["code"] == "unsupported_mode"


async def test_simulator_and_simulate_v2() -> None:
    _, config = await call("GET", "simulator", params={"algorithm": "v2"})
    assert config["version"] == "v2"
    assert config["defaults"]["start_soh_pct"] == V2.trend.soh_now_pct
    names = [c["name"] for c in config["coefficients"]]
    assert names == ["base_fade", "temperature", "c_rate", "dod"]  # no acceleration term (F4)
    status, sim = await call("POST", "simulate", params={"algorithm": "v2"}, json=SIMULATE_BODY)
    assert status == 200
    assert sim["context"]["algorithm_version"] == "v2"
    assert sim["known_issues"] == []
    assert len(sim["trajectories"]["scenario"]) == 201


async def test_simulator_baseline_matches_the_overview_in_v2() -> None:
    """F4 through the API: the v2 advisor baseline equals the rounded v2 Overview RUL."""
    _, summary = await call("GET", "summary", params={"algorithm": "v2"})
    _, advisor = await call("GET", "advisor", params={"algorithm": "v2"})
    assert advisor["baseline_cycles_to_eol"] == round(summary["rul"]["point"])


async def test_advisor_v2_reports_rows_that_cannot_be_compared() -> None:
    status, body = await call(
        "GET", "advisor", params={"algorithm": "v2", "eol_pct": 90, "start_soh_pct": 85}
    )
    assert status == 200
    assert body["baseline_cycles_to_eol"] == 0
    for row in body["rows"]:
        assert row["change_pct"] is None  # explicit null, not omitted
        assert row["comparison"] == "at_or_below_eol"
        assert row["delta_pct"] == 0  # v1 meaning, kept for compatibility
    _, default = await call("GET", "advisor", params={"algorithm": "v2"})
    assert all(r["comparison"] == "comparable" for r in default["rows"])
    assert default["rows"][0]["change_pct"] == default["rows"][0]["delta_pct"]


async def test_unknown_algorithm_is_rejected() -> None:
    status, _ = await call("GET", "summary", params={"algorithm": "v3"})
    assert status == 422


async def test_v1_and_v2_are_cached_separately() -> None:
    repo = InMemoryRepository()
    service = AnalysisService(AnalysisCache(4))
    v1 = await service.analyze(repo, repo.battery.id, 80.0)
    v2 = await service.analyze_v2(repo, repo.battery.id, 80.0)
    again = await service.analyze_v2(repo, repo.battery.id, 80.0)
    assert again.analysis is v2.analysis
    assert v1.analysis.algorithm_version == "v1" and v2.analysis.algorithm_version == "v2"
    assert (service.cache.hits, service.cache.misses, len(service.cache)) == (1, 2, 2)


async def test_openapi_keeps_every_advisor_row_field() -> None:
    """Guard: a serializer's return annotation once erased the row schema (caught in review)."""
    app = create_app(make_settings())
    row = app.openapi()["components"]["schemas"]["AdvisorRowOut"]
    assert set(row["required"]) == {"change", "why", "override", "cycles_to_eol", "delta_pct"}
    assert {"change_pct", "comparison"} <= set(row["properties"])
