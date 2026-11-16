"""Battery-wise splits, metrics and split-conformal intervals.

**Splits** are by battery, never by row: a battery's whole history lands in exactly one of
``train`` (60 %), ``calibration`` (20 %) or ``test`` (20 %), decided by a salted SHA-256 of its key,
so the assignment is deterministic and independent of row order. Cross-validation inside the
training cells uses grouped folds from the same hash.

**Intervals** are split-conformal: the 90 % quantile (finite-sample corrected) of the calibration
cells' absolute residuals widens every point prediction. Rows of one battery are correlated, so
the textbook coverage guarantee holds only approximately; the empirical coverage (PICP) on the
held-out test batteries is always reported next to the interval width (MPIW).
"""

from __future__ import annotations

import hashlib
import math
from typing import Literal

import numpy as np

from volterra_ml.modeling.data import FloatArray

Split = Literal["train", "calibration", "test"]
SPLIT_SALT = "volterra-phase7-v1"


def _unit(key: str, salt: str) -> float:
    digest = hashlib.sha256(f"{salt}:{key}".encode()).hexdigest()
    return int(digest[:13], 16) / float(16**13)


def split_of(key: str, salt: str = SPLIT_SALT) -> Split:
    u = _unit(key, salt)
    if u < 0.2:
        return "test"
    if u < 0.4:
        return "calibration"
    return "train"


def fold_of(key: str, n_folds: int = 5, salt: str = SPLIT_SALT) -> int:
    return int(_unit(key, salt + ":fold") * n_folds)


def conformal_quantile(residuals: FloatArray, level: float = 0.9) -> float:
    """Split-conformal half-width: the k-th smallest absolute residual, k = ceil((n+1) level).

    Infinite when k > n (too few calibration rows for the requested level); callers then fall
    back to a pooled calibration set.
    """
    finite = np.sort(np.abs(residuals[np.isfinite(residuals)]))
    n = finite.size
    if n == 0:
        return float("nan")
    k = math.ceil((n + 1) * level)
    return float("inf") if k > n else float(finite[k - 1])


def point_metrics(y: FloatArray, pred: FloatArray) -> dict[str, float | int]:
    ok = np.isfinite(y) & np.isfinite(pred)
    y, pred = y[ok], pred[ok]
    n = int(y.size)
    if n == 0:
        return {"n": 0}
    err = pred - y
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        "n": n,
        "mae": float(np.abs(err).mean()),
        "rmse": float(np.sqrt((err**2).mean())),
        "bias": float(err.mean()),
        "r2": float(1.0 - (err**2).sum() / ss_tot) if ss_tot > 0 else float("nan"),
    }


def interval_metrics(y: FloatArray, lower: FloatArray, upper: FloatArray) -> dict[str, float]:
    ok = np.isfinite(y) & np.isfinite(lower) & np.isfinite(upper)
    if not ok.any():
        return {}
    y, lower, upper = y[ok], lower[ok], upper[ok]
    return {
        "picp": float(((y >= lower) & (y <= upper)).mean()),
        "mpiw": float((upper - lower).mean()),
    }


def alpha_lambda_accuracy(y: FloatArray, pred: FloatArray, alpha: float = 0.2) -> float:
    """Share of RUL predictions within +-alpha of the true RUL (prognostics alpha-lambda)."""
    ok = np.isfinite(y) & np.isfinite(pred) & (y > 0)
    if not ok.any():
        return float("nan")
    return float((np.abs(pred[ok] - y[ok]) <= alpha * y[ok]).mean())
