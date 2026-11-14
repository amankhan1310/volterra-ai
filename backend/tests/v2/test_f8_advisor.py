"""F8 (v2): the advisor says when a change cannot be compared instead of reporting 0%.

v1 expectations stay in tests/parity and the strict-xfail F8 test.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.analytics.advisor import ADVISOR_CHANGES, sensitivity_table
from app.analytics.advisor_v2 import compare_cycles, sensitivity_table_v2
from app.analytics.forecast_v2 import recent_trend_v2
from app.analytics.legacy_v1 import analyze
from app.analytics.simulator import ScenarioParams
from app.analytics.simulator_v2 import default_params_v2

A = analyze()
TREND = recent_trend_v2(A.records)
DEFAULTS = default_params_v2(TREND)


def test_f8_regression_no_percentage_without_a_baseline() -> None:
    """F8 acceptance (as in test_known_defects.py, for v2): start 70% below EOL 80%."""
    below_eol = ScenarioParams.from_legacy({**DEFAULTS.to_legacy(), "S": 70})
    table = sensitivity_table_v2(below_eol, TREND)
    assert table.baseline_cycles_to_eol == 0
    assert all(row.change_pct is None for row in table.rows)
    assert {row.comparison for row in table.rows} == {"at_or_below_eol"}


def test_default_table_expected_values() -> None:
    table = sensitivity_table_v2(DEFAULTS, TREND)
    assert table.baseline_cycles_to_eol == 97
    assert [r.change.label for r in table.rows] == [c.label for c in ADVISOR_CHANGES]
    # baseline 96.536 cycles / stress factor, rounded: e.g. 0.5C -> /0.8 = 120.7 -> 121
    assert [r.cycles_to_eol for r in table.rows] == [176, 53, 121, 69, 125, 79]
    assert all(r.comparison == "comparable" for r in table.rows)
    assert table.rows[0].change_pct == pytest.approx(81.44329896907216, rel=1e-12)
    assert table.rows[1].change_pct == pytest.approx(-45.36082474226804, rel=1e-12)


def test_rows_beyond_the_horizon_are_marked() -> None:
    slow = dataclasses.replace(TREND, fit=dataclasses.replace(TREND.fit, c1=-0.001, c2=0.0))
    table = sensitivity_table_v2(DEFAULTS, slow)  # baseline ≈ 6000 cycles: beyond 5000
    assert table.baseline_cycles_to_eol is None
    assert all(r.change_pct is None for r in table.rows)
    assert {r.comparison for r in table.rows} == {"beyond_horizon"}
    # Warmer still reaches EOL in range, but cannot be compared with an unknown baseline.
    assert table.rows[1].cycles_to_eol is not None


@pytest.mark.parametrize(
    ("n", "baseline", "expected"),
    [
        (120, 100, (20.0, "comparable")),
        (80, 100, (-20.0, "comparable")),
        (None, 100, (None, "beyond_horizon")),
        (100, None, (None, "beyond_horizon")),
        (0, 0, (None, "at_or_below_eol")),
    ],
)
def test_compare_cycles(n, baseline, expected) -> None:
    assert compare_cycles(n, baseline) == expected


def test_v1_advisor_is_unchanged() -> None:
    below_eol = ScenarioParams.from_legacy({**A.simulator_defaults.to_legacy(), "S": 70})
    v1 = sensitivity_table(below_eol, A.trend.fade_pct_per_cycle)
    assert all(row.delta_pct == 0.0 for row in v1.rows)  # the v1 defect, kept on purpose
