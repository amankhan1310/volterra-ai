"""Causal features: a feature at array position ``pos`` reads only positions ``0..pos``.

``tests/modeling/test_features.py`` enforces this by recomputing every feature on a copy of the
cell truncated after ``pos`` and requiring identical values (no future cycle can leak in).

Two families:

* **Trajectory features** (SOH history up to the prediction point): current SOH, fade so far and
  local fade slopes/curvature. Used to forecast degradation and RUL. They exist for every dataset,
  so they also serve the cross-dataset stress test.
* **Signal features** (per-cycle measurements other than capacity): temperature, voltage,
  internal resistance and charge time. Used to *estimate* SOH without being given capacity.
  Discharge time and current are excluded: at constant current they are capacity in disguise.
"""

from __future__ import annotations

import numpy as np

from volterra_ml.modeling.data import CHANNELS, Cell, FloatArray

TRAJECTORY_FEATURES = (
    "cycle",
    "soh_now",
    "soh_drop",
    "fade_per_100_overall",
    "slope_10",
    "slope_50",
    "slope_100",
    "curvature_100",
)
CHANNEL_FEATURES = tuple(f"{c}_recent" for c in CHANNELS) + (
    "internal_resistance_ohm_delta",
    "charge_time_s_delta",
)
SIGNAL_FEATURES = ("cycle", *CHANNEL_FEATURES)


def _median_finite(values: FloatArray) -> float:
    finite = values[np.isfinite(values)]
    return float(np.median(finite)) if finite.size else float("nan")


def _slope(x: FloatArray, y: FloatArray) -> float:
    """SOH change per 100 cycles from a least-squares line (NaN with fewer than 3 points)."""
    if len(x) < 3 or float(np.ptp(x)) == 0.0:
        return float("nan")
    xc = x - x.mean()
    return float((xc @ (y - y.mean())) / (xc @ xc) * 100.0)


def _curvature(x: FloatArray, y: FloatArray) -> float:
    """Second-order coefficient of a quadratic fit, per (100 cycles)^2 (NaN with < 5 points)."""
    if len(x) < 5 or float(np.ptp(x)) == 0.0:
        return float("nan")
    xs = (x - x.mean()) / 100.0
    return float(np.polyfit(xs, y, 2)[0])


def trajectory_features(cell: Cell, pos: int) -> dict[str, float]:
    x = cell.cycle[: pos + 1]
    y = cell.soh[: pos + 1]
    soh_now = _median_finite(y[-5:])
    soh_start = _median_finite(y[:5])
    span = max(float(x[-1] - x[0]), 1.0)
    return {
        "cycle": float(x[-1]),
        "soh_now": soh_now,
        "soh_drop": soh_start - soh_now,
        "fade_per_100_overall": (soh_start - soh_now) / span * 100.0,
        "slope_10": _slope(x[-10:], y[-10:]),
        "slope_50": _slope(x[-50:], y[-50:]),
        "slope_100": _slope(x[-100:], y[-100:]),
        "curvature_100": _curvature(x[-100:], y[-100:]),
    }


def channel_features(cell: Cell, pos: int, recent: int = 10) -> dict[str, float]:
    out: dict[str, float] = {}
    for name in CHANNELS:
        series = cell.channels[name][: pos + 1]
        out[f"{name}_recent"] = _median_finite(series[-recent:])
    for name in ("internal_resistance_ohm", "charge_time_s"):
        series = cell.channels[name][: pos + 1]
        out[f"{name}_delta"] = _median_finite(series[-recent:]) - _median_finite(series[:recent])
    return out


def signal_features(cell: Cell, pos: int) -> dict[str, float]:
    """Inputs for SOH estimation at ``pos``: measured signals only, never capacity or SOH."""
    return {"cycle": float(cell.cycle[pos]), **channel_features(cell, pos, recent=3)}


def rul_features(cell: Cell, pos: int) -> dict[str, float]:
    return {**trajectory_features(cell, pos), **channel_features(cell, pos)}


def matrix(rows: list[dict[str, float]], names: tuple[str, ...]) -> FloatArray:
    return np.array([[row[n] for n in names] for row in rows], dtype=np.float64).reshape(
        len(rows), len(names)
    )
