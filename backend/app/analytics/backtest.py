"""Time-ordered hold-out backtest of the straight-line SOH forecast (v1).

Ported from ``legacy/core.js:65-73``::

    const f = lin(cycles 100..219, soh);
    const e = D.slice(220).map((d) => Math.abs(f.b + f.s * d.i - d.soh));
    return { mae: e.reduce((a, b) => a + b) / e.length };
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from app.analytics.jsmath import reduce_add
from app.analytics.stats import LinearFit, lin
from app.analytics.synthetic import CycleRecord
from app.analytics.types import Provenance

TRAIN_FROM_CYCLE = 100
TEST_FROM_CYCLE = 220


@dataclass(frozen=True)
class BacktestPoint:
    cycle: int
    observed_soh_pct: float
    predicted_soh_pct: float
    abs_error: float


@dataclass(frozen=True)
class BacktestResult:
    train_from_cycle: int
    train_to_cycle: int
    test_from_cycle: int
    test_to_cycle: int
    fit: LinearFit
    points: tuple[BacktestPoint, ...]
    mae: float

    provenance: ClassVar[Provenance] = "fitted"


def run_backtest(
    records: Sequence[CycleRecord],
    train_from: int = TRAIN_FROM_CYCLE,
    test_from: int = TEST_FROM_CYCLE,
) -> BacktestResult:
    """Fit on ``records[train_from:test_from]`` and score on ``records[test_from:]``."""
    if not 0 <= train_from < test_from < len(records):
        raise ValueError("need 0 <= train_from < test_from < number of cycles")
    train = records[train_from:test_from]
    test = records[test_from:]
    fit = lin([r.cycle for r in train], [r.soh_pct for r in train])
    points = tuple(
        BacktestPoint(
            cycle=r.cycle,
            observed_soh_pct=r.soh_pct,
            predicted_soh_pct=fit.predict(r.cycle),
            abs_error=abs(fit.predict(r.cycle) - r.soh_pct),
        )
        for r in test
    )
    return BacktestResult(
        train_from_cycle=train[0].cycle,
        train_to_cycle=train[-1].cycle,
        test_from_cycle=test[0].cycle,
        test_to_cycle=test[-1].cycle,
        fit=fit,
        points=points,
        mae=reduce_add(p.abs_error for p in points) / len(points),
    )
