"""Map v1 analysis results to API schemas.

Rule (enforced by tests/unit/test_api_purity.py): mappers only **copy** values. No arithmetic,
rounding or aggregation happens here, so API responses carry exactly the numbers produced by
``legacy_v1.analyze()`` and the other v1 analytics functions.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.analytics.legacy_v1 import LegacyV1Analysis
from app.analytics.stats import LinearFit
from app.analytics.synthetic import CycleRecord
from app.db.repositories import BatteryInfo, DatasetInfo
from app.schemas.analysis import (
    AccelerationOut,
    AnomalyCounts,
    BacktestPointOut,
    BacktestResponse,
    CycleWindow,
    ForecastResponse,
    InsightOut,
    InsightsResponse,
    LatestCycle,
    LinearFitOut,
    SeriesOut,
    SummaryResponse,
    TrendOut,
)
from app.schemas.common import AnalysisContext, Interval, Quantity, data_provenance
from app.schemas.datasets import BatteryOut, CycleOut, CyclesResponse, DatasetOut
from app.services.analysis import BatteryAnalysis


def context(battery: BatteryInfo, eol_pct: float | None = None) -> AnalysisContext:
    return AnalysisContext(
        battery_id=battery.id,
        dataset=battery.dataset_slug,
        is_synthetic=battery.is_synthetic,
        data_provenance=data_provenance(battery.is_synthetic),
        eol_pct=eol_pct,
    )


def dataset_out(d: DatasetInfo) -> DatasetOut:
    # `meta` (internal metadata such as synthetic ground truth) is deliberately not mapped.
    return DatasetOut(
        slug=d.slug,
        name=d.name,
        source=d.source,
        version=d.version,
        licence=d.licence,
        citation=d.citation,
        description=d.description,
        status=d.status,
        checksum=d.checksum,
        synthetic=d.source == "synthetic",
        battery_count=d.battery_count,
    )


def battery_out(b: BatteryInfo) -> BatteryOut:
    return BatteryOut(
        id=b.id,
        external_id=b.external_id,
        dataset=b.dataset_slug,
        dataset_name=b.dataset_name,
        chemistry=b.chemistry,
        form_factor=b.form_factor,
        nominal_capacity_ah=b.nominal_capacity_ah,
        nominal_voltage_v=b.nominal_voltage_v,
        eol_threshold_pct=b.eol_threshold_pct,
        is_synthetic=b.is_synthetic,
        data_provenance=data_provenance(b.is_synthetic),
        cycle_count=b.cycle_count,
    )


CYCLE_UNITS = {"capacity_ah": "Ah", "soh_pct": "%", "temp_c": "°C", "voltage_v": "V"}


def cycle_out(r: CycleRecord) -> CycleOut:
    return CycleOut(
        cycle=r.cycle,
        capacity_ah=r.capacity_ah,
        soh_pct=r.soh_pct,
        temp_c=r.temp_c,
        voltage_v=r.voltage_v,
    )


def cycles_response(battery: BatteryInfo, records: Sequence[CycleRecord]) -> CyclesResponse:
    return CyclesResponse(
        context=context(battery),
        provenance=data_provenance(battery.is_synthetic),
        units=CYCLE_UNITS,
        items=[cycle_out(r) for r in records],
    )


# --- Overview analytics (v1) --------------------------------------------------------------------

FORECAST_METHOD = "linear_trend_recent_120_cycles"


def linear_fit_out(fit: LinearFit) -> LinearFitOut:
    return LinearFitOut(
        slope=fit.slope,
        intercept=fit.intercept,
        residual_sd=fit.residual_sd,
        slope_se=fit.slope_se,
    )


def acceleration_out(a: LegacyV1Analysis) -> AccelerationOut:
    return AccelerationOut(
        accelerated=a.acceleration.accelerated, note=a.acceleration.appended_text
    )


def summary_response(ba: BatteryAnalysis) -> SummaryResponse:
    a, battery = ba.analysis, ba.battery
    data = data_provenance(battery.is_synthetic)
    latest = ba.records[-1]
    return SummaryResponse(
        context=context(battery, a.eol_pct),
        soh_now=Quantity(value=a.trend.soh_now_pct, unit="%", provenance="fitted"),
        observed_last_soh=Quantity(value=a.trend.observed_last_soh_pct, unit="%", provenance=data),
        fade_rate=Quantity(value=a.trend.fade_pct_per_cycle, unit="%/cycle", provenance="fitted"),
        rul=Interval(
            point=a.rul_cycles,
            lower=a.rul_interval.lower,
            upper=a.rul_interval.upper,
            level=a.rul_interval.level,
            method=a.rul_interval.method,
            unit="cycles",
            provenance="predicted",
        ),
        health_level=a.health_level,
        condition=a.condition,
        life_used_fraction=Quantity(
            value=a.life_used_fraction, unit="fraction", provenance="fitted"
        ),
        cycle_count=len(ba.records),
        latest=LatestCycle(
            cycle=latest.cycle,
            capacity=Quantity(value=latest.capacity_ah, unit="Ah", provenance=data),
            temperature=Quantity(value=latest.temp_c, unit="°C", provenance=data),
            voltage=Quantity(value=latest.voltage_v, unit="V", provenance=data),
        ),
        anomalies=AnomalyCounts(
            total=a.anomalies.count(),
            high=a.anomalies.count("high"),
            medium=a.anomalies.count("medium"),
        ),
        acceleration=acceleration_out(a),
        trend=TrendOut(
            fit_from_cycle=a.trend.fit_from_cycle,
            fit_to_cycle=a.trend.fit_to_cycle,
            **linear_fit_out(a.trend.fit).model_dump(),
        ),
    )


def forecast_response(ba: BatteryAnalysis) -> ForecastResponse:
    a, battery = ba.analysis, ba.battery
    return ForecastResponse(
        context=context(battery, a.eol_pct),
        observed=SeriesOut(
            cycles=[r.cycle for r in ba.records],
            values=[r.soh_pct for r in ba.records],
            unit="%",
            provenance=data_provenance(battery.is_synthetic),
        ),
        forecast=SeriesOut(
            cycles=list(range(a.trend.fit_to_cycle, a.forecast_extent)),
            values=list(a.forecast),
            unit="%",
            provenance="predicted",
        ),
        method=FORECAST_METHOD,
        extent_cycles=a.forecast_extent,
        prediction_boundary_cycle=a.trend.fit_to_cycle,
    )


def backtest_response(ba: BatteryAnalysis) -> BacktestResponse:
    bt = ba.analysis.backtest
    return BacktestResponse(
        context=context(ba.battery),
        train=CycleWindow(from_cycle=bt.train_from_cycle, to_cycle=bt.train_to_cycle),
        test=CycleWindow(from_cycle=bt.test_from_cycle, to_cycle=bt.test_to_cycle),
        fit=linear_fit_out(bt.fit),
        points=[
            BacktestPointOut(
                cycle=p.cycle,
                observed_soh_pct=p.observed_soh_pct,
                predicted_soh_pct=p.predicted_soh_pct,
                abs_error=p.abs_error,
            )
            for p in bt.points
        ],
        mae=Quantity(value=bt.mae, unit="SOH points", provenance="fitted"),
    )


def insights_response(ba: BatteryAnalysis) -> InsightsResponse:
    a = ba.analysis
    return InsightsResponse(
        context=context(ba.battery),
        insights=[InsightOut(kind=i.kind, text=i.text, values=dict(i.values)) for i in a.insights],
        acceleration=acceleration_out(a),
    )
