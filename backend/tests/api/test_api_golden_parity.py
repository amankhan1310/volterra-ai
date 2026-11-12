"""End-to-end regression: API responses reproduce the golden fixtures.

Runs twice: through the in-memory repository and through the full PostgreSQL stack (seed ->
float8 storage -> asyncpg -> legacy_v1.analyze() -> mappers -> JSON). Comparison rules are the
Phase 2 rules: exact by default, 1e-12 only on fields derived from sin/exp/pow, integers exact.
Results are read from the JSON body, so serialization is covered too.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from app.analytics.simulator import LEGACY_KEYS
from app.db.session import Database
from app.main import create_app
from tests.support.api import client_for, make_settings, memory_app
from tests.support.database import assert_disposable
from tests.support.golden import assert_matches

pytestmark = pytest.mark.anyio

LEGACY_COLOUR = {"healthy": "var(--gr)", "caution": "var(--am)", "critical": "var(--rd)"}
TO_LEGACY = {v: k for k, v in LEGACY_KEYS.items()}


class Parity:
    def __init__(self, client: httpx.AsyncClient, battery_id: str, backend: str) -> None:
        self.client, self.backend = client, backend
        self.base = f"/api/v1/batteries/{battery_id}"

    def label(self, section: str) -> str:
        return f"api:{self.backend}:{section}"

    async def get(self, path: str, **params: Any) -> Any:
        r = await self.client.get(f"{self.base}/{path}", params=params)
        assert r.status_code == 200, r.text
        return r.json()

    async def simulate(self, params: dict[str, Any]) -> httpx.Response:
        return await self.client.post(f"{self.base}/simulate", json={"params": params})


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.db)])
async def parity(request: pytest.FixtureRequest) -> AsyncIterator[Parity]:
    if request.param == "memory":
        app, repo = memory_app()
        async with client_for(app) as client:
            yield Parity(client, str(repo.battery.id), "memory")
        return
    url: str = request.getfixturevalue("seeded_database_url")
    assert_disposable(url)
    database = Database(url)
    try:
        async with client_for(create_app(make_settings(), database=database)) as client:
            battery_id = (await client.get("/api/v1/batteries")).json()["items"][0]["id"]
            yield Parity(client, battery_id, "postgres")
    finally:
        await database.dispose()


def to_legacy(params: dict[str, Any]) -> dict[str, Any]:
    return {TO_LEGACY[k]: v for k, v in params.items()}


def from_legacy(params: dict[str, Any]) -> dict[str, Any]:
    return {LEGACY_KEYS[k]: v for k, v in params.items()}


async def test_cycles_match_dataset_fixture(parity: Parity, golden) -> None:
    items = (await parity.get("cycles"))["items"]
    rows = [
        [c["cycle"], c["capacity_ah"], c["soh_pct"], c["temp_c"], c["voltage_v"]] for c in items
    ]
    assert_matches(
        rows, golden("dataset")["rows"], label=parity.label("cycles"), tolerant=[("*", 3)]
    )


async def test_summary_matches_soh_rul_display_and_regression(parity: Parity, golden) -> None:
    soh = golden("soh_rul")
    body = await parity.get("summary", eol_pct=80)
    current = {
        "soh_now_pct": body["soh_now"]["value"],
        "soh_now_provenance": body["soh_now"]["provenance"],
        "observed_last_soh_pct": body["observed_last_soh"]["value"],
        "fade_pct_per_cycle": body["fade_rate"]["value"],
        "fit_cycles": {
            "from": body["trend"]["fit_from_cycle"],
            "to_inclusive": body["trend"]["fit_to_cycle"],
        },
        "default_eol_pct": body["context"]["eol_pct"],
        "rul_cycles_at_default_eol": body["rul"]["point"],
    }
    assert_matches(current, soh["current"], label=parity.label("summary:current"))
    assert_matches(
        {"life_used_fraction": body["life_used_fraction"]["value"]},
        {"life_used_fraction": soh["gauge"]["life_used_fraction"]},
        label=parity.label("summary:gauge"),
    )
    display = golden("display_rules")["current"]
    assert_matches(
        {
            "soh_pct": body["soh_now"]["value"],
            "colour": LEGACY_COLOUR[body["health_level"]],
            "condition": body["condition"],
        },
        display,
        label=parity.label("summary:display"),
    )
    recent = next(f for f in golden("regression")["fits"] if f["name"] == "recent_trend")
    fields = ("slope", "intercept", "residual_sd", "slope_se")
    assert_matches(
        {k: body["trend"][k] for k in fields},
        {k: recent[k] for k in fields},
        label=parity.label("summary:trend"),
    )


async def test_rul_for_every_eol_threshold(parity: Parity, golden) -> None:
    expected = golden("soh_rul")["rul_by_eol"]
    actual = []
    for row in expected:
        rul = (await parity.get("summary", eol_pct=row["eol_pct"]))["rul"]
        actual.append(
            {
                "eol_pct": row["eol_pct"],
                "rul_cycles": rul["point"],
                "interval_95": {"lower": rul["lower"], "upper": rul["upper"]},
            }
        )
    assert_matches(actual, expected, label=parity.label("summary:rul_by_eol"))


async def test_forecast_matches(parity: Parity, golden) -> None:
    body = await parity.get("forecast", eol_pct=80)
    expected = golden("soh_rul")["forecast"]
    actual = {
        "extent_cycles": body["extent_cycles"],
        "from_cycle": body["forecast"]["cycles"][0],
        "to_cycle_inclusive": body["forecast"]["cycles"][-1],
        "values": body["forecast"]["values"],
    }
    assert_matches(actual, {k: expected[k] for k in actual}, label=parity.label("forecast"))


async def test_backtest_matches(parity: Parity, golden) -> None:
    body = await parity.get("backtest")
    actual = {
        "train_cycles": {
            "from": body["train"]["from_cycle"],
            "to_inclusive": body["train"]["to_cycle"],
        },
        "test_cycles": {
            "from": body["test"]["from_cycle"],
            "to_inclusive": body["test"]["to_cycle"],
        },
        "fit": body["fit"],
        "columns": ["cycle", "observed_soh_pct", "predicted_soh_pct", "abs_error"],
        "per_cycle": [
            [p["cycle"], p["observed_soh_pct"], p["predicted_soh_pct"], p["abs_error"]]
            for p in body["points"]
        ],
        "mae": body["mae"]["value"],
    }
    expected = {k: v for k, v in golden("backtest").items() if k != "meta"}
    assert_matches(actual, expected, label=parity.label("backtest"))


async def test_anomalies_match(parity: Parity, golden) -> None:
    body = await parity.get("anomalies", include_scores="true")
    fixture = golden("anomalies")
    channels = []
    for c in body["channels"]:
        row = {k: c[k] for k in ("channel", "label", "unit", "median", "mad", "expected_low")}
        row |= {"expected_high": c["expected_high"], "z": c["z"]}
        if c["channel"] == "soh":
            row["input_values"] = c["values"]
        channels.append(row)
    expected_channels = [{k: v for k, v in c.items() if k != "input"} for c in fixture["channels"]]
    assert_matches(
        channels, expected_channels, label=parity.label("anomalies:channels"), tolerant=[(0, "**")]
    )
    temp_events = [(i, "**") for i, e in enumerate(fixture["events"]) if e["channel"] == "temp"]
    assert_matches(
        body["events"],
        fixture["events"],
        label=parity.label("anomalies:events"),
        tolerant=temp_events,
    )
    assert_matches(body["summary"], fixture["summary"], label=parity.label("anomalies:summary"))
    method = {k: body["method"][k] for k in ("flag_threshold_abs_z", "high_severity_abs_z")}
    assert_matches(
        method, {k: fixture["method"][k] for k in method}, label=parity.label("anomalies:method")
    )


async def test_insights_match(parity: Parity, golden) -> None:
    body = await parity.get("insights")
    fixture = golden("insights")
    values = [i["values"] for i in body["insights"]]
    actual = {
        "inputs": {
            "first_soh_pct": values[0]["first_soh_pct"],
            "soh_now_pct": values[0]["soh_now_pct"],
            "n_cycles": values[0]["n_cycles"],
            "first_half_fade_pct_per_cycle": values[1]["first_half_fade_pct_per_cycle"],
            "recent_fade_pct_per_cycle": values[1]["recent_fade_pct_per_cycle"],
            "temp_events": values[2]["temp_events"],
            "volt_events": values[2]["volt_events"],
            "backtest_mae": values[3]["backtest_mae"],
        },
        "insights": [i["text"] for i in body["insights"]],
        "overview_hero": {
            "accelerated": body["acceleration"]["accelerated"],
            "appended_text": body["acceleration"]["note"],
        },
    }
    expected = {
        "inputs": fixture["inputs"],
        "insights": fixture["insights"],
        "overview_hero": {k: fixture["overview_hero"][k] for k in ("accelerated", "appended_text")},
    }
    assert_matches(actual, expected, label=parity.label("insights"))


async def test_simulator_config_matches(parity: Parity, golden) -> None:
    body = await parity.get("simulator")
    fixture = golden("simulator")
    coefficients = {c["name"]: c["value"] for c in body["coefficients"]}
    actual = {
        "coefficients": {
            "temp_exp_per_c": coefficients["temperature"],
            "c_rate_linear": coefficients["c_rate"],
            "dod_exponent": coefficients["dod"],
            "acceleration_cycles": coefficients["acceleration"],
        },
        "base_fade_pct_per_cycle": body["base_fade"]["value"],
        "baseline_conditions": to_legacy(body["baseline_conditions"]),
        "default_params": to_legacy(body["defaults"]),
        "sliders": [
            {k: s[k] for k in ("label", "min", "max", "step", "unit")} | {"key": s["legacy_key"]}
            for s in body["sliders"]
        ],
    }
    expected_coefficients = dict(fixture["model"]["coefficients"])
    expected_coefficients.pop("eol_scan_max_cycles")
    expected = {
        "coefficients": expected_coefficients,
        "base_fade_pct_per_cycle": fixture["base_fade_pct_per_cycle"],
        "baseline_conditions": fixture["baseline_conditions"],
        "default_params": fixture["default_params"],
        "sliders": fixture["sliders"],
    }
    assert_matches(actual, expected, label=parity.label("simulator:config"))


async def test_simulated_scenarios_match(parity: Parity, golden) -> None:
    sliders = {s["key"]: s for s in golden("simulator")["sliders"]}

    def in_range(params: dict[str, Any]) -> bool:
        return all(sliders[k]["min"] <= v <= sliders[k]["max"] for k, v in params.items())

    tolerant = [
        ("*", "rate_pct_per_cycle"),
        ("*", "soh_at", "*", 1),
        ("*", "comparison_vs_baseline", "soh_after_n"),
        ("*", "comparison_vs_baseline", "baseline_soh_after_n"),
    ]
    actual, expected, rejected = [], [], []
    for scenario in golden("simulator")["scenarios"]:
        r = await parity.simulate(from_legacy(scenario["params"]))
        if not in_range(scenario["params"]):
            rejected.append((scenario["name"], r.status_code))
            continue
        assert r.status_code == 200, r.text
        body = r.json()
        horizon = scenario["params"]["N"]
        samples = [[n, v] for n, v in scenario["soh_at"] if n <= horizon]
        trajectory = body["trajectories"]["scenario"]
        cmp = scenario["comparison_vs_baseline"]
        expected.append(
            {
                "name": scenario["name"],
                "params": scenario["params"],
                "rate_pct_per_cycle": scenario["rate_pct_per_cycle"],
                "cycles_to_eol": scenario["cycles_to_eol"],
                "soh_at": samples,
                "comparison_vs_baseline": cmp,
            }
        )
        actual.append(
            {
                "name": scenario["name"],
                "params": to_legacy(body["params"]),
                "rate_pct_per_cycle": body["rate"]["value"],
                "cycles_to_eol": body["cycles_to_eol"],
                "soh_at": [[n, trajectory[n]] for n, _ in samples],
                "comparison_vs_baseline": {
                    "baseline_params": to_legacy(body["baseline_params"]),
                    "baseline_cycles_to_eol": body["baseline_cycles_to_eol"],
                    "delta_cycles": body["delta_cycles"],
                    "delta_pct": body["delta_pct"],
                    "soh_after_n": body["soh_after_horizon"]["value"],
                    "baseline_soh_after_n": body["baseline_soh_after_horizon"]["value"],
                },
            }
        )
    assert_matches(actual, expected, label=parity.label("simulate:scenarios"), tolerant=tolerant)
    assert len(actual) == 17
    assert rejected == [("beyond_horizon", 422)]  # T = -20 °C is outside the slider range


async def test_trajectories_and_f4_match(parity: Parity, golden) -> None:
    fixture = golden("simulator")
    default = (await parity.simulate(from_legacy(fixture["default_params"]))).json()
    actual = [
        {
            "name": "default",
            "params": to_legacy(default["params"]),
            "soh": default["trajectories"]["scenario"],
        },
        {
            "name": "baseline",
            "params": to_legacy(default["baseline_params"]),
            "soh": default["trajectories"]["baseline"],
        },
    ]
    assert_matches(
        actual,
        fixture["trajectories"],
        label=parity.label("simulate:trajectories"),
        tolerant=[("*", "soh", "*")],
    )
    summary = await parity.get("summary", eol_pct=80)
    f4 = {
        "overview_rul_cycles_at_default_eol": summary["rul"]["point"],
        "simulator_baseline_cycles_to_eol": default["baseline_cycles_to_eol"],
    }
    assert_matches(f4, fixture["consistency_check_F4"], label=parity.label("simulate:F4"))


async def test_advisor_matches(parity: Parity, golden) -> None:
    fixture = golden("advisor")
    for section, params in (("default", {}), ("edge_start_below_eol", {"start_soh_pct": 70})):
        body = await parity.get("advisor", **params)
        expected = fixture[section]
        actual = {
            "start_soh_pct": body["start_soh_pct"],
            "eol_pct": body["eol_pct"],
            "baseline_cycles_to_eol": body["baseline_cycles_to_eol"],
            "rows": [
                {
                    "change": r["change"],
                    "params_override": to_legacy(r["override"]),
                    "cycles_to_eol": r["cycles_to_eol"],
                    "delta_pct_ui": r["delta_pct"],
                }
                for r in body["rows"]
            ],
        }
        trimmed = {
            **{k: v for k, v in expected.items() if k != "rows"},
            "rows": [
                {k: v for k, v in r.items() if k not in {"bar", "delta_pct_core"}}
                for r in expected["rows"]
            ],
        }
        assert_matches(actual, trimmed, label=parity.label(f"advisor:{section}"))
