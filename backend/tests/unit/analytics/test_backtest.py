"""Unit tests for the v1 backtest."""

from __future__ import annotations

import pytest

from app.analytics.backtest import run_backtest
from app.analytics.synthetic import CycleRecord, generate_synthetic_v1


def test_windows_and_point_count() -> None:
    result = run_backtest(generate_synthetic_v1())
    assert (result.train_from_cycle, result.train_to_cycle) == (100, 219)
    assert (result.test_from_cycle, result.test_to_cycle) == (220, 319)
    assert len(result.points) == 100
    assert result.provenance == "fitted"


def test_perfect_line_has_zero_error() -> None:
    records = tuple(CycleRecord(i, 0.0, 100 - 0.05 * i, 25.0, 3.7) for i in range(40))
    result = run_backtest(records, train_from=0, test_from=30)
    assert result.mae < 1e-12
    assert all(p.abs_error < 1e-12 for p in result.points)


@pytest.mark.parametrize(("train_from", "test_from"), [(-1, 10), (10, 10), (0, 320), (5, 2)])
def test_invalid_windows_raise(train_from: int, test_from: int) -> None:
    with pytest.raises(ValueError):
        run_backtest(generate_synthetic_v1(), train_from=train_from, test_from=test_from)
