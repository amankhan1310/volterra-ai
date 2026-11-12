"""Map v1 analysis results to API schemas.

Rule (enforced by tests/unit/test_api_purity.py): mappers only **copy** values. No arithmetic,
rounding or aggregation happens here, so API responses carry exactly the numbers produced by
``legacy_v1.analyze()`` and the other v1 analytics functions.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.analytics.advisor import AdvisorTable
from app.analytics.anomalies import (
    FLAG_ABS_Z,
    HIGH_ABS_Z,
    MAD_FLOOR,
    RESIDUAL_HALF_WINDOW,
    Z_SCALE,
)
from app.analytics.display import health_level
from app.analytics.legacy_v1 import LegacyV1Analysis
from app.analytics.simulator import (
    ACCELERATION_CYCLES,
    BASELINE_C_RATE,
    BASELINE_DOD_PCT,
    BASELINE_TEMP_C,
    C_RATE_LINEAR,
    DOD_EXPONENT,
    LEGACY_KEYS,
    SIMULATOR_VERSION,
    SLIDERS,
    TEMP_EXP_PER_C,
    ScenarioParams,
)
from app.analytics.stats import LinearFit
from app.analytics.synthetic import CycleRecord
from app.analytics.twin import TWIN_MODULE_COUNT, temperature_band
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
from app.schemas.monitoring import (
    AnomaliesResponse,
    AnomalyEventOut,
    AnomalyMethodOut,
    ChannelStatsOut,
    DetectorOut,
    TwinModules,
    TwinPack,
    TwinResponse,
)
from app.schemas.simulator import (
    AdvisorResponse,
    AdvisorRowOut,
    BaselineConditions,
    CoefficientOut,
    ScenarioParamsModel,
    SimulateResponse,
    SimulatorConfigResponse,
    SliderOut,
    TrajectoriesOut,
)
from app.services.analysis import BatteryAnalysis
from app.services.simulation import SimulationResult


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


# --- Anomalies and digital twin (v1) ------------------------------------------------------------

ANOMALY_KNOWN_ISSUES = ["F1", "F2", "F7"]
TWIN_NOTE = (
    "The dataset has pack-level measurements only; every module shows the pack value "
    "(illustrative, not a per-cell measurement)."
)


def anomalies_response(ba: BatteryAnalysis, include_scores: bool) -> AnomaliesResponse:
    report = ba.analysis.anomalies
    channels = (
        [
            ChannelStatsOut(
                channel=c.spec.key,
                label=c.spec.label,
                unit=c.spec.unit,
                median=c.median,
                mad=c.mad,
                expected_low=c.expected_low,
                expected_high=c.expected_high,
                values=list(c.values),
                z=list(c.z),
            )
            for c in report.channels
        ]
        if include_scores
        else None
    )
    return AnomaliesResponse(
        context=context(ba.battery),
        detector=DetectorOut(name=report.detector, version=report.version, mode=report.mode),
        method=AnomalyMethodOut(
            z_scale=Z_SCALE,
            flag_threshold_abs_z=FLAG_ABS_Z,
            high_severity_abs_z=HIGH_ABS_Z,
            mad_floor=MAD_FLOOR,
            residual_half_window=RESIDUAL_HALF_WINDOW,
        ),
        summary=AnomalyCounts(
            total=report.count(), high=report.count("high"), medium=report.count("medium")
        ),
        events=[
            AnomalyEventOut(
                cycle=e.cycle,
                channel=e.channel,
                type=e.type,
                value=e.value,
                unit=e.unit,
                expected_low=e.expected_low,
                expected_high=e.expected_high,
                z=e.z,
                severity=e.severity,
            )
            for e in report.events
        ],
        channels=channels,
        known_issues=ANOMALY_KNOWN_ISSUES,
    )


def twin_response(battery: BatteryInfo, record: CycleRecord, last_cycle: int) -> TwinResponse:
    data = data_provenance(battery.is_synthetic)
    return TwinResponse(
        context=context(battery),
        cycle=record.cycle,
        last_cycle=last_cycle,
        pack=TwinPack(
            soh=Quantity(value=record.soh_pct, unit="%", provenance=data),
            capacity=Quantity(value=record.capacity_ah, unit="Ah", provenance=data),
            temperature=Quantity(value=record.temp_c, unit="°C", provenance=data),
            voltage=Quantity(value=record.voltage_v, unit="V", provenance=data),
        ),
        health_level=health_level(record.soh_pct),
        temperature_band=temperature_band(record.temp_c),
        modules=TwinModules(count=TWIN_MODULE_COUNT, note=TWIN_NOTE),
    )


# --- Simulator and Charging Advisor (v1) --------------------------------------------------------

SIMULATOR_MODEL = (
    "soh(n) = S - r*n*(1 + n/1500), r = base_fade * exp(0.06*(T-25)) * (1 + 0.4*(C-1)) "
    "* (D/80)^0.9; stress coefficients are assumed, not fitted"
)
ADVISOR_NOTE = (
    "Modelled direction and relative size under the simulator's assumed coefficients; "
    "not guaranteed battery-life gains."
)


def params_model(p: ScenarioParams) -> ScenarioParamsModel:
    return ScenarioParamsModel(
        temp_c=p.temp_c,
        c_rate=p.c_rate,
        dod_pct=p.dod_pct,
        horizon_cycles=p.horizon_cycles,
        start_soh_pct=p.start_soh_pct,
        eol_pct=p.eol_pct,
    )


def scenario_params(m: ScenarioParamsModel) -> ScenarioParams:
    return ScenarioParams(
        temp_c=m.temp_c,
        c_rate=m.c_rate,
        dod_pct=m.dod_pct,
        horizon_cycles=m.horizon_cycles,
        start_soh_pct=m.start_soh_pct,
        eol_pct=m.eol_pct,
    )


BASELINE = BaselineConditions(
    temp_c=BASELINE_TEMP_C, c_rate=BASELINE_C_RATE, dod_pct=BASELINE_DOD_PCT
)


def simulator_config_response(ba: BatteryAnalysis) -> SimulatorConfigResponse:
    a = ba.analysis
    fade = a.trend.fade_pct_per_cycle
    return SimulatorConfigResponse(
        context=context(ba.battery, a.eol_pct),
        version=SIMULATOR_VERSION,
        defaults=params_model(a.simulator_defaults),
        baseline_conditions=BASELINE,
        base_fade=Quantity(value=fade, unit="%/cycle", provenance="fitted"),
        coefficients=[
            CoefficientOut(name="base_fade", value=fade, provenance="fitted"),
            CoefficientOut(name="temperature", value=TEMP_EXP_PER_C, provenance="assumed"),
            CoefficientOut(name="c_rate", value=C_RATE_LINEAR, provenance="assumed"),
            CoefficientOut(name="dod", value=DOD_EXPONENT, provenance="assumed"),
            CoefficientOut(name="acceleration", value=ACCELERATION_CYCLES, provenance="assumed"),
        ],
        sliders=[
            SliderOut(
                key=LEGACY_KEYS[s.key],
                legacy_key=s.key,
                label=s.label,
                min=s.min,
                max=s.max,
                step=s.step,
                unit=s.unit,
            )
            for s in SLIDERS
        ],
        model=SIMULATOR_MODEL,
    )


def simulate_response(battery: BatteryInfo, result: SimulationResult) -> SimulateResponse:
    c = result.comparison
    trajectories = (
        TrajectoriesOut(
            cycles=result.trajectory_cycles,
            scenario=result.trajectory,
            baseline=result.baseline_trajectory,
        )
        if result.trajectory_cycles is not None
        and result.trajectory is not None
        and result.baseline_trajectory is not None
        else None
    )
    return SimulateResponse(
        context=context(battery, c.params.eol_pct),
        params=params_model(c.params),
        baseline_params=params_model(c.baseline_params),
        rate=Quantity(value=result.rate_pct_per_cycle, unit="%/cycle", provenance="simulated"),
        cycles_to_eol=c.cycles_to_eol,
        baseline_cycles_to_eol=c.baseline_cycles_to_eol,
        delta_cycles=c.delta_cycles,
        delta_pct=c.delta_pct,
        soh_after_horizon=Quantity(value=c.soh_after_horizon_pct, unit="%", provenance="simulated"),
        baseline_soh_after_horizon=Quantity(
            value=c.baseline_soh_after_horizon_pct, unit="%", provenance="simulated"
        ),
        trajectories=trajectories,
        known_issues=["F4"],
    )


def advisor_response(battery: BatteryInfo, table: AdvisorTable) -> AdvisorResponse:
    return AdvisorResponse(
        context=context(battery, table.eol_pct),
        start_soh_pct=table.start_soh_pct,
        eol_pct=table.eol_pct,
        baseline_conditions=BASELINE,
        baseline_cycles_to_eol=table.baseline_cycles_to_eol,
        rows=[
            AdvisorRowOut(
                change=r.change.label,
                why=r.change.why,
                override={LEGACY_KEYS[k]: v for k, v in r.change.override.items()},
                cycles_to_eol=r.cycles_to_eol,
                delta_pct=r.delta_pct,
            )
            for r in table.rows
        ],
        note=ADVISOR_NOTE,
        known_issues=["F8"],
    )
