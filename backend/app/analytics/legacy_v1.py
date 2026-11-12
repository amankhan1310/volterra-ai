"""End-to-end v1 analysis: everything the legacy prototype computed, in one immutable result.

``analyze()`` is the Python equivalent of the prototype's top-level state (``D``, ``F``,
``sohNow``, ``fade``, ``BT``, ``AN``, ``P``, ``insights()``, Overview and Advisor values). It is
the single entry point later phases (API, UI) use for the ``synthetic-v1`` behaviour. All
algorithms are v1 and reproduce the prototype exactly, including known defects F1–F8.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass

from app.analytics.advisor import AdvisorTable, sensitivity_table
from app.analytics.anomalies import AnomalyReport, detect_anomalies_v1
from app.analytics.backtest import BacktestResult, run_backtest
from app.analytics.display import HealthLevel, condition_label, health_level
from app.analytics.health import (
    DEFAULT_EOL_PCT,
    RulInterval,
    TrendSummary,
    forecast_extent,
    forecast_series,
    life_used_fraction,
    recent_trend,
    rul_at,
    rul_interval_95,
)
from app.analytics.insights import (
    AccelerationNote,
    Insight,
    first_half_fade,
    generate_insights_v1,
    overview_acceleration_v1,
)
from app.analytics.simulator import (
    ScenarioComparison,
    ScenarioParams,
    compare_to_baseline,
    default_params,
)
from app.analytics.synthetic import SYNTHETIC_V1, CycleRecord, generate_synthetic_v1

ALGORITHM_VERSION = "v1"


@dataclass(frozen=True)
class LegacyV1Analysis:
    dataset_id: str
    records: tuple[CycleRecord, ...]
    eol_pct: float
    trend: TrendSummary
    rul_cycles: float | None
    rul_interval: RulInterval
    forecast_extent: int
    forecast: tuple[float, ...]
    life_used_fraction: float
    health_level: HealthLevel
    condition: str
    backtest: BacktestResult
    anomalies: AnomalyReport
    insights: tuple[Insight, ...]
    acceleration: AccelerationNote
    simulator_defaults: ScenarioParams
    simulator_baseline: ScenarioComparison
    advisor: AdvisorTable
    algorithm_version: str = ALGORITHM_VERSION


def analyze(
    records: Sequence[CycleRecord] | None = None,
    *,
    eol_pct: float = DEFAULT_EOL_PCT,
    dataset_id: str | None = None,
) -> LegacyV1Analysis:
    """Run every v1 analysis. Defaults to the ``synthetic-v1`` dataset and an 80% EOL."""
    if records is None:
        data = generate_synthetic_v1()
        dataset_id = dataset_id or SYNTHETIC_V1.dataset_id
    else:
        data = tuple(records)
    trend = recent_trend(data)
    rul = rul_at(trend, eol_pct)
    extent = forecast_extent(trend.n_cycles, rul)
    anomalies = detect_anomalies_v1(data)
    backtest = run_backtest(data)
    defaults = dataclasses.replace(default_params(trend.soh_now_pct), eol_pct=eol_pct)
    fade = trend.fade_pct_per_cycle
    return LegacyV1Analysis(
        dataset_id=dataset_id or "custom",
        records=data,
        eol_pct=eol_pct,
        trend=trend,
        rul_cycles=rul,
        rul_interval=rul_interval_95(trend, eol_pct),
        forecast_extent=extent,
        forecast=tuple(forecast_series(trend, extent)),
        life_used_fraction=life_used_fraction(trend.soh_now_pct, eol_pct),
        health_level=health_level(trend.soh_now_pct),
        condition=condition_label(trend.soh_now_pct),
        backtest=backtest,
        anomalies=anomalies,
        insights=generate_insights_v1(data, trend, anomalies, backtest),
        acceleration=overview_acceleration_v1(fade, first_half_fade(data)),
        simulator_defaults=defaults,
        simulator_baseline=compare_to_baseline(defaults.with_baseline_conditions(), fade),
        advisor=sensitivity_table(defaults, fade),
    )
