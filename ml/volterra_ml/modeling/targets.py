"""End-of-life and remaining-useful-life targets.

**EOL label:** when the source documents each cell's cycle life (Severson et al.: the test ran
until 80 % of nominal capacity by the tester's measure), that label is the EOL: cycle
``reported_life - 1`` (the source counts from 1), capped at the last recorded cycle. Those cells
end at 80.0-80.3 % SOH by the per-cycle capacity, so a strict threshold would wrongly call them
censored. Otherwise the threshold rule applies.

**Threshold rule:** the first measured cycle whose SOH is at or below the threshold (80 % of the
rated capacity by default, the Severson et al. definition) *and* whose forward window (that cycle
and the next four measured ones, fewer at the end of the record) has a median at or below it
too. A single noisy dip that recovers (NASA capacity regeneration) does not count; a crossing in
the last recorded cycles does. A cell that never reaches it is
**censored**: its RUL is only known to exceed the observed remainder, so it is never used as an
exact target.

**RUL at cycle n:** ``eol_cycle - n`` in cycles; 0 once the cell has reached EOL.
"""

from __future__ import annotations

import numpy as np

from volterra_ml.modeling.data import Cell, FloatArray

EOL_PCT = 80.0
SMOOTHING = 5


def centred_median(values: FloatArray, width: int = SMOOTHING) -> FloatArray:
    half = width // 2
    out = np.empty_like(values)
    for i in range(len(values)):
        out[i] = np.median(values[max(0, i - half) : i + half + 1])
    return out


def eol_cycle(cell: Cell, eol_pct: float = EOL_PCT) -> float | None:
    """Cycle index at which the cell reaches EOL, or None when censored."""
    if len(cell) == 0:
        return None
    if cell.reported_cycle_life is not None and eol_pct == EOL_PCT:
        return float(min(cell.reported_cycle_life - 1.0, cell.cycle[-1]))
    return threshold_eol_cycle(cell, eol_pct)


def threshold_eol_cycle(cell: Cell, eol_pct: float = EOL_PCT) -> float | None:
    """The threshold rule alone (also used to sanity-check source labels)."""
    for i in np.nonzero(cell.soh <= eol_pct)[0]:
        if float(np.median(cell.soh[i : i + SMOOTHING])) <= eol_pct:
            return float(cell.cycle[i])
    return None


def starts_below_eol(cell: Cell, eol_pct: float = EOL_PCT) -> bool:
    """True when the first measurements are already at or below EOL (no usable life left)."""
    head = cell.soh[:SMOOTHING]
    return bool(head.size) and float(np.median(head)) <= eol_pct


def rul(eol: float, cycle: float) -> float:
    return max(0.0, eol - cycle)
