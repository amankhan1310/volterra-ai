"""F1 (v2): detrending finds every injected temperature spike (and only the injected anomalies).

v1 expectations stay in tests/parity and the strict-xfail F1 test.
"""

from __future__ import annotations

import pytest

from app.analytics.anomalies_v2 import (
    DETECTOR_V2,
    POINT_HALF_WINDOW,
    detect_anomalies_v2,
    residuals_retrospective,
    robust_scale,
)
from app.analytics.legacy_v1 import analyze
from app.analytics.synthetic import SYNTHETIC_V1

A = analyze()
REPORT = detect_anomalies_v2(A.records)


def test_f1_regression_all_injected_temperature_spikes_are_detected() -> None:
    """F1 acceptance (as in test_known_defects.py, for v2)."""
    assert REPORT.detected_cycles("temp") == list(SYNTHETIC_V1.temp_spike_cycles)


def test_voltage_finds_exactly_the_injected_dips() -> None:
    assert REPORT.detected_cycles("volt") == list(SYNTHETIC_V1.voltage_dip_cycles)


@pytest.mark.parametrize(
    ("channel", "injected"),
    [("temp", SYNTHETIC_V1.temp_spike_cycles), ("volt", SYNTHETIC_V1.voltage_dip_cycles)],
)
def test_precision_and_recall_on_labelled_injections(channel, injected) -> None:
    found = set(REPORT.detected_cycles(channel))
    true_pos = found & set(injected)
    assert len(true_pos) / len(found) == 1.0  # precision (v1 temperature: 1/1, recall 1/3)
    assert len(true_pos) / len(injected) == 1.0  # recall


def test_events_follow_the_local_baseline() -> None:
    spike_90 = next(e for e in REPORT.events if e.cycle == 90)
    assert spike_90.type == "Temperature excursion"
    assert spike_90.value > spike_90.expected_high  # above the local band
    assert spike_90.expected_high < 30  # cool phase of the wave: band is local, not global
    assert spike_90.z > 3.5
    assert REPORT.detector == DETECTOR_V2 and REPORT.version == "v2"
    assert REPORT.mode == "retrospective"


def test_edge_cycles_are_not_evaluated() -> None:
    temp = next(c for c in REPORT.channels if c.spec.key == "temp")
    assert temp.cycles[0] == POINT_HALF_WINDOW
    assert temp.cycles[-1] == len(A.records) - 1 - POINT_HALF_WINDOW
    assert len(temp.values) == len(temp.z) == len(temp.cycles)


def test_counts_by_severity() -> None:
    assert REPORT.count() == 5
    assert REPORT.count("high") + REPORT.count("medium") == 5


def test_residuals_skip_truncated_windows() -> None:
    values = [float(i) for i in range(20)]
    res = residuals_retrospective(values, half=3)
    assert [r.index for r in res] == list(range(3, 17))
    assert all(r.residual == 0 for r in res)  # a straight line has no residual


def test_robust_scale_floors_a_flat_series() -> None:
    assert robust_scale([1.0, 1.0, 1.0]) == (1.0, 1e-9)
