"""The committed OpenAPI document matches the code, and the contract has the agreed shape."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.openapi import OPENAPI_FILE, main, openapi_document, render

EXPECTED_PATHS = {
    "/api/v1/health": {"get"},
    "/api/v1/datasets": {"get"},
    "/api/v1/datasets/{slug}": {"get"},
    "/api/v1/batteries": {"get"},
    "/api/v1/batteries/{battery_id}": {"get"},
    "/api/v1/batteries/{battery_id}/cycles": {"get"},
    "/api/v1/batteries/{battery_id}/summary": {"get"},
    "/api/v1/batteries/{battery_id}/forecast": {"get"},
    "/api/v1/batteries/{battery_id}/backtest": {"get"},
    "/api/v1/batteries/{battery_id}/insights": {"get"},
    "/api/v1/batteries/{battery_id}/anomalies": {"get"},
    "/api/v1/batteries/{battery_id}/twin": {"get"},
    "/api/v1/batteries/{battery_id}/simulator": {"get"},
    "/api/v1/batteries/{battery_id}/simulate": {"post"},
    "/api/v1/batteries/{battery_id}/advisor": {"get"},
    "/api/v1/batteries/{battery_id}/scenarios": {"get", "post"},
    "/api/v1/scenarios/{scenario_id}": {"get", "patch", "delete"},
}


def test_committed_openapi_is_up_to_date() -> None:
    assert (
        OPENAPI_FILE.read_text(encoding="utf-8") == render()
    ), "backend/openapi.json is stale: run `uv run python -m app.openapi`"


def test_paths_and_methods_are_the_agreed_contract() -> None:
    paths = openapi_document()["paths"]
    assert {p: set(ops) for p, ops in paths.items()} == EXPECTED_PATHS


def test_error_envelope_is_documented_for_battery_routes() -> None:
    paths = openapi_document()["paths"]
    for path, ops in paths.items():
        if "{battery_id}" in path or "{scenario_id}" in path:
            for op in ops.values():
                ref = op["responses"]["404"]["content"]["application/json"]["schema"]["$ref"]
                assert ref.endswith("/ErrorResponse"), path


def test_analytical_responses_carry_context_and_provenance() -> None:
    schemas = openapi_document()["components"]["schemas"]
    for name in (
        "SummaryResponse",
        "ForecastResponse",
        "BacktestResponse",
        "InsightsResponse",
        "AnomaliesResponse",
        "TwinResponse",
        "SimulatorConfigResponse",
        "SimulateResponse",
        "AdvisorResponse",
        "CyclesResponse",
    ):
        assert "context" in schemas[name]["properties"], name
    for name in ("Quantity", "Interval"):
        assert "provenance" in schemas[name]["required"], name
    assert "meta" not in schemas["DatasetOut"]["properties"]


def test_cli_write_and_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "openapi.json"
    assert main(["--check"], target) == 1
    assert main([], target) == 0
    assert main(["--check"], target) == 0
    assert target.read_text(encoding="utf-8") == render()
    assert "out of date" in capsys.readouterr().err
