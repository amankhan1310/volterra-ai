"""Parity: the v1 simulator matches ``simulator.json`` and the advisor matches ``advisor.json``.

Values computed through ``Math.exp`` / ``Math.pow`` (rates, SOH values) may use the documented
1e-12 tolerance; cycle counts and the percentage changes derived from them are exact.
"""

from __future__ import annotations

from app.analytics.advisor import sensitivity_table
from app.analytics.health import DEFAULT_EOL_PCT, recent_trend, rul_at
from app.analytics.simulator import (
    ACCELERATION_CYCLES,
    BASELINE_C_RATE,
    BASELINE_DOD_PCT,
    BASELINE_TEMP_C,
    C_RATE_LINEAR,
    DOD_EXPONENT,
    EOL_SCAN_MAX_CYCLES,
    SLIDERS,
    TEMP_EXP_PER_C,
    ScenarioParams,
    compare_to_baseline,
    cycles_to_eol,
    default_params,
    degradation_rate,
    soh_at,
    trajectory,
)
from app.analytics.synthetic import generate_synthetic_v1
from tests.support.golden import assert_matches

TREND = recent_trend(generate_synthetic_v1())
FADE = TREND.fade_pct_per_cycle
DEFAULT = default_params(TREND.soh_now_pct)


def test_model_constants_defaults_and_sliders_match_golden(golden) -> None:
    fixture = golden("simulator")
    actual = {
        "coefficients": {
            "temp_exp_per_c": TEMP_EXP_PER_C,
            "c_rate_linear": C_RATE_LINEAR,
            "dod_exponent": DOD_EXPONENT,
            "acceleration_cycles": ACCELERATION_CYCLES,
            "eol_scan_max_cycles": EOL_SCAN_MAX_CYCLES,
        },
        "base_fade_pct_per_cycle": FADE,
        "baseline_conditions": {"T": BASELINE_TEMP_C, "C": BASELINE_C_RATE, "D": BASELINE_DOD_PCT},
        "default_params": DEFAULT.to_legacy(),
        "sliders": [vars(s) for s in SLIDERS],
    }
    expected = {
        "coefficients": fixture["model"]["coefficients"],
        **{k: fixture[k] for k in actual if k != "coefficients"},
    }
    assert_matches(actual, expected, label="simulator:model")


def test_f4_consistency_check_is_reproduced(golden) -> None:
    actual = {
        "overview_rul_cycles_at_default_eol": rul_at(TREND, DEFAULT_EOL_PCT),
        "simulator_baseline_cycles_to_eol": cycles_to_eol(DEFAULT.with_baseline_conditions(), FADE),
    }
    assert_matches(actual, golden("simulator")["consistency_check_F4"], label="simulator:F4")


def test_scenarios_match_golden(golden) -> None:
    expected = [
        {k: v for k, v in s.items() if k != "note"} for s in golden("simulator")["scenarios"]
    ]
    actual = []
    for spec in expected:
        p = ScenarioParams.from_legacy(spec["params"])
        cmp = compare_to_baseline(p, FADE)
        actual.append(
            {
                "name": spec["name"],
                "params": p.to_legacy(),
                "rate_pct_per_cycle": degradation_rate(p, FADE),
                "cycles_to_eol": cmp.cycles_to_eol,
                "soh_at": [[n, soh_at(p, n, FADE)] for n, _ in spec["soh_at"]],
                "comparison_vs_baseline": {
                    "baseline_params": cmp.baseline_params.to_legacy(),
                    "baseline_cycles_to_eol": cmp.baseline_cycles_to_eol,
                    "delta_cycles": cmp.delta_cycles,
                    "delta_pct": cmp.delta_pct,
                    "soh_after_n": cmp.soh_after_horizon_pct,
                    "baseline_soh_after_n": cmp.baseline_soh_after_horizon_pct,
                },
            }
        )
    tolerant = [
        ("*", "rate_pct_per_cycle"),
        ("*", "soh_at", "*", 1),
        ("*", "comparison_vs_baseline", "soh_after_n"),
        ("*", "comparison_vs_baseline", "baseline_soh_after_n"),
    ]
    assert_matches(actual, expected, label="simulator:scenarios", tolerant=tolerant)
    assert expected[0]["params"] == DEFAULT.to_legacy()


def test_trajectories_match_golden(golden) -> None:
    expected = golden("simulator")["trajectories"]
    actual = []
    for spec in expected:
        p = ScenarioParams.from_legacy(spec["params"])
        actual.append({"name": spec["name"], "params": p.to_legacy(), "soh": trajectory(p, FADE)})
    assert_matches(actual, expected, label="simulator:trajectories", tolerant=[("*", "soh", "*")])


def advisor_actual(table) -> dict[str, object]:
    return {
        "start_soh_pct": table.start_soh_pct,
        "eol_pct": table.eol_pct,
        "baseline_cycles_to_eol": table.baseline_cycles_to_eol,
        "rows": [
            {
                "change": r.change.label,
                "params_override": r.change.override,
                "cycles_to_eol": r.cycles_to_eol,
                "delta_pct_ui": r.delta_pct,
            }
            for r in table.rows
        ],
    }


def advisor_expected(section: dict) -> dict[str, object]:
    # Bar geometry is presentation (frontend phase); delta_pct_core is F8 evidence only.
    rows = [
        {k: v for k, v in row.items() if k not in {"bar", "delta_pct_core"}}
        for row in section["rows"]
    ]
    return {**{k: v for k, v in section.items() if k != "rows"}, "rows": rows}


def test_advisor_tables_match_golden(golden) -> None:
    fixture = golden("advisor")
    default = sensitivity_table(DEFAULT, FADE)
    edge = sensitivity_table(ScenarioParams.from_legacy({**DEFAULT.to_legacy(), "S": 70}), FADE)
    assert_matches(
        advisor_actual(default), advisor_expected(fixture["default"]), label="advisor:default"
    )
    assert_matches(
        advisor_actual(edge),
        advisor_expected(fixture["edge_start_below_eol"]),
        label="advisor:edge_start_below_eol",
    )


def test_f8_discrepancy_is_preserved_as_evidence(golden) -> None:
    rows = golden("advisor")["edge_start_below_eol"]["rows"]
    assert all(r["delta_pct_ui"] == 0 and r["delta_pct_core"] is None for r in rows)
    default_rows = golden("advisor")["default"]["rows"]
    assert all(r["delta_pct_ui"] == r["delta_pct_core"] for r in default_rows)
