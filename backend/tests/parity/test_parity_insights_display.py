"""Parity: insight text matches insights.json exactly; display rules match display_rules.json."""

from __future__ import annotations

from app.analytics.anomalies import detect_anomalies_v1
from app.analytics.backtest import run_backtest
from app.analytics.display import condition_label, health_level
from app.analytics.health import recent_trend
from app.analytics.insights import first_half_fade, generate_insights_v1, overview_acceleration_v1
from app.analytics.synthetic import generate_synthetic_v1
from tests.support.golden import assert_matches

RECORDS = generate_synthetic_v1()
TREND = recent_trend(RECORDS)
ANOMALIES = detect_anomalies_v1(RECORDS)
BACKTEST = run_backtest(RECORDS)

#: The prototype's CSS colour per semantic level (presentation mapping, frontend concern).
LEGACY_COLOUR = {"healthy": "var(--gr)", "caution": "var(--am)", "critical": "var(--rd)"}


def test_insight_inputs_and_text_match_golden(golden) -> None:
    fixture = golden("insights")
    insights = generate_insights_v1(RECORDS, TREND, ANOMALIES, BACKTEST)
    early = first_half_fade(RECORDS)
    hero = overview_acceleration_v1(TREND.fade_pct_per_cycle, early)
    actual = {
        "inputs": {
            "first_soh_pct": RECORDS[0].soh_pct,
            "soh_now_pct": TREND.soh_now_pct,
            "n_cycles": len(RECORDS),
            "first_half_fade_pct_per_cycle": early,
            "recent_fade_pct_per_cycle": TREND.fade_pct_per_cycle,
            "temp_events": len(ANOMALIES.detected_cycles("temp")),
            "volt_events": len(ANOMALIES.detected_cycles("volt")),
            "backtest_mae": BACKTEST.mae,
        },
        "insights": [i.text for i in insights],
        "overview_hero": {"accelerated": hero.accelerated, "appended_text": hero.appended_text},
    }
    expected = {
        "inputs": fixture["inputs"],
        "insights": fixture["insights"],
        "overview_hero": {
            k: v
            for k, v in fixture["overview_hero"].items()
            if k in {"accelerated", "appended_text"}
        },
    }
    assert_matches(actual, expected, label="insights")


def test_display_rules_match_golden(golden) -> None:
    fixture = golden("display_rules")

    def row(soh: float) -> dict[str, object]:
        return {
            "soh_pct": soh,
            "colour": LEGACY_COLOUR[health_level(soh)],
            "condition": condition_label(soh),
        }

    actual = {
        "cases": [row(c["soh_pct"]) for c in fixture["cases"]],
        "current": row(TREND.soh_now_pct),
    }
    expected = {"cases": fixture["cases"], "current": fixture["current"]}
    assert_matches(actual, expected, label="display_rules")
