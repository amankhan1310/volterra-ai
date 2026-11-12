"""Simulator config, simulate and advisor endpoints (in-memory repository)."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.analytics.advisor import sensitivity_table
from app.analytics.legacy_v1 import analyze
from app.analytics.simulator import compare_to_baseline, degradation_rate, trajectory
from tests.support.api import client_for, memory_app

pytestmark = pytest.mark.anyio

A = analyze()
FADE = A.trend.fade_pct_per_cycle
DEFAULT = {
    "temp_c": 25.0,
    "c_rate": 1.0,
    "dod_pct": 80.0,
    "horizon_cycles": 600,
    "start_soh_pct": 86.1,
    "eol_pct": 80.0,
}


async def call(method: str, path: str, **kwargs: Any) -> Any:
    app, repo = memory_app()
    async with client_for(app) as client:
        return await client.request(method, f"/api/v1/batteries/{repo.battery.id}/{path}", **kwargs)


async def test_simulator_config() -> None:
    body = (await call("GET", "simulator")).json()
    assert body["defaults"] == DEFAULT
    assert body["baseline_conditions"] == {"temp_c": 25.0, "c_rate": 1.0, "dod_pct": 80.0}
    assert body["base_fade"] == {"value": FADE, "unit": "%/cycle", "provenance": "fitted"}
    assert {c["name"]: c["provenance"] for c in body["coefficients"]} == {
        "base_fade": "fitted",
        "temperature": "assumed",
        "c_rate": "assumed",
        "dod": "assumed",
        "acceleration": "assumed",
    }
    assert [s["legacy_key"] for s in body["sliders"]] == ["T", "C", "D", "N", "S", "E"]
    assert body["sliders"][0] == {
        "key": "temp_c",
        "legacy_key": "T",
        "label": "Temperature",
        "min": 5.0,
        "max": 45.0,
        "step": 1.0,
        "unit": "°C",
    }


async def test_simulate_copies_the_v1_simulator() -> None:
    params = {**DEFAULT, "temp_c": 35.0, "c_rate": 2.0}
    body = (await call("POST", "simulate", json={"params": params})).json()
    p = dataclasses.replace(A.simulator_defaults, temp_c=35.0, c_rate=2.0)
    expected = compare_to_baseline(p, FADE)
    assert body["rate"] == {
        "value": degradation_rate(p, FADE),
        "unit": "%/cycle",
        "provenance": "simulated",
    }
    assert (body["cycles_to_eol"], body["baseline_cycles_to_eol"], body["delta_cycles"]) == (
        expected.cycles_to_eol,
        expected.baseline_cycles_to_eol,
        expected.delta_cycles,
    )
    assert body["delta_pct"] == expected.delta_pct
    assert body["baseline_params"] == DEFAULT
    assert body["trajectories"]["cycles"] == list(range(601))
    assert body["trajectories"]["scenario"] == trajectory(p, FADE)
    assert body["trajectories"]["baseline"] == trajectory(expected.baseline_params, FADE)
    assert body["known_issues"] == ["F4"] and body["context"]["eol_pct"] == 80.0


async def test_simulate_edge_cases_and_options() -> None:
    below = await call("POST", "simulate", json={"params": {**DEFAULT, "start_soh_pct": 70.0}})
    no_traj = await call(
        "POST", "simulate", json={"params": DEFAULT, "include_trajectories": False}
    )
    assert below.json()["cycles_to_eol"] == 0
    assert below.json()["delta_pct"] == "NaN"  # 0/0 in the prototype, serialized as a string
    assert no_traj.json()["trajectories"] is None


@pytest.mark.parametrize(
    "bad",
    [
        {**DEFAULT, "temp_c": 45.5},
        {**DEFAULT, "c_rate": 0.4},
        {**DEFAULT, "horizon_cycles": 99},
        {**DEFAULT, "eol_pct": 91},
        {**DEFAULT, "start_soh_pct": "NaN"},
        {**DEFAULT, "unexpected": 1},
        {k: v for k, v in DEFAULT.items() if k != "dod_pct"},
    ],
)
async def test_simulate_rejects_values_outside_the_slider_ranges(bad: dict[str, Any]) -> None:
    r = await call("POST", "simulate", json={"params": bad})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


async def test_advisor_default_and_custom_start() -> None:
    default = (await call("GET", "advisor")).json()
    edge = (await call("GET", "advisor", params={"start_soh_pct": 70})).json()
    expected = sensitivity_table(A.simulator_defaults, FADE)
    assert default["baseline_cycles_to_eol"] == expected.baseline_cycles_to_eol == 106
    assert [r["cycles_to_eol"] for r in default["rows"]] == [r.cycles_to_eol for r in expected.rows]
    assert [r["delta_pct"] for r in default["rows"]] == [r.delta_pct for r in expected.rows]
    assert default["rows"][0]["override"] == {"temp_c": 15}
    assert default["known_issues"] == ["F8"]
    assert edge["baseline_cycles_to_eol"] == 0
    assert all(r["delta_pct"] == 0 for r in edge["rows"])  # F8 reproduced
    bad = await call("GET", "advisor", params={"start_soh_pct": 69})
    assert bad.status_code == 422
