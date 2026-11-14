"""``analyze_v2()`` composes the eight fixes; the v2 simulation services wrap them unchanged."""

from __future__ import annotations

from app.analytics.analysis_v2 import analyze_v2
from app.analytics.jsmath import js_round
from app.analytics.legacy_v1 import analyze
from app.analytics.synthetic import SYNTHETIC_V1
from app.services.simulation import advisor_table_v2, simulate_v2

A2 = analyze_v2()


def test_defaults_to_synthetic_v1() -> None:
    assert A2.dataset_id == SYNTHETIC_V1.dataset_id
    assert A2.algorithm_version == "v2"
    assert analyze_v2(A2.records).dataset_id == "custom"


def test_every_fix_holds_in_the_composed_result() -> None:
    assert A2.anomalies.detected_cycles("temp") == [90, 170, 251]  # F1
    assert A2.anomalies.detected_cycles("soh") == []  # F2
    assert A2.rul_interval.label == "90% prediction interval"  # F3
    assert A2.rul_cycles is not None
    assert A2.simulator_baseline.cycles_to_eol == js_round(A2.rul_cycles)  # F4
    assert A2.insights[1].text.startswith("Fade is accelerating")  # F5 (true here)
    assert abs(A2.backtest.mean_signed_error) < 0.1  # F6
    assert A2.anomalies_causal.mode == "causal"  # F7
    assert all(r.comparison == "comparable" for r in A2.advisor.rows)  # F8


def test_v1_analysis_is_untouched() -> None:
    v1 = analyze()
    assert v1.algorithm_version == "v1"
    assert v1.anomalies.detected_cycles("temp") == [170]
    assert v1.simulator_baseline.cycles_to_eol == 106


def test_simulation_services() -> None:
    p = A2.simulator_defaults
    without = simulate_v2(p, A2.trend, include_trajectories=False)
    assert without.trajectory is None and without.comparison.cycles_to_eol == 97
    with_traj = simulate_v2(p, A2.trend, include_trajectories=True)
    assert with_traj.trajectory_cycles == list(range(p.horizon_cycles + 1))
    assert advisor_table_v2(p, A2.trend, None).baseline_cycles_to_eol == 97
    assert advisor_table_v2(p, A2.trend, 85.0).start_soh_pct == 85.0
