"""Shared API building blocks: provenance-tagged quantities, intervals and analysis context.

Contract notes (stable for the Phase 4 frontend):

* Every analytical value carries ``provenance``: ``measured`` / ``simulated`` (data),
  ``fitted`` (estimated from data), ``predicted`` (extrapolated), ``assumed`` (not from data).
* Non-finite numbers are serialized as the strings ``"NaN"``, ``"Infinity"`` and
  ``"-Infinity"`` (the golden-fixture convention); ``null`` always means "not applicable".
* Floats are serialized in shortest round-trip form, so JSON clients recover the exact doubles.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.analytics.types import Provenance
from app.core.errors import ErrorDetail, ErrorResponse

__all__ = [
    "AnalysisContext",
    "ApiModel",
    "ApiRequestModel",
    "DataProvenance",
    "ErrorDetail",
    "ErrorResponse",
    "Interval",
    "Provenance",
    "Quantity",
    "data_provenance",
]

DataProvenance = Literal["measured", "simulated"]


class ApiModel(BaseModel):
    """Base for response models: immutable, strict keys, NaN/Infinity as strings."""

    model_config = ConfigDict(frozen=True, extra="forbid", ser_json_inf_nan="strings")


class ApiRequestModel(BaseModel):
    """Base for request bodies: strict keys and no NaN/Infinity inputs."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Quantity(ApiModel):
    value: float | None
    unit: str
    provenance: Provenance


class Interval(ApiModel):
    point: float | None
    lower: float | None
    upper: float | None
    level: float = Field(description="Nominal coverage, e.g. 0.95.")
    method: str = Field(description="How the interval was computed (v1: 'slope_se', see F3).")
    unit: str
    provenance: Provenance


class AnalysisContext(ApiModel):
    """Identifies what an analytical response was computed from."""

    battery_id: uuid.UUID
    dataset: str
    is_synthetic: bool
    data_provenance: DataProvenance = Field(
        description="'simulated' for synthetic datasets, 'measured' for real ones."
    )
    algorithm_version: Literal["v1"] = "v1"
    eol_pct: float | None = Field(default=None, description="End-of-life SOH threshold used.")


def data_provenance(is_synthetic: bool) -> DataProvenance:
    return "simulated" if is_synthetic else "measured"
