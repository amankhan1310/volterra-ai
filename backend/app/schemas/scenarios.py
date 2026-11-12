"""Saved what-if scenarios (no API limit on their number; the UI decides how many to overlay)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import StringConstraints, model_validator

from app.schemas.common import ApiModel, ApiRequestModel
from app.schemas.simulator import ScenarioParamsModel

ScenarioName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class ScenarioCreate(ApiRequestModel):
    name: ScenarioName
    params: ScenarioParamsModel


class ScenarioUpdate(ApiRequestModel):
    name: ScenarioName | None = None
    params: ScenarioParamsModel | None = None

    @model_validator(mode="after")
    def _something_to_update(self) -> ScenarioUpdate:
        if self.name is None and self.params is None:
            raise ValueError("provide name and/or params")
        return self


class ScenarioOut(ApiModel):
    id: uuid.UUID
    battery_id: uuid.UUID
    name: str
    params: ScenarioParamsModel
    simulator_version: str
    created_at: datetime
    updated_at: datetime


class ScenarioList(ApiModel):
    items: list[ScenarioOut]
