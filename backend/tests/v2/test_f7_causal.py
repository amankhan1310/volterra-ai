"""F7 (v2): a live (causal) mode whose results cannot depend on future cycles.

v1 expectations stay in tests/parity and the strict-xfail F7 test.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.analytics.anomalies_v2 import (
    CAUSAL_FIT_WINDOW,
    CAUSAL_MIN_HISTORY,
    STEP_WINDOW,
    AnomalyReportV2,
    detect_anomalies_v2,
    first_of_each_run,
    step_size,
    steps_causal,
)
from app.analytics.legacy_v1 import analyze
from app.analytics.synthetic import SYNTHETIC_V1, CycleRecord

A = analyze()
CAUSAL = detect_anomalies_v2(A.records, mode="causal")


def change_after(records: tuple[CycleRecord, ...], k: int) -> tuple[CycleRecord, ...]:
    """Rewrite every channel of every cycle after ``k`` (large, irregular changes)."""
    return tuple(
        r
        if r.cycle <= k
        else dataclasses.replace(
            r,
            soh_pct=r.soh_pct + 5.0 + (r.cycle % 7),
            temp_c=r.temp_c + 12.0 * ((r.cycle % 3) - 1),
            voltage_v=r.voltage_v - 0.3 * (r.cycle % 2),
        )
        for r in records
    )


def upto(report: AnomalyReportV2, k: int) -> tuple:
    """Everything the report says about cycles <= k: events and per-cycle inputs/z-scores."""
    events = tuple(e for e in report.events if e.cycle <= k)
    channels = tuple(
        tuple(
            (cycle, value, z)
            for cycle, value, z in zip(c.cycles, c.values, c.z, strict=True)
            if cycle <= k
        )
        for c in report.channels
    )
    return events, channels


def test_f7_regression_capacity_statistic_is_causal() -> None:
    """F7 acceptance (as in test_known_defects.py, for v2): changing cycles > 100 leaves the
    capacity statistic at cycle 100 unchanged."""
    soh = [r.soh_pct for r in A.records]
    changed_future = soh[:101] + [v + 5.0 for v in soh[101:]]
    at_100 = {s.index: s.residual for s in steps_causal(soh)}[100]
    assert {s.index: s.residual for s in steps_causal(changed_future)}[100] == at_100


@pytest.mark.parametrize("k", [80, 100, 150, 250, 318])
def test_causal_results_cannot_be_changed_by_future_data(k: int) -> None:
    changed = detect_anomalies_v2(change_after(A.records, k), mode="causal")
    assert upto(changed, k) == upto(CAUSAL, k)


def test_retrospective_mode_does_look_ahead() -> None:
    """The default (look back over history) mode legitimately uses later cycles."""
    retro = detect_anomalies_v2(A.records)
    changed = detect_anomalies_v2(change_after(A.records, 150))
    assert upto(changed, 150) != upto(retro, 150)
    assert retro.mode == "retrospective" and CAUSAL.mode == "causal"


def test_causal_mode_finds_the_injected_anomalies_without_false_steps() -> None:
    assert CAUSAL.detected_cycles("temp") == list(SYNTHETIC_V1.temp_spike_cycles)
    assert CAUSAL.detected_cycles("volt") == list(SYNTHETIC_V1.voltage_dip_cycles)
    assert CAUSAL.detected_cycles("soh") == []


@pytest.mark.parametrize("at", [100, 200, 300])
def test_causal_mode_detects_a_step_after_it_happens(at: int) -> None:
    stepped = tuple(
        dataclasses.replace(r, soh_pct=r.soh_pct - (1.0 if r.cycle >= at else 0.0))
        for r in A.records
    )
    found = detect_anomalies_v2(stepped, mode="causal").detected_cycles("soh")
    assert len(found) == 1
    assert at <= found[0] <= at + STEP_WINDOW  # reported at detection, never before the step


def test_causal_mode_needs_history_before_judging() -> None:
    temp, _volt, soh = CAUSAL.channels
    assert temp.cycles[0] == CAUSAL_FIT_WINDOW + CAUSAL_MIN_HISTORY
    assert soh.cycles[0] == 2 * STEP_WINDOW - 1 + CAUSAL_MIN_HISTORY


def test_causal_step_uses_only_cycles_up_to_detection() -> None:
    values = [float(i % 5) for i in range(40)]
    detection = 30
    stat = {s.index: s.residual for s in steps_causal(values)}[detection]
    onset = detection - STEP_WINDOW + 1
    assert stat == step_size(values, onset)[0]
    assert onset + STEP_WINDOW - 1 == detection  # the after-window ends at the detection cycle


def test_first_of_each_run() -> None:
    assert first_of_each_run([100, 101, 105, 140, 141], 10) == [100, 140]
    assert first_of_each_run([], 10) == []
