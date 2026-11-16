"""Phase 7 model evaluations and stored RUL predictions (values copied from the offline run)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import AnalysisContext, ApiModel, Interval, Quantity

Split = Literal["train", "calibration", "test"]


class MetricSet(ApiModel):
    """Point and interval metrics over rows of held-out (or out-of-fold) batteries."""

    n: int = Field(description="Prediction rows evaluated (0 when none).")
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = Field(default=None, description="Mean of prediction - truth.")
    r2: float | None = None
    picp: float | None = Field(default=None, description="Interval coverage (90 % nominal).")
    mpiw: float | None = Field(default=None, description="Mean interval width.")
    alpha_lambda_20: float | None = Field(
        default=None, description="RUL only: share of predictions within +-20 % of the true RUL."
    )
    batteries: int | None = Field(default=None, description="Batteries behind these rows.")
    batteries_per_fold: list[int] | None = Field(
        default=None, description="CV only: training batteries in each of the grouped folds."
    )


class CalibrationSize(ApiModel):
    rows: int
    batteries: int


class DatasetEvaluation(ApiModel):
    dataset: str
    interval_basis: str = Field(description="'dataset' (Mondrian) or the pooled fallback.")
    interval_half_width: float | None = Field(
        description="Conformal half-width on the interval scale of the task."
    )
    cv: MetricSet = Field(description="Out-of-fold over this dataset's training batteries.")
    test: MetricSet = Field(description="This dataset's held-out test batteries.")
    calibration: CalibrationSize


class LifeFractionMetrics(ApiModel):
    fraction: str = Field(description="Prediction point as a fraction of the battery's life.")
    metrics: MetricSet


class CandidateEvaluation(ApiModel):
    name: str
    learned: bool
    selected: bool
    cv: MetricSet
    test: MetricSet
    interval_scale: str
    pooled_half_width: float | None
    datasets: list[DatasetEvaluation]
    by_life_fraction: list[LifeFractionMetrics] | None = None


class SplitCounts(ApiModel):
    train: int
    calibration: int
    test: int


class ModelTaskOut(ApiModel):
    task: str
    kind: Literal["rul", "forecast", "soh"]
    horizon_cycles: int | None
    status: Literal["experimental"]
    selected_model: str
    selection_rule: str
    features: list[str]
    batteries: SplitCounts
    batteries_by_dataset: dict[str, SplitCounts]
    candidates: list[CandidateEvaluation]
    artifact_sha256: str | None


class DatasetCensus(ApiModel):
    dataset: str
    version: str
    bundle_checksum: str
    batteries: int
    excluded: list[str] = Field(description="Excluded by the source (e.g. Severson paper).")
    too_short: list[str]
    start_below_eol: list[str]
    censored: list[str] = Field(description="Never reach EOL: no exact RUL target.")


class LabelCheck(ApiModel):
    """The threshold EOL rule against the source's documented cycle lives."""

    labelled_cells: int
    rule_finds_eol: int
    rule_misses_eol: int
    rule_minus_label_max_abs_cycles: float | None
    missed_cells_final_soh_range: list[float] | None
    note: str | None


class ModelRunOut(ApiModel):
    run_id: str
    trained_at: datetime
    status: Literal["experimental"]
    git_sha: str | None
    code_sha256: str | None
    data_hash: str
    eol_definition: str
    split_rule: str
    interval_level: float
    eol_pct: float
    libraries: dict[str, str]
    datasets: list[DatasetCensus]
    label_check: LabelCheck


class ModelsResponse(ApiModel):
    run: ModelRunOut | None = Field(description="Null when no model run was imported.")
    tasks: list[ModelTaskOut]
    note: str


class ModelRef(ApiModel):
    run_id: str
    task: str
    model: str
    status: Literal["experimental"]
    trained_at: datetime


class RulPointOut(ApiModel):
    cycle: int
    soh: Quantity = Field(description="Measured SOH at the prediction point.")
    rul: Interval = Field(description="Predicted RUL in cycles with its conformal interval.")
    actual_rul: Quantity | None = Field(
        description="Cycles to the battery's EOL label; null for censored batteries."
    )
    past_eol: bool


class RulPredictionsResponse(ApiModel):
    context: AnalysisContext
    model: ModelRef
    split: Split
    in_sample: bool = Field(description="True for training batteries: not a held-out result.")
    interval_basis: str
    eol_cycle: float | None
    censored: bool
    note: str
    points: list[RulPointOut]
