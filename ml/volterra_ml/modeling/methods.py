"""Models compared in Phase 7, from per-cell extrapolation baselines to learned regressors.

All share ``fit(X, y, weight)`` / ``predict(X)`` over the feature matrices of ``features.py``;
the per-cell baselines ignore ``fit`` and read the trajectory features of each row.

* ``linear_trend``: straight line through the recent SOH trajectory, extrapolated (the legacy
  prototype's method). Implemented here from the row's slope features, so it uses no other cell.
* ``cycle_lookup``: SOH estimation baseline, the training batteries' median SOH at that cycle.
* ``ridge``: standardised linear regression with median imputation.
* ``lightgbm``: gradient-boosted trees (native missing-value handling), fixed hyper-parameters
  (not tuned on the test batteries), deterministic single-thread training.

RUL models predict ``log1p(RUL)`` (errors scale with the remaining life); SOH models predict SOH.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
from lightgbm import LGBMRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from volterra_ml.modeling.data import FloatArray

#: RUL predictions are capped: no dataset here observes more than ~2,300 cycles of life.
RUL_CAP = 3000.0


class Model(Protocol):
    name: str
    learned: bool

    def fit(self, x: FloatArray, y: FloatArray, weight: FloatArray) -> None: ...
    def predict(self, x: FloatArray) -> FloatArray: ...


def lightgbm_params(seed: int) -> dict[str, Any]:
    return {
        "n_estimators": 400,
        "learning_rate": 0.03,
        "num_leaves": 15,
        "min_child_samples": 20,
        "subsample": 0.8,
        "subsample_freq": 1,
        "colsample_bytree": 0.8,
        "reg_lambda": 1.0,
        "random_state": seed,
        "deterministic": True,
        "force_row_wise": True,
        "n_jobs": 1,
        "verbose": -1,
    }


@dataclass
class LightGBM:
    seed: int
    name: str = "lightgbm"
    learned: bool = True
    objective: str = "regression"
    alpha: float | None = None
    model: LGBMRegressor | None = field(default=None, repr=False)

    def fit(self, x: FloatArray, y: FloatArray, weight: FloatArray) -> None:
        params = lightgbm_params(self.seed)
        params["objective"] = self.objective
        if self.alpha is not None:
            params["alpha"] = self.alpha
        self.model = LGBMRegressor(**params)
        self.model.fit(x, y, sample_weight=weight)

    def predict(self, x: FloatArray) -> FloatArray:
        assert self.model is not None, "fit first"
        return np.asarray(self.model.predict(x), dtype=np.float64)


@dataclass
class RidgeRegression:
    name: str = "ridge"
    learned: bool = True
    alpha: float = 1.0
    model: Pipeline | None = field(default=None, repr=False)

    def fit(self, x: FloatArray, y: FloatArray, weight: FloatArray) -> None:
        self.model = make_pipeline(
            SimpleImputer(strategy="median", keep_empty_features=True),
            StandardScaler(),
            Ridge(alpha=self.alpha),
        )
        self.model.fit(x, y, ridge__sample_weight=weight)

    def predict(self, x: FloatArray) -> FloatArray:
        assert self.model is not None, "fit first"
        return np.asarray(self.model.predict(x), dtype=np.float64)


@dataclass
class LinearTrendRul:
    """RUL from the recent SOH slope; predicts ``log1p(RUL)`` like the learned RUL models."""

    cycle_col: int
    soh_col: int
    slope_col: int
    fallback_slope_col: int
    eol_pct: float
    name: str = "linear_trend"
    learned: bool = False

    def fit(self, x: FloatArray, y: FloatArray, weight: FloatArray) -> None:
        return None

    def predict(self, x: FloatArray) -> FloatArray:
        slope = x[:, self.slope_col].copy()  # SOH change per 100 cycles
        missing = ~np.isfinite(slope)
        slope[missing] = x[missing, self.fallback_slope_col]
        margin = x[:, self.soh_col] - self.eol_pct
        with np.errstate(divide="ignore", invalid="ignore"):
            cycles = np.where(slope < 0, margin / (-slope) * 100.0, RUL_CAP)
        cycles = np.where(np.isfinite(cycles), cycles, RUL_CAP)
        return np.asarray(np.log1p(np.clip(cycles, 0.0, RUL_CAP)), dtype=np.float64)


@dataclass
class LinearTrendForecast:
    """SOH ``horizon`` cycles ahead along the recent straight-line trend."""

    soh_col: int
    slope_col: int
    fallback_slope_col: int
    horizon: float
    name: str = "linear_trend"
    learned: bool = False

    def fit(self, x: FloatArray, y: FloatArray, weight: FloatArray) -> None:
        return None

    def predict(self, x: FloatArray) -> FloatArray:
        slope = x[:, self.slope_col].copy()
        missing = ~np.isfinite(slope)
        slope[missing] = x[missing, self.fallback_slope_col]
        slope = np.where(np.isfinite(slope), slope, 0.0)
        return np.asarray(x[:, self.soh_col] + slope * self.horizon / 100.0, dtype=np.float64)


@dataclass
class PersistenceForecast:
    """SOH stays where it is (the naive bar every forecast must beat)."""

    soh_col: int
    name: str = "persistence"
    learned: bool = False

    def fit(self, x: FloatArray, y: FloatArray, weight: FloatArray) -> None:
        return None

    def predict(self, x: FloatArray) -> FloatArray:
        return np.asarray(x[:, self.soh_col], dtype=np.float64)


@dataclass
class CycleLookup:
    """SOH estimation baseline: the training batteries' median SOH in the same 50-cycle bin."""

    cycle_col: int
    bin_width: float = 50.0
    name: str = "cycle_lookup"
    learned: bool = True
    table: dict[int, float] = field(default_factory=dict, repr=False)

    def fit(self, x: FloatArray, y: FloatArray, weight: FloatArray) -> None:
        bins = (x[:, self.cycle_col] // self.bin_width).astype(int)
        self.table = {int(b): float(np.median(y[bins == b])) for b in np.unique(bins)}

    def predict(self, x: FloatArray) -> FloatArray:
        keys = np.array(sorted(self.table))
        out = np.empty(len(x))
        for i, cycle in enumerate(x[:, self.cycle_col]):
            b = int(cycle // self.bin_width)
            nearest = int(keys[np.argmin(np.abs(keys - b))])
            out[i] = self.table[nearest]
        return out


@dataclass
class CohortLifeRul:
    """Population RUL baseline: the training batteries' median life minus the current cycle.

    Uses no history of the battery itself, only how long similar batteries lasted; a learned model
    must beat it to show that the battery's own trajectory adds information.
    """

    cycle_col: int
    name: str = "cohort_median"
    learned: bool = True
    life: float = float("nan")

    def fit(self, x: FloatArray, y: FloatArray, weight: FloatArray) -> None:
        lives = x[:, self.cycle_col] + np.expm1(y)  # constant per battery: its EOL cycle
        order = np.argsort(lives)
        cumulative = np.cumsum(weight[order])
        self.life = float(lives[order][np.searchsorted(cumulative, cumulative[-1] / 2.0)])

    def predict(self, x: FloatArray) -> FloatArray:
        remaining = np.clip(self.life - x[:, self.cycle_col], 0.0, RUL_CAP)
        return np.asarray(np.log1p(remaining), dtype=np.float64)
