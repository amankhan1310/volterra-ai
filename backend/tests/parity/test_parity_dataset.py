"""Parity: the synthetic-v1 dataset matches ``dataset.json``.

capacity, SOH and voltage must be bit-exact. Temperature (column 3) uses ``Math.sin`` and is the
only field allowed the documented 1e-12 tolerance.
"""

from __future__ import annotations

from app.analytics.synthetic import SYNTHETIC_V1, generate_synthetic_v1
from tests.support.golden import assert_matches

TEMP_COLUMN = 3  # columns: cycle, capacity_ah, soh_pct, temp_c, voltage_v


def test_dataset_rows_match_golden(golden) -> None:
    expected = golden("dataset")
    assert expected["columns"] == ["cycle", "capacity_ah", "soh_pct", "temp_c", "voltage_v"]
    rows = [
        [r.cycle, r.capacity_ah, r.soh_pct, r.temp_c, r.voltage_v] for r in generate_synthetic_v1()
    ]
    assert_matches(rows, expected["rows"], label="dataset", tolerant=[("*", TEMP_COLUMN)])


def test_dataset_parameters_match_golden(golden) -> None:
    params = golden("dataset")["parameters"]
    injected = params["injected_anomalies"]
    actual = {
        "prng": "mulberry32",
        "seed": SYNTHETIC_V1.seed,
        "n_cycles": SYNTHETIC_V1.n_cycles,
        "nominal_capacity_ah": SYNTHETIC_V1.nominal_capacity_ah,
        "temp_spike": {
            "cycles": list(SYNTHETIC_V1.temp_spike_cycles),
            "delta_c": SYNTHETIC_V1.temp_spike_c,
        },
        "voltage_dip": {
            "cycles": list(SYNTHETIC_V1.voltage_dip_cycles),
            "delta_v": -SYNTHETIC_V1.voltage_dip_v,
        },
    }
    expected = {
        "prng": params["prng"],
        "seed": params["seed"],
        "n_cycles": params["n_cycles"],
        "nominal_capacity_ah": params["nominal_capacity_ah"],
        "temp_spike": injected["temp_spike"],
        "voltage_dip": injected["voltage_dip"],
    }
    assert_matches(actual, expected, label="dataset:parameters")
    assert injected["capacity_step"]["cycles"] == []
