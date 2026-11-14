"""F2 (v2): no false capacity steps on clean data, and genuine steps are still detected.

v1 expectations (five false flags) stay in tests/parity and the strict-xfail F2 test.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.analytics.anomalies_v2 import (
    MIN_STEP_SOH_PCT,
    STEP_WINDOW,
    detect_anomalies_v2,
    step_size,
    steps_retrospective,
    suppress_neighbours,
    theil_sen,
)
from app.analytics.legacy_v1 import analyze
from app.analytics.synthetic import CycleRecord

A = analyze()
REPORT = detect_anomalies_v2(A.records)


def with_step(records: tuple[CycleRecord, ...], at: int, size: float) -> tuple[CycleRecord, ...]:
    """Inject a sustained capacity step of ``size`` SOH points from cycle ``at`` onwards."""
    return tuple(
        dataclasses.replace(r, soh_pct=r.soh_pct + (size if r.cycle >= at else 0.0))
        for r in records
    )


def test_f2_regression_no_capacity_steps_flagged_when_none_injected() -> None:
    """F2 acceptance (as in test_known_defects.py, for v2)."""
    assert REPORT.detected_cycles("soh") == []


def test_clean_data_stays_below_the_minimum_step() -> None:
    soh = next(c for c in REPORT.channels if c.spec.key == "soh")
    assert max(abs(v) for v in soh.values) < MIN_STEP_SOH_PCT == 0.5


@pytest.mark.parametrize("at", [60, 150, 200, 250, 300])
def test_an_injected_one_point_step_is_detected(at: int) -> None:
    """Recall: a sustained -1.0 SOH-point step is found once, near its onset, as high severity."""
    report = detect_anomalies_v2(with_step(A.records, at, -1.0))
    steps = [e for e in report.events if e.channel == "soh"]
    assert len(steps) == 1
    assert abs(steps[0].cycle - at) <= 4
    assert steps[0].value < -MIN_STEP_SOH_PCT
    assert steps[0].severity == "high"
    assert steps[0].type == "Capacity step" and steps[0].unit == "SOH pts"
    # The other channels are unaffected.
    assert report.detected_cycles("temp") == [90, 170, 251]


def test_steps_smaller_than_the_minimum_are_not_reported() -> None:
    report = detect_anomalies_v2(with_step(A.records, 200, -0.3))
    assert report.detected_cycles("soh") == []


def test_series_edges_are_not_evaluated() -> None:
    soh = next(c for c in REPORT.channels if c.spec.key == "soh")
    assert soh.cycles[0] == STEP_WINDOW
    assert soh.cycles[-1] == len(A.records) - STEP_WINDOW
    assert len(steps_retrospective([0.0] * 25)) == 25 - 2 * STEP_WINDOW + 1


def test_step_size_on_an_exact_step() -> None:
    values = [100 - 0.05 * i - (1.0 if i >= 30 else 0.0) for i in range(60)]
    step, predicted = step_size(values, 30)
    assert step == pytest.approx(-1.0, abs=1e-9)  # the trend is removed
    assert predicted == pytest.approx(100 - 0.05 * 34.5, abs=1e-9)


def test_theil_sen_ignores_an_outlier() -> None:
    xs = [float(i) for i in range(10)]
    ys = [2.0 * x + 1 for x in xs]
    ys[4] = 100.0
    slope, intercept = theil_sen(xs, ys)
    assert (slope, intercept) == (2.0, 1.0)
    with pytest.raises(ValueError, match="two distinct"):
        theil_sen([1.0, 1.0], [1.0, 2.0])


def test_neighbour_suppression_keeps_one_event_per_step() -> None:
    assert suppress_neighbours([(10, -0.6), (11, -0.9), (12, -0.7), (40, 0.8)], 10) == [11, 40]
