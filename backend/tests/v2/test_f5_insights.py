"""F5 (v2): the fade insight follows the numbers (accelerating / slowing / steady).

v1 expectations stay in tests/parity and the strict-xfail F5 test.
"""

from __future__ import annotations

import pytest

from app.analytics.anomalies import detect_anomalies_v1
from app.analytics.anomalies_v2 import detect_anomalies_v2
from app.analytics.backtest import run_backtest
from app.analytics.forecast_v2 import recent_trend_v2, run_backtest_v2
from app.analytics.health import recent_trend
from app.analytics.insights import first_half_fade, generate_insights_v1
from app.analytics.insights_v2 import (
    ACCELERATION_NOTE_V2,
    classify_fade,
    generate_insights_v2,
    overview_acceleration_v2,
    signed,
)
from app.analytics.legacy_v1 import analyze
from app.analytics.synthetic import CycleRecord

A = analyze()


def piecewise(early_rate: float, late_rate: float) -> tuple[CycleRecord, ...]:
    """Noise-free SOH: ``early_rate`` for cycles 0-159, then ``late_rate``."""
    knee = 100 - early_rate * 160
    return tuple(
        CycleRecord(
            i,
            0.0,
            100 - early_rate * i if i < 160 else knee - late_rate * (i - 160),
            25.0,
            3.7,
        )
        for i in range(320)
    )


def insights(records: tuple[CycleRecord, ...]):
    return generate_insights_v2(
        records,
        recent_trend_v2(records),
        detect_anomalies_v2(records),
        run_backtest_v2(records),
    )


def test_f5_regression_slowing_fade_is_not_called_accelerating() -> None:
    """F5 acceptance (the dataset of test_known_defects.py, for v2)."""
    fade = insights(piecewise(0.08, 0.02))[1]
    assert "accelerating" not in fade.text
    assert fade.text.startswith("Fade is slowing:")
    assert fade.kind == "observation"


def test_accelerating_fade() -> None:
    fade = insights(piecewise(0.02, 0.08))[1]
    assert fade.text.startswith("Fade is accelerating:")
    assert fade.text.endswith("(more than 1.2×).")
    assert fade.kind == "watch"
    assert fade.values["fade_ratio"] == pytest.approx(4.0, rel=1e-6)


def test_steady_fade() -> None:
    fade = insights(piecewise(0.05, 0.05))[1]
    assert fade.text == (
        "Fade is steady: first-half 0.050 vs current 0.050 %/cycle (within 1.2× either way)."
    )


@pytest.mark.parametrize(
    ("recent", "early", "expected"),
    [
        (0.0601, 0.05, "accelerating"),
        (0.06, 0.05, "steady"),  # exactly 1.2×: not more than
        (0.05 / 1.2, 0.05, "steady"),  # exactly 1/1.2×: not less than
        (0.041, 0.05, "slowing"),
        (0.05, 0.0, "accelerating"),  # no early fade to compare
        (0.0, 0.0, "steady"),
    ],
)
def test_classify_fade_rule(recent, early, expected) -> None:
    assert classify_fade(recent, early) == expected


def test_synthetic_v1_expected_text() -> None:
    texts = [i.text for i in insights(A.records)]
    assert texts[0] == (
        "Capacity fell from 99.9% to 86.0% SOH over 320 cycles; current fade is 0.059 %/cycle."
    )
    assert texts[1] == (
        "Fade is accelerating: first-half 0.036 vs current 0.059 %/cycle (more than 1.2×)."
    )
    assert texts[2].startswith("3 temperature and 2 voltage events were flagged.")
    assert texts[3] == (
        "The interim quadratic forecast has a hold-out MAE of 0.10 SOH points and a bias of"
        " +0.04; treat the RUL as an estimate."
    )


def test_overview_note_uses_the_same_rule() -> None:
    early = first_half_fade(A.records)
    assert overview_acceleration_v2(0.0585, early).appended_text == ACCELERATION_NOTE_V2
    assert overview_acceleration_v2(early, early).accelerated is False
    assert overview_acceleration_v2(early, early).appended_text == ""


def test_signed() -> None:
    assert signed(0.0418, 2) == "+0.04"
    assert signed(-0.0418, 2) == "-0.04"


def test_v1_insight_is_unchanged() -> None:
    slowing = piecewise(0.08, 0.02)
    v1 = generate_insights_v1(
        slowing, recent_trend(slowing), detect_anomalies_v1(slowing), run_backtest(slowing)
    )
    assert "accelerating" in v1[1].text  # the v1 defect, kept on purpose
