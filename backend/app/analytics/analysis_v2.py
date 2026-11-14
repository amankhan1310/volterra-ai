"""End-to-end v2 analysis: the corrected methods for F1-F8, in one immutable result.

``analyze_v2()`` is the v2 counterpart of :func:`app.analytics.legacy_v1.analyze`. v1 stays
permanent and is the API default; v2 is opt-in (``?algorithm=v2``). Each part fixes one known
prototype defect (ARCHITECTURE_PLAN.md §3.6; see CHANGELOG.md):

* forecast (F6, interim quadratic) and its calibrated 90% prediction interval (F3)
* anomalies: detrended point detection (F1), a capacity-step detector (F2), a causal mode (F7)
* simulator baseline anchored to the shared forecast (F4) and the advisor's explicit
  "cannot compare" state (F8)
* rule-based fade insight (F5)

Display rules shared with v1 (health level, condition label, forecast extent, gauge fraction) are
reused unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.analytics.advisor_v2 import AdvisorTableV2, sensitivity_table_v2
from app.analytics.anomalies_v2 import AnomalyReportV2, detect_anomalies_v2
from app.analytics.display import HealthLevel, condition_label, health_level
from app.analytics.forecast_v2 import (
    BacktestResultV2,
    PredictionIntervalV2,
    TrendSummaryV2,
    forecast_series_v2,
    recent_trend_v2,
    rolling_origin_errors,
    rul_interval_v2,
    rul_v2,
    run_backtest_v2,
)
from app.analytics.health import DEFAULT_EOL_PCT, forecast_extent, life_used_fraction
from app.analytics.insights import AccelerationNote, Insight, first_half_fade
from app.analytics.insights_v2 import generate_insights_v2, overview_acceleration_v2
from app.analytics.simulator import ScenarioComparison, ScenarioParams
from app.analytics.simulator_v2 import compare_to_baseline_v2, default_params_v2
from app.analytics.synthetic import SYNTHETIC_V1, CycleRecord, generate_synthetic_v1

ALGORITHM_VERSION_V2 = "v2"


@dataclass(frozen=True)
class AnalysisV2:
    dataset_id: str
    records: tuple[CycleRecord, ...]
    eol_pct: float
    trend: TrendSummaryV2
    rul_cycles: float | None
    rul_interval: PredictionIntervalV2
    forecast_extent: int
    forecast: tuple[float, ...]
    life_used_fraction: float
    health_level: HealthLevel
    condition: str
    backtest: BacktestResultV2
    #: Retrospective detection (look back over history): the default.
    anomalies: AnomalyReportV2
    #: Causal (live) detection: never uses later cycles.
    anomalies_causal: AnomalyReportV2
    insights: tuple[Insight, ...]
    acceleration: AccelerationNote
    simulator_defaults: ScenarioParams
    simulator_baseline: ScenarioComparison
    advisor: AdvisorTableV2
    algorithm_version: str = ALGORITHM_VERSION_V2


def analyze_v2(
    records: Sequence[CycleRecord] | None = None,
    *,
    eol_pct: float = DEFAULT_EOL_PCT,
    dataset_id: str | None = None,
) -> AnalysisV2:
    """Run every v2 analysis. Defaults to the ``synthetic-v1`` dataset and an 80% EOL."""
    if records is None:
        data = generate_synthetic_v1()
        dataset_id = dataset_id or SYNTHETIC_V1.dataset_id
    else:
        data = tuple(records)
    trend = recent_trend_v2(data)
    rul = rul_v2(trend, eol_pct)
    extent = forecast_extent(trend.n_cycles, rul)
    anomalies = detect_anomalies_v2(data)
    backtest = run_backtest_v2(data)
    defaults = default_params_v2(trend, eol_pct)
    return AnalysisV2(
        dataset_id=dataset_id or "custom",
        records=data,
        eol_pct=eol_pct,
        trend=trend,
        rul_cycles=rul,
        rul_interval=rul_interval_v2(trend, rolling_origin_errors(data), eol_pct),
        forecast_extent=extent,
        forecast=tuple(forecast_series_v2(trend, extent)),
        life_used_fraction=life_used_fraction(trend.soh_now_pct, eol_pct),
        health_level=health_level(trend.soh_now_pct),
        condition=condition_label(trend.soh_now_pct),
        backtest=backtest,
        anomalies=anomalies,
        anomalies_causal=detect_anomalies_v2(data, mode="causal"),
        insights=generate_insights_v2(data, trend, anomalies, backtest),
        acceleration=overview_acceleration_v2(trend.fade_pct_per_cycle, first_half_fade(data)),
        simulator_defaults=defaults,
        simulator_baseline=compare_to_baseline_v2(defaults.with_baseline_conditions(), trend),
        advisor=sensitivity_table_v2(defaults, trend),
    )
