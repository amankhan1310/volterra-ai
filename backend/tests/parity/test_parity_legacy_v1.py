"""End-to-end parity: one ``analyze()`` run reproduces the prototype's headline outputs."""

from __future__ import annotations

import dataclasses

import pytest

from app.analytics.legacy_v1 import analyze
from app.analytics.synthetic import generate_synthetic_v1
from tests.support.golden import assert_matches

LEGACY_COLOUR = {"healthy": "var(--gr)", "caution": "var(--am)", "critical": "var(--rd)"}


def test_analyze_reproduces_all_headline_outputs(golden) -> None:
    a = analyze()
    soh = golden("soh_rul")
    row80 = next(r for r in soh["rul_by_eol"] if r["eol_pct"] == 80)
    sim = golden("simulator")
    actual = {
        "dataset_rows": len(a.records),
        "soh_now_pct": a.trend.soh_now_pct,
        "fade_pct_per_cycle": a.trend.fade_pct_per_cycle,
        "rul_cycles": a.rul_cycles,
        "interval_95": {"lower": a.rul_interval.lower, "upper": a.rul_interval.upper},
        "forecast": list(a.forecast),
        "life_used_fraction": a.life_used_fraction,
        "colour": LEGACY_COLOUR[a.health_level],
        "condition": a.condition,
        "backtest_mae": a.backtest.mae,
        "event_cycles": [e.cycle for e in a.anomalies.events],
        "insights": [i.text for i in a.insights],
        "accelerated": a.acceleration.accelerated,
        "default_params": a.simulator_defaults.to_legacy(),
        "simulator_baseline_cycles_to_eol": a.simulator_baseline.cycles_to_eol,
        "advisor_cycles": [r.cycles_to_eol for r in a.advisor.rows],
        "advisor_delta_pct": [r.delta_pct for r in a.advisor.rows],
    }
    expected = {
        "dataset_rows": len(golden("dataset")["rows"]),
        "soh_now_pct": soh["current"]["soh_now_pct"],
        "fade_pct_per_cycle": soh["current"]["fade_pct_per_cycle"],
        "rul_cycles": row80["rul_cycles"],
        "interval_95": row80["interval_95"],
        "forecast": soh["forecast"]["values"],
        "life_used_fraction": soh["gauge"]["life_used_fraction"],
        "colour": golden("display_rules")["current"]["colour"],
        "condition": golden("display_rules")["current"]["condition"],
        "backtest_mae": golden("backtest")["mae"],
        "event_cycles": [e["cycle"] for e in golden("anomalies")["events"]],
        "insights": golden("insights")["insights"],
        "accelerated": golden("insights")["overview_hero"]["accelerated"],
        "default_params": sim["default_params"],
        "simulator_baseline_cycles_to_eol": sim["consistency_check_F4"][
            "simulator_baseline_cycles_to_eol"
        ],
        "advisor_cycles": [r["cycles_to_eol"] for r in golden("advisor")["default"]["rows"]],
        "advisor_delta_pct": [r["delta_pct_ui"] for r in golden("advisor")["default"]["rows"]],
    }
    assert_matches(actual, expected, label="legacy_v1:end_to_end")


def test_analyze_metadata_and_custom_inputs() -> None:
    a = analyze()
    assert (a.dataset_id, a.algorithm_version, a.eol_pct) == ("synthetic-v1", "v1", 80.0)
    custom = analyze(generate_synthetic_v1(), eol_pct=85.0, dataset_id="custom-run")
    assert custom.dataset_id == "custom-run"
    assert custom.simulator_defaults.eol_pct == 85.0
    assert custom.rul_cycles is not None and a.rul_cycles is not None
    assert custom.rul_cycles < a.rul_cycles
    assert analyze(generate_synthetic_v1()).dataset_id == "custom"


def test_analysis_result_is_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        analyze().eol_pct = 70.0  # type: ignore[misc]
