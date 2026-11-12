"""Parity: SOH, fade, RUL, interval, forecast and gauge match ``soh_rul.json``."""

from __future__ import annotations

from app.analytics.health import (
    DEFAULT_EOL_PCT,
    forecast_extent,
    forecast_series,
    life_used_fraction,
    recent_trend,
    rul_at,
    rul_interval_95,
)
from app.analytics.synthetic import generate_synthetic_v1
from tests.support.golden import assert_matches

TREND = recent_trend(generate_synthetic_v1())


def test_current_state_matches_golden(golden) -> None:
    actual = {
        "soh_now_pct": TREND.soh_now_pct,
        "soh_now_provenance": TREND.provenance,
        "observed_last_soh_pct": TREND.observed_last_soh_pct,
        "fade_pct_per_cycle": TREND.fade_pct_per_cycle,
        "fit_cycles": {"from": TREND.fit_from_cycle, "to_inclusive": TREND.fit_to_cycle},
        "default_eol_pct": DEFAULT_EOL_PCT,
        "rul_cycles_at_default_eol": rul_at(TREND, DEFAULT_EOL_PCT),
    }
    assert_matches(actual, golden("soh_rul")["current"], label="soh_rul:current")


def test_rul_by_eol_matches_golden(golden) -> None:
    expected = golden("soh_rul")["rul_by_eol"]
    actual = []
    for row in expected:
        iv = rul_interval_95(TREND, row["eol_pct"])
        actual.append(
            {
                "eol_pct": row["eol_pct"],
                "rul_cycles": rul_at(TREND, row["eol_pct"]),
                "interval_95": {"lower": iv.lower, "upper": iv.upper},
            }
        )
    assert_matches(actual, expected, label="soh_rul:rul_by_eol")


def test_rul_with_explicit_slope_matches_golden(golden) -> None:
    expected = [
        {k: v for k, v in row.items() if k != "note"}
        for row in golden("soh_rul")["rul_with_explicit_slope"]
    ]
    actual = [
        {
            "eol_pct": row["eol_pct"],
            "slope": row["slope"],
            "rul_cycles": rul_at(TREND, row["eol_pct"], row["slope"]),
        }
        for row in expected
    ]
    assert_matches(actual, expected, label="soh_rul:explicit_slope")


def test_forecast_and_gauge_match_golden(golden) -> None:
    fixture = golden("soh_rul")
    extent = forecast_extent(TREND.n_cycles, rul_at(TREND, DEFAULT_EOL_PCT))
    forecast = {
        "extent_cycles": extent,
        "from_cycle": TREND.n_cycles - 1,
        "to_cycle_inclusive": extent - 1,
        "values": forecast_series(TREND, extent),
    }
    expected_forecast = {k: fixture["forecast"][k] for k in forecast}
    assert_matches(forecast, expected_forecast, label="soh_rul:forecast")
    gauge = {"life_used_fraction": life_used_fraction(TREND.soh_now_pct, DEFAULT_EOL_PCT)}
    expected_gauge = {"life_used_fraction": fixture["gauge"]["life_used_fraction"]}
    assert_matches(gauge, expected_gauge, label="soh_rul:gauge")
