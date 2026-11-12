"""Common schema behaviour: NaN/Infinity encoding, exact floats, strictness, immutability."""

from __future__ import annotations

import json
import math
import uuid

import pytest
from fastapi import APIRouter
from pydantic import ValidationError

from app.main import create_app
from app.schemas.common import (
    AnalysisContext,
    ApiRequestModel,
    Interval,
    Quantity,
    data_provenance,
)
from tests.support.api import client_for, make_settings

EXACT = 0.1 + 0.2  # 0.30000000000000004


def test_non_finite_values_serialize_as_strings() -> None:
    q = Quantity(value=math.nan, unit="%", provenance="simulated")
    assert json.loads(q.model_dump_json())["value"] == "NaN"
    i = Interval(
        point=math.inf,
        lower=-math.inf,
        upper=None,
        level=0.95,
        method="m",
        unit="cycles",
        provenance="predicted",
    )
    assert json.loads(i.model_dump_json()) == {
        "point": "Infinity",
        "lower": "-Infinity",
        "upper": None,
        "level": 0.95,
        "method": "m",
        "unit": "cycles",
        "provenance": "predicted",
    }


def test_floats_round_trip_exactly() -> None:
    q = Quantity(value=EXACT, unit="", provenance="fitted")
    assert json.loads(q.model_dump_json())["value"] == EXACT


def test_response_models_are_strict_and_immutable() -> None:
    with pytest.raises(ValidationError):
        Quantity(value=1.0, unit="%", provenance="guessed")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Quantity(value=1.0, unit="%", provenance="fitted", extra=1)  # type: ignore[call-arg]
    q = Quantity(value=1.0, unit="%", provenance="fitted")
    with pytest.raises(ValidationError):
        q.value = 2.0


def test_request_models_reject_non_finite_input() -> None:
    class Body(ApiRequestModel):
        x: float

    assert Body(x=1.5).x == 1.5
    for bad in (math.nan, math.inf, "NaN"):
        with pytest.raises(ValidationError):
            Body(x=bad)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Body(x=1.0, y=2.0)  # type: ignore[call-arg]


def test_analysis_context_and_data_provenance() -> None:
    ctx = AnalysisContext(
        battery_id=uuid.uuid4(),
        dataset="synthetic-v1",
        is_synthetic=True,
        data_provenance="simulated",
    )
    assert ctx.algorithm_version == "v1" and ctx.eol_pct is None
    assert data_provenance(True) == "simulated" and data_provenance(False) == "measured"


@pytest.mark.anyio
async def test_fastapi_responses_keep_the_encoding() -> None:
    app = create_app(make_settings())
    router = APIRouter()

    @router.get("/q", response_model=Quantity)
    async def q() -> Quantity:
        return Quantity(value=math.nan, unit="%", provenance="simulated")

    @router.get("/x", response_model=Quantity)
    async def x() -> Quantity:
        return Quantity(value=EXACT, unit="%", provenance="fitted")

    app.include_router(router)
    async with client_for(app) as client:
        nan_body = (await client.get("/q")).json()
        exact_body = (await client.get("/x")).json()
    assert nan_body["value"] == "NaN"
    assert exact_body["value"] == EXACT
