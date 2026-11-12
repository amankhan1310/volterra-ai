"""What-if simulator and Charging Advisor requests/responses (v1).

Parameter limits are taken from the prototype's slider definitions (``simulator.SLIDERS``), so the
API enforces exactly the ranges the UI offers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.analytics.simulator import SLIDERS
from app.schemas.common import AnalysisContext, ApiModel, ApiRequestModel, Provenance, Quantity

_RANGE = {s.key: s for s in SLIDERS}


class ScenarioParamsModel(ApiRequestModel):
    """Scenario controls. Descriptive names; prototype keys in parentheses."""

    temp_c: float = Field(
        description="Temperature in °C (T).", ge=_RANGE["T"].min, le=_RANGE["T"].max
    )
    c_rate: float = Field(
        description="Charge rate in C (C).", ge=_RANGE["C"].min, le=_RANGE["C"].max
    )
    dod_pct: float = Field(
        description="Depth of discharge in % (D).", ge=_RANGE["D"].min, le=_RANGE["D"].max
    )
    horizon_cycles: int = Field(
        description="Cycles to simulate (N).", ge=_RANGE["N"].min, le=_RANGE["N"].max
    )
    start_soh_pct: float = Field(
        description="Initial SOH in % (S).", ge=_RANGE["S"].min, le=_RANGE["S"].max
    )
    eol_pct: float = Field(
        description="End-of-life SOH in % (E).", ge=_RANGE["E"].min, le=_RANGE["E"].max
    )


class BaselineConditions(ApiModel):
    temp_c: float
    c_rate: float
    dod_pct: float


class SliderOut(ApiModel):
    key: str
    legacy_key: str
    label: str
    min: float
    max: float
    step: float
    unit: str


class CoefficientOut(ApiModel):
    name: str
    value: float
    provenance: Provenance


class SimulatorConfigResponse(ApiModel):
    context: AnalysisContext
    version: str
    defaults: ScenarioParamsModel
    baseline_conditions: BaselineConditions
    base_fade: Quantity
    coefficients: list[CoefficientOut]
    sliders: list[SliderOut]
    model: str


class SimulateRequest(ApiRequestModel):
    params: ScenarioParamsModel
    include_trajectories: bool = True


class TrajectoriesOut(ApiModel):
    cycles: list[int]
    scenario: list[float]
    baseline: list[float]
    note: str = "SOH values are unclamped; charts clamp at 0."


class SimulateResponse(ApiModel):
    context: AnalysisContext
    params: ScenarioParamsModel
    baseline_params: ScenarioParamsModel
    rate: Quantity
    cycles_to_eol: int | None = Field(description="null when EOL is not reached within 5000.")
    baseline_cycles_to_eol: int | None
    delta_cycles: int | None
    delta_pct: float | None = Field(description="'NaN' when both cycle counts are 0.")
    soh_after_horizon: Quantity
    baseline_soh_after_horizon: Quantity
    trajectories: TrajectoriesOut | None
    known_issues: list[str]
    provenance: Literal["simulated"] = "simulated"


class AdvisorRowOut(ApiModel):
    change: str
    why: str
    override: dict[str, float]
    cycles_to_eol: int | None
    delta_pct: float = Field(description="v1: 0 when either cycle count is missing or 0 (F8).")


class AdvisorResponse(ApiModel):
    context: AnalysisContext
    start_soh_pct: float
    eol_pct: float
    baseline_conditions: BaselineConditions
    baseline_cycles_to_eol: int | None
    rows: list[AdvisorRowOut]
    note: str
    known_issues: list[str]
    provenance: Literal["simulated"] = "simulated"
