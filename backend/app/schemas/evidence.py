"""Phase 8: the evidence behind the simulator's assumed stress coefficients and baseline."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel


class Bootstrap(ApiModel):
    replicates: int
    seed: int
    unit: str


class MatchedPair(ApiModel):
    low_temp_cell: str
    high_temp_cell: str
    fade_low: float
    fade_high: float


class TemperatureEvidence(ApiModel):
    dataset: str
    bundle_checksum: str
    pairs: list[MatchedPair]
    fade_unit: str
    temperatures_c: list[float]
    observed_ratio: float
    observed_ratio_ci90: list[float]
    implied_exp_per_c_if_all_temperature: float
    implied_exp_per_c_ci90: list[float]
    use: str = Field(description="How far this evidence may be used (exploratory only).")
    assumed_factor_for_this_delta: float
    assumed_within_ci: bool
    confounder: str
    bootstrap: Bootstrap


class CRateEvidence(ApiModel):
    dataset: str
    bundle_checksum: str
    cells: int
    charge_c_rate_range: list[float]
    model: str
    b_per_c: float
    b_per_c_ci90: list[float]
    r2: float
    life_factor_per_extra_c: float
    life_factor_per_extra_c_ci90: list[float]
    assumed_fade_factor_per_extra_c: float
    applies_to: str
    bootstrap: Bootstrap


class TemperatureCoefficient(ApiModel):
    assumed_exp_per_c: float
    provenance: Literal["assumed"]
    evidence: TemperatureEvidence


class CRateCoefficient(ApiModel):
    assumed_linear: float
    provenance: Literal["assumed"]
    evidence: CRateEvidence


class DodCoefficient(ApiModel):
    """No dataset varies depth of discharge, so there is no evidence to report."""

    provenance: Literal["assumed"]
    note: str


class StressEvidence(ApiModel):
    schema_version: int
    generated_at: str
    status: str
    temperature: TemperatureCoefficient
    c_rate: CRateCoefficient
    dod: DodCoefficient


class ValidationMetrics(ApiModel):
    n: int
    no_estimate: int
    mae_cycles: float | None = None
    median_abs_error_cycles: float | None = None
    bias_cycles: float | None = None
    within_20_pct: float | None = None


class BaselineValidation(ApiModel):
    schema_version: int
    generated_at: str
    dataset: str
    bundle_checksum: str
    eol_pct: float
    eol_label: str
    cells: int
    cells_skipped_short: int
    methods: dict[str, str]
    results: dict[str, dict[str, ValidationMetrics]] = Field(
        description="method -> fraction of life at the prediction point -> metrics"
    )
    note: str


class SimulatorEvidenceResponse(ApiModel):
    stress: StressEvidence
    baseline_validation: BaselineValidation
    note: str
