"""Unit tests for insights and display rules."""

from __future__ import annotations

import math

import pytest

from app.analytics.anomalies import detect_anomalies_v1
from app.analytics.backtest import run_backtest
from app.analytics.display import condition_label, health_level
from app.analytics.health import recent_trend
from app.analytics.insights import (
    ACCELERATION_NOTE,
    first_half_fade,
    generate_insights_v1,
    overview_acceleration_v1,
)
from app.analytics.synthetic import generate_synthetic_v1

RECORDS = generate_synthetic_v1()


def test_insights_are_structured_and_ordered() -> None:
    trend = recent_trend(RECORDS)
    insights = generate_insights_v1(
        RECORDS, trend, detect_anomalies_v1(RECORDS), run_backtest(RECORDS)
    )
    assert [i.kind for i in insights] == ["observation", "watch", "note", "model"]
    assert insights[1].values["first_half_fade_pct_per_cycle"] == first_half_fade(RECORDS)
    assert insights[2].values == {"temp_events": 1, "volt_events": 2}
    assert all(i.provenance == "fitted" for i in insights)


@pytest.mark.parametrize(
    ("fade", "early", "accelerated"),
    [(0.054, 0.036, True), (0.0431, 0.036, False), (0.05, 0.05, False), (0.02, 0.05, False)],
)
def test_overview_acceleration_rule(fade: float, early: float, accelerated: bool) -> None:
    note = overview_acceleration_v1(fade, early)
    assert note.accelerated is accelerated
    assert note.appended_text == (ACCELERATION_NOTE if accelerated else "")


@pytest.mark.parametrize(
    ("soh", "level", "label"),
    [
        (100.0, "healthy", "Healthy"),
        (90.0, "healthy", "Healthy"),
        (89.99, "healthy", "Good"),
        (85.0, "healthy", "Good"),
        (84.99, "caution", "Approaching end-of-life threshold"),
        (80.0, "caution", "Approaching end-of-life threshold"),
        (79.99, "critical", "Below threshold"),
        (math.nan, "critical", "Below threshold"),
    ],
)
def test_display_rules(soh: float, level: str, label: str) -> None:
    assert health_level(soh) == level
    assert condition_label(soh) == label
