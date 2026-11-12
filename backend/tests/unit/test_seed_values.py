"""Seed value builders and the cycle checksum (no database)."""

from __future__ import annotations

import dataclasses
import math

import pytest

from app.analytics.synthetic import generate_synthetic_v1
from app.db.seed import _main as seed_cli_main
from app.db.seed import (
    cycles_checksum,
    synthetic_battery_values,
    synthetic_dataset_values,
    synthetic_ground_truth,
)
from tests.support.api import make_settings


def test_checksum_is_stable_and_sensitive_to_a_single_ulp() -> None:
    records = generate_synthetic_v1()
    checksum = cycles_checksum(records)
    assert len(checksum) == 64 and checksum == cycles_checksum(generate_synthetic_v1())
    first = records[0]
    nudged = dataclasses.replace(first, temp_c=math.nextafter(first.temp_c, math.inf))
    assert cycles_checksum((nudged, *records[1:])) != checksum


def test_seed_values_describe_synthetic_v1(golden) -> None:
    dataset = synthetic_dataset_values("c" * 64)
    battery = synthetic_battery_values("c" * 64)
    assert (dataset["slug"], dataset["source"], dataset["status"]) == (
        "synthetic-v1",
        "synthetic",
        "ready",
    )
    assert "Simulated" in dataset["description"]
    assert dataset["meta"]["injected_anomalies"] == synthetic_ground_truth()
    assert synthetic_ground_truth() == golden("dataset")["parameters"]["injected_anomalies"]
    assert (battery["external_id"], battery["is_synthetic"], battery["nominal_capacity_ah"]) == (
        "SYN-001",
        True,
        2.0,
    )


@pytest.mark.anyio
async def test_seed_cli_without_database_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("app.core.config.get_settings", lambda: make_settings())
    assert await seed_cli_main() == 1
    assert "DATABASE_URL is not configured" in capsys.readouterr().err
