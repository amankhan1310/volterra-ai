from __future__ import annotations

import dataclasses
from collections import Counter

import numpy as np
import pytest

from tests.modeling.conftest import make_cell
from volterra_ml.modeling.evaluation import (
    alpha_lambda_accuracy,
    conformal_quantile,
    fold_of,
    interval_metrics,
    point_metrics,
    split_of,
)
from volterra_ml.modeling.targets import (
    eol_cycle,
    rul,
    starts_below_eol,
    threshold_eol_cycle,
)


def with_soh(values: list[float], reported: float | None = None):
    cell = make_cell(life=100, observed=len(values), seed=1)
    return dataclasses.replace(
        cell, soh=np.array(values, dtype=np.float64), reported_cycle_life=reported
    )


def test_threshold_rule_ignores_a_dip_that_recovers() -> None:
    cell = with_soh([90, 85, 79, 86, 85, 84, 83, 81, 79.5, 79.4, 79.2, 79.0, 78.8])
    assert threshold_eol_cycle(cell) == 8.0


def test_threshold_rule_counts_a_crossing_in_the_last_records() -> None:
    assert threshold_eol_cycle(with_soh([90, 85, 82, 80.5, 79.9])) == 4.0


def test_censored_cells_have_no_eol() -> None:
    cell = with_soh([95, 94, 93, 92, 91, 90])
    assert eol_cycle(cell) is None and threshold_eol_cycle(cell) is None


def test_source_label_takes_precedence_and_is_capped_at_the_last_record() -> None:
    ends_above = with_soh([95, 90, 85, 82, 80.2, 80.1], reported=7.0)  # tester's own 80 % trigger
    assert threshold_eol_cycle(ends_above) is None
    assert eol_cycle(ends_above) == 5.0  # min(7 - 1, last cycle 5)
    assert eol_cycle(with_soh([95, 90, 85, 82, 79, 78, 77, 76], reported=5.0)) == 4.0


def test_cells_starting_below_eol_are_recognised() -> None:
    assert starts_below_eol(with_soh([70, 69, 68, 67, 66, 65]))
    assert not starts_below_eol(with_soh([95, 94, 93, 92, 91]))


def test_rul_is_never_negative() -> None:
    assert rul(100.0, 40.0) == 60.0 and rul(100.0, 130.0) == 0.0


def test_every_battery_lands_in_exactly_one_split_deterministically() -> None:
    keys = [f"ds{i % 3}:cell{i}" for i in range(3000)]
    first = [split_of(k) for k in keys]
    assert first == [split_of(k) for k in reversed(keys)][::-1]  # order independent
    share = Counter(first)
    assert abs(share["test"] / 3000 - 0.2) < 0.03
    assert abs(share["calibration"] / 3000 - 0.2) < 0.03
    assert {fold_of(k) for k in keys} == {0, 1, 2, 3, 4}


def test_conformal_quantile_uses_the_finite_sample_correction() -> None:
    residuals = np.arange(
        1, 11, dtype=np.float64
    )  # n = 10: ceil(11 * 0.9) / 10 = 1.0 -> the maximum
    assert conformal_quantile(residuals, 0.9) == 10.0
    assert conformal_quantile(-residuals, 0.5) == 6.0  # absolute values; ceil(5.5) / 10
    assert np.isnan(conformal_quantile(np.array([np.nan])))
    assert conformal_quantile(np.array([1.0, 2.0]), 0.9) == float("inf")  # k = 3 > n = 2


def test_metrics() -> None:
    y = np.array([1.0, 2.0, 3.0, np.nan])
    p = np.array([1.0, 2.0, 5.0, 1.0])
    m = point_metrics(y, p)
    assert m["n"] == 3 and m["mae"] == pytest.approx(2 / 3) and m["bias"] == pytest.approx(2 / 3)
    assert point_metrics(np.array([np.nan]), np.array([1.0])) == {"n": 0}
    assert interval_metrics(y, p - 1, p + 1) == {"picp": pytest.approx(2 / 3), "mpiw": 2.0}
    assert alpha_lambda_accuracy(np.array([100.0, 100.0]), np.array([110.0, 150.0])) == 0.5
