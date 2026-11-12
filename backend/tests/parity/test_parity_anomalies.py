"""Parity: the v1 detector matches ``anomalies.json``, defects F1/F2/F7 included.

Only temperature-derived values (from ``Math.sin``) may use the documented 1e-12 tolerance.
"""

from __future__ import annotations

from app.analytics.anomalies import FLAG_ABS_Z, HIGH_ABS_Z, detect_anomalies_v1
from app.analytics.synthetic import SYNTHETIC_V1, generate_synthetic_v1
from tests.support.golden import assert_matches

REPORT = detect_anomalies_v1(generate_synthetic_v1())


def test_method_constants_match_golden(golden) -> None:
    method = golden("anomalies")["method"]
    actual = {"flag_threshold_abs_z": FLAG_ABS_Z, "high_severity_abs_z": HIGH_ABS_Z}
    expected = {k: method[k] for k in actual}
    assert_matches(actual, expected, label="anomalies:method")


def test_channel_statistics_match_golden(golden) -> None:
    expected = [
        {k: v for k, v in c.items() if k != "input"} for c in golden("anomalies")["channels"]
    ]
    actual = []
    for stats in REPORT.channels:
        row: dict[str, object] = {
            "channel": stats.spec.key,
            "label": stats.spec.label,
            "unit": stats.spec.unit,
            "median": stats.median,
            "mad": stats.mad,
            "expected_low": stats.expected_low,
            "expected_high": stats.expected_high,
            "z": list(stats.z),
        }
        if stats.spec.key == "soh":
            row["input_values"] = list(stats.values)
        actual.append(row)
    temp = next(i for i, c in enumerate(expected) if c["channel"] == "temp")
    assert_matches(actual, expected, label="anomalies:channels", tolerant=[(temp, "**")])


def test_events_and_summary_match_golden(golden) -> None:
    fixture = golden("anomalies")
    events = [
        {
            "cycle": e.cycle,
            "channel": e.channel,
            "type": e.type,
            "value": e.value,
            "unit": e.unit,
            "expected_low": e.expected_low,
            "expected_high": e.expected_high,
            "z": e.z,
            "severity": e.severity,
        }
        for e in REPORT.events
    ]
    temp_events = [(i, "**") for i, e in enumerate(fixture["events"]) if e["channel"] == "temp"]
    assert_matches(events, fixture["events"], label="anomalies:events", tolerant=temp_events)
    summary = {
        "total": REPORT.count(),
        "high": REPORT.count("high"),
        "medium": REPORT.count("medium"),
    }
    assert_matches(summary, fixture["summary"], label="anomalies:summary")


def test_ground_truth_vs_detected_reproduces_f1_and_f2(golden) -> None:
    actual = {
        "temp": {
            "injected": list(SYNTHETIC_V1.temp_spike_cycles),
            "detected": REPORT.detected_cycles("temp"),
        },
        "volt": {
            "injected": list(SYNTHETIC_V1.voltage_dip_cycles),
            "detected": REPORT.detected_cycles("volt"),
        },
        "soh": {"injected": [], "detected": REPORT.detected_cycles("soh")},
    }
    expected = golden("anomalies")["ground_truth_vs_detected"]
    assert_matches(actual, expected, label="anomalies:ground_truth")
