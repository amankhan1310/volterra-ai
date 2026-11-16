"""Phase 7 experiment: build rows, cross-validate, fit, calibrate, evaluate and write a run.

Tasks (all evaluated on held-out *batteries*):

* ``rul``: remaining useful life (cycles to EOL) from the history up to a prediction point.
  Pooled over every dataset; per-dataset results are reported separately.
* ``forecast_h{H}``: SOH ``H`` cycles ahead (degradation forecasting), pooled.
* ``soh_<dataset>``: SOH *estimation* from measured signals other than capacity, per dataset
  (their sensors differ).
* ``rul_cross_dataset``: trained and calibrated on Severson LFP batteries only, with trajectory
  features, and tested on every usable CALCE battery (LiCoO2: a genuinely different chemistry)
  and NASA battery (chemistry not stated, so only a different dataset). A stress test, not a
  claim of generalisation.

Prediction rows sit on a fixed grid of cycle numbers (every ``grid_step`` cycles), never at
fractions of a battery's life: a row at "20 % of life" would carry the life in its cycle number.
Life fractions (20/40/60/80 %) are used only to *report* test errors, as is customary.

Model choice is made on grouped cross-validation over the training batteries only; the test
batteries are used once, for the reported numbers, by the model fitted on the training batteries.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from volterra_ml.modeling import features as feat
from volterra_ml.modeling.data import Bundle, Cell, FloatArray, load_bundle
from volterra_ml.modeling.evaluation import (
    alpha_lambda_accuracy,
    conformal_quantile,
    fold_of,
    interval_metrics,
    point_metrics,
    split_of,
)
from volterra_ml.modeling.methods import (
    RUL_CAP,
    CohortLifeRul,
    CycleLookup,
    LightGBM,
    LinearTrendForecast,
    LinearTrendRul,
    Model,
    PersistenceForecast,
    RidgeRegression,
)
from volterra_ml.modeling.targets import (
    EOL_PCT,
    centred_median,
    eol_cycle,
    rul,
    starts_below_eol,
    threshold_eol_cycle,
)

RUN_SCHEMA = 1
CROSS_TRAIN = "severson-2019"


@dataclass(frozen=True)
class Config:
    eol_pct: float = EOL_PCT
    grid_step: int = 10
    min_history: int = 10
    soh_stride: int = 5
    horizons: tuple[int, ...] = (50, 100, 200)
    life_fractions: tuple[float, ...] = (0.2, 0.4, 0.6, 0.8)
    interval_level: float = 0.9
    n_folds: int = 5
    seed: int = 7


@dataclass
class Rows:
    """Feature rows of one task: one per (battery, prediction point)."""

    names: tuple[str, ...]
    keys: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    cycles: list[float] = field(default_factory=list)
    feats: list[dict[str, float]] = field(default_factory=list)
    y: list[float] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)  # "grid" or "life_0.2" ...

    def add(self, cell: Cell, pos: int, feats: dict[str, float], y: float, tag: str) -> None:
        self.keys.append(cell.key)
        self.datasets.append(cell.dataset)
        self.cycles.append(float(cell.cycle[pos]))
        self.feats.append(feats)
        self.y.append(y)
        self.tags.append(tag)

    def x(self) -> FloatArray:
        return feat.matrix(self.feats, self.names)

    def subset(self, mask: Sequence[bool]) -> Rows:
        out = Rows(self.names)
        for i, keep in enumerate(mask):
            if keep:
                out.keys.append(self.keys[i])
                out.datasets.append(self.datasets[i])
                out.cycles.append(self.cycles[i])
                out.feats.append(self.feats[i])
                out.y.append(self.y[i])
                out.tags.append(self.tags[i])
        return out

    def __len__(self) -> int:
        return len(self.y)


def usable(cell: Cell, cfg: Config) -> bool:
    return cell.excluded is None and len(cell) > cfg.min_history


def grid_positions(cell: Cell, cfg: Config, end_cycle: float | None = None) -> list[int]:
    """Array positions at cycles ``start + min_history, + grid_step, ...`` (before ``end``)."""
    start = float(cell.cycle[0]) + cfg.min_history
    last = float(cell.cycle[-1]) if end_cycle is None else end_cycle
    out: list[int] = []
    for target in np.arange(start, last + 1e-9, cfg.grid_step):
        pos = int(np.searchsorted(cell.cycle, target))
        fresh = pos < len(cell) and (not out or pos != out[-1]) and pos >= cfg.min_history - 1
        if fresh and (end_cycle is None or cell.cycle[pos] < end_cycle):
            out.append(pos)
    return out


def rul_rows(
    cells: Sequence[Cell], cfg: Config, names: tuple[str, ...], feature_fn: FeatureFn
) -> Rows:
    rows = Rows(names)
    for cell in cells:
        if not usable(cell, cfg) or starts_below_eol(cell, cfg.eol_pct):
            continue
        eol = eol_cycle(cell, cfg.eol_pct)
        if eol is None:
            continue  # censored: the true RUL is unknown
        for pos in grid_positions(cell, cfg, end_cycle=eol):
            rows.add(cell, pos, feature_fn(cell, pos), rul(eol, float(cell.cycle[pos])), "grid")
        start = float(cell.cycle[0])
        for frac in cfg.life_fractions:
            pos = int(np.searchsorted(cell.cycle, start + frac * (eol - start)))
            if cfg.min_history - 1 <= pos < len(cell) and cell.cycle[pos] < eol:
                feats = feature_fn(cell, pos)
                rows.add(cell, pos, feats, rul(eol, float(cell.cycle[pos])), f"life_{frac:.1f}")
    return rows


def forecast_rows(cells: Sequence[Cell], cfg: Config, horizon: int) -> Rows:
    names = tuple(feat.TRAJECTORY_FEATURES + feat.CHANNEL_FEATURES)
    rows = Rows(names)
    for cell in cells:
        if not usable(cell, cfg):
            continue
        smooth = centred_median(cell.soh)
        for pos in grid_positions(cell, cfg):
            target_pos = int(np.searchsorted(cell.cycle, cell.cycle[pos] + horizon))
            if target_pos >= len(cell):
                break  # the battery was not observed that far
            rows.add(cell, pos, feat.rul_features(cell, pos), float(smooth[target_pos]), "grid")
    return rows


def soh_rows(cells: Sequence[Cell], cfg: Config) -> Rows:
    rows = Rows(feat.SIGNAL_FEATURES)
    for cell in cells:
        if not usable(cell, cfg):
            continue
        for pos in range(cfg.min_history - 1, len(cell), cfg.soh_stride):
            rows.add(cell, pos, feat.signal_features(cell, pos), float(cell.soh[pos]), "grid")
    return rows


FeatureFn = Callable[[Cell, int], dict[str, float]]


def _weights(keys: Sequence[str]) -> FloatArray:
    """Each battery weighs the same in training, however many rows it contributes."""
    counts: dict[str, int] = {}
    for k in keys:
        counts[k] = counts.get(k, 0) + 1
    return np.array([1.0 / counts[k] for k in keys], dtype=np.float64)


def _drop_empty(rows: Rows, fit_mask: FloatArray) -> Rows:
    """Remove feature columns with no finite value in the *training* rows (missing sensors)."""
    x = rows.x()[fit_mask.astype(bool)]
    keep = tuple(n for i, n in enumerate(rows.names) if np.isfinite(x[:, i]).any())
    out = rows.subset([True] * len(rows))
    out.names = keep
    return out


@dataclass(frozen=True)
class Task:
    name: str
    kind: str  # rul | forecast | soh
    rows: Rows
    candidates: Callable[[tuple[str, ...]], list[Model]]
    log_target: bool = False
    horizon: int | None = None


def rul_candidates(cfg: Config) -> Callable[[tuple[str, ...]], list[Model]]:
    def make(names: tuple[str, ...]) -> list[Model]:
        return [
            LinearTrendRul(
                cycle_col=names.index("cycle"),
                soh_col=names.index("soh_now"),
                slope_col=names.index("slope_100"),
                fallback_slope_col=names.index("fade_per_100_overall"),
                eol_pct=cfg.eol_pct,
            ),
            CohortLifeRul(cycle_col=names.index("cycle")),
            RidgeRegression(),
            LightGBM(seed=cfg.seed),
        ]

    return make


def forecast_candidates(cfg: Config, horizon: int) -> Callable[[tuple[str, ...]], list[Model]]:
    def make(names: tuple[str, ...]) -> list[Model]:
        return [
            PersistenceForecast(soh_col=names.index("soh_now")),
            LinearTrendForecast(
                soh_col=names.index("soh_now"),
                slope_col=names.index("slope_100"),
                fallback_slope_col=names.index("fade_per_100_overall"),
                horizon=float(horizon),
            ),
            RidgeRegression(),
            LightGBM(seed=cfg.seed),
        ]

    return make


def soh_candidates(cfg: Config) -> Callable[[tuple[str, ...]], list[Model]]:
    def make(names: tuple[str, ...]) -> list[Model]:
        return [CycleLookup(cycle_col=names.index("cycle")), RidgeRegression(), LightGBM(cfg.seed)]

    return make


def _to_original(pred: FloatArray, log_target: bool) -> FloatArray:
    return np.clip(np.expm1(pred), 0.0, RUL_CAP) if log_target else pred


def _target(y: FloatArray, log_target: bool) -> FloatArray:
    return np.log1p(y) if log_target else y


#: Fewest calibration batteries for a dataset-specific (Mondrian) interval; otherwise pooled.
MIN_CALIBRATION_BATTERIES = 3


@dataclass
class Fitted:
    """A fitted model with split-conformal half-widths per dataset (pooled as the fallback)."""

    model: Model
    q_pooled: float
    q_by_dataset: dict[str, float]
    log_target: bool

    def half_widths(self, datasets: Sequence[str]) -> FloatArray:
        return np.array([self.q_by_dataset.get(d, self.q_pooled) for d in datasets])

    def predict(
        self, x: FloatArray, datasets: Sequence[str]
    ) -> tuple[FloatArray, FloatArray, FloatArray]:
        raw = self.model.predict(x)
        q = self.half_widths(datasets)
        point = _to_original(raw, self.log_target)
        lower = _to_original(raw - q, self.log_target)
        upper = _to_original(raw + q, self.log_target)
        return point, lower, upper


def calibrate(
    model: Model,
    x: FloatArray,
    yt: FloatArray,
    datasets: FloatArray | Any,
    keys: Sequence[str],
    calib: FloatArray,
    level: float,
    log_target: bool,
) -> Fitted:
    residual = np.full(len(yt), np.nan)
    residual[calib.astype(bool)] = yt[calib.astype(bool)] - model.predict(x[calib.astype(bool)])
    q_by: dict[str, float] = {}
    for ds in sorted(set(datasets[calib.astype(bool)])):
        m = calib.astype(bool) & (datasets == ds)
        if len({keys[i] for i in np.where(m)[0]}) >= MIN_CALIBRATION_BATTERIES:
            q = conformal_quantile(residual[m], level)
            if np.isfinite(q):
                q_by[str(ds)] = q
    return Fitted(model, conformal_quantile(residual[calib.astype(bool)], level), q_by, log_target)


def _batteries(keys: Sequence[str], mask: Any) -> int:
    return len({keys[i] for i in np.where(mask)[0]})


def run_task(task: Task, cfg: Config, splits: Mapping[str, str]) -> tuple[dict[str, Any], Fitted]:
    split = np.array([splits[k] for k in task.rows.keys])
    grid = np.array([t == "grid" for t in task.rows.tags])
    train = (split == "train") & grid
    rows = _drop_empty(task.rows, train)
    names = rows.names
    x = rows.x()
    y = np.array(rows.y, dtype=np.float64)
    datasets = np.array(rows.datasets)
    calib = (split == "calibration") & grid
    test = split == "test"
    tags = np.array(rows.tags)
    folds = np.array([fold_of(k, cfg.n_folds) for k in rows.keys])
    yt = _target(y, task.log_target)
    results: dict[str, Any] = {}
    fitted: dict[str, Fitted] = {}
    for index, model in enumerate(task.candidates(names)):
        oof = np.full(len(y), np.nan)
        for fold in range(cfg.n_folds):
            fit_mask = train & (folds != fold)
            pred_mask = train & (folds == fold)
            if not pred_mask.any() or not fit_mask.any():
                continue
            fresh = task.candidates(names)[index]
            fresh.fit(
                x[fit_mask], yt[fit_mask], _weights([rows.keys[i] for i in np.where(fit_mask)[0]])
            )
            oof[pred_mask] = _to_original(fresh.predict(x[pred_mask]), task.log_target)
        model.fit(x[train], yt[train], _weights([rows.keys[i] for i in np.where(train)[0]]))
        fit = calibrate(
            model, x, yt, datasets, rows.keys, calib, cfg.interval_level, task.log_target
        )
        fitted[model.name] = fit
        point, lower, upper = fit.predict(x, rows.datasets)
        tg = test & grid
        res: dict[str, Any] = {
            "learned": model.learned,
            "cv": point_metrics(y[train], oof[train]),
            "test": {
                **point_metrics(y[tg], point[tg]),
                **interval_metrics(y[tg], lower[tg], upper[tg]),
            },
            "interval": {
                "scale": "log1p(cycles)" if task.log_target else "SOH percentage points",
                "pooled_half_width": fit.q_pooled,
                "half_width_by_dataset": fit.q_by_dataset,
            },
            "by_dataset": {},
        }
        for ds in sorted(set(rows.datasets)):
            in_ds = datasets == ds
            entry: dict[str, Any] = {
                "interval_basis": "dataset"
                if ds in fit.q_by_dataset
                else "pooled (too few calibration batteries)",
                "cv": {
                    **point_metrics(y[train & in_ds], oof[train & in_ds]),
                    "batteries": _batteries(rows.keys, train & in_ds),
                    "batteries_per_fold": [
                        _batteries(rows.keys, train & in_ds & (folds == f))
                        for f in range(cfg.n_folds)
                    ],
                },
                "calibration": {
                    "rows": int((calib & in_ds).sum()),
                    "batteries": _batteries(rows.keys, calib & in_ds),
                },
                "test": {
                    **point_metrics(y[tg & in_ds], point[tg & in_ds]),
                    **interval_metrics(y[tg & in_ds], lower[tg & in_ds], upper[tg & in_ds]),
                    "batteries": _batteries(rows.keys, tg & in_ds),
                },
            }
            if task.kind == "rul":
                entry["test"]["alpha_lambda_0.2"] = alpha_lambda_accuracy(
                    y[tg & in_ds], point[tg & in_ds]
                )
            res["by_dataset"][ds] = entry
        if task.kind == "rul":
            res["test"]["alpha_lambda_0.2"] = alpha_lambda_accuracy(y[tg], point[tg])
            res["test_by_life_fraction"] = {}
            for frac in cfg.life_fractions:
                m = test & (tags == f"life_{frac:.1f}")
                if m.any():
                    res["test_by_life_fraction"][f"{frac:.1f}"] = {
                        **point_metrics(y[m], point[m]),
                        **interval_metrics(y[m], lower[m], upper[m]),
                        "alpha_lambda_0.2": alpha_lambda_accuracy(y[m], point[m]),
                    }
        results[model.name] = res
    selected = min(results, key=lambda n: results[n]["cv"].get("mae", float("inf")))
    summary = {
        "kind": task.kind,
        "horizon": task.horizon,
        "features": list(names),
        "rows": {
            "train": int(train.sum()),
            "calibration": int(calib.sum()),
            "test": int((test & grid).sum()),
        },
        "batteries": {
            s: _batteries(rows.keys, split == s) for s in ("train", "calibration", "test")
        },
        "batteries_by_dataset": {
            ds: {
                s: _batteries(rows.keys, (split == s) & (datasets == ds))
                for s in ("train", "calibration", "test")
            }
            for ds in sorted(set(rows.datasets))
        },
        "selected": selected,
        "selection_rule": "lowest grouped-CV MAE on the training batteries (test batteries unused)",
        "models": results,
    }
    return summary, fitted[selected]


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def code_hash() -> str:
    """SHA-256 over the modelling source, so a code change always yields a new run id."""
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def _versions() -> dict[str, str]:
    import lightgbm
    import sklearn

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scikit-learn": sklearn.__version__,
        "lightgbm": lightgbm.__version__,
    }


def target_check(bundles: Sequence[Bundle], cfg: Config) -> dict[str, Any]:
    """The threshold rule against the source's own cycle-life labels (Severson et al.)."""
    agree, unlabelled_by_rule, end_soh = [], 0, []
    for b in bundles:
        for cell in b.cells:
            if cell.reported_cycle_life is None or cell.excluded is not None or len(cell) == 0:
                continue
            rule = threshold_eol_cycle(cell, cfg.eol_pct)
            label = eol_cycle(cell, cfg.eol_pct)
            if rule is None:
                unlabelled_by_rule += 1
                end_soh.append(float(cell.soh[-1]))
            elif label is not None:
                agree.append(rule - label)
    d = np.array(agree)
    return {
        "labelled_cells": len(agree) + unlabelled_by_rule,
        "rule_finds_eol": len(agree),
        "rule_minus_label_max_abs_cycles": float(np.abs(d).max()) if d.size else None,
        "rule_misses_eol": unlabelled_by_rule,
        "missed_cells_final_soh_range": [min(end_soh), max(end_soh)] if end_soh else None,
        "note": "cells the rule misses stop at 80.0-80.3 % SOH: the tester ended them at its own "
        "0.88 Ah EOL; the source label is used as their EOL",
    }


def census(bundles: Sequence[Bundle], cfg: Config) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for b in bundles:
        cells = b.cells
        out[b.slug] = {
            "version": b.version,
            "bundle_checksum": b.checksum,
            "batteries": len(cells),
            "excluded": sorted(c.external_id for c in cells if c.excluded),
            "too_short": sorted(
                c.external_id for c in cells if c.excluded is None and len(c) <= cfg.min_history
            ),
            "start_below_eol": sorted(
                c.external_id for c in cells if usable(c, cfg) and starts_below_eol(c, cfg.eol_pct)
            ),
            "censored": sorted(
                c.external_id
                for c in cells
                if usable(c, cfg)
                and not starts_below_eol(c, cfg.eol_pct)
                and eol_cycle(c, cfg.eol_pct) is None
            ),
            "cycles_dropped_not_capacity": b.dropped_cycles,
        }
    return out


def predictions_for(
    cells: Sequence[Cell],
    cfg: Config,
    rul_fit: Fitted,
    rul_names: tuple[str, ...],
    splits: Mapping[str, str],
    model_name: str,
) -> list[dict[str, Any]]:
    """Grid RUL predictions for every battery (including censored ones), labelled by split."""
    out: list[dict[str, Any]] = []
    for cell in cells:
        if not usable(cell, cfg):
            continue
        eol = eol_cycle(cell, cfg.eol_pct)
        positions = grid_positions(cell, cfg)
        if positions and positions[-1] != len(cell) - 1:
            positions.append(len(cell) - 1)
        if not positions:
            continue
        x = feat.matrix([feat.rul_features(cell, p) for p in positions], rul_names)
        point, lower, upper = rul_fit.predict(x, [cell.dataset] * len(positions))
        points = []
        for i, pos in enumerate(positions):
            cycle = float(cell.cycle[pos])
            actual = None if eol is None else rul(eol, cycle)
            points.append(
                {
                    "cycle": cycle,
                    "soh_pct": float(cell.soh[pos]),
                    "rul": float(point[i]),
                    "lower": float(lower[i]),
                    "upper": float(upper[i]),
                    "actual_rul": actual,
                    "past_eol": eol is not None and cycle >= eol,
                }
            )
        basis = "dataset" if cell.dataset in rul_fit.q_by_dataset else "pooled"
        out.append(
            {
                "dataset": cell.dataset,
                "external_id": cell.external_id,
                "split": splits[cell.key],
                "eol_cycle": eol,
                "censored": eol is None,
                "model": model_name,
                "interval_basis": basis,
                "points": points,
            }
        )
    return out


def run(bundle_dirs: Sequence[Path], out_dir: Path, cfg: Config | None = None) -> dict[str, Any]:
    cfg = cfg or Config()
    bundles = [load_bundle(p) for p in bundle_dirs]
    cells = [c for b in bundles for c in b.cells]
    splits = {c.key: split_of(c.key) for c in cells}
    rul_names = tuple(feat.TRAJECTORY_FEATURES + feat.CHANNEL_FEATURES)
    tasks = [
        Task(
            "rul",
            "rul",
            rul_rows(cells, cfg, rul_names, feat.rul_features),
            rul_candidates(cfg),
            log_target=True,
        ),
        *[
            Task(
                f"forecast_h{h}",
                "forecast",
                forecast_rows(cells, cfg, h),
                forecast_candidates(cfg, h),
                horizon=h,
            )
            for h in cfg.horizons
        ],
        *[
            Task(f"soh_{b.slug}", "soh", soh_rows(b.cells, cfg), soh_candidates(cfg))
            for b in bundles
        ],
    ]
    report: dict[str, Any] = {}
    fitted: dict[str, Fitted] = {}
    for task in tasks:
        report[task.name], fitted[task.name] = run_task(task, cfg, splits)

    # Cross-dataset stress test: Severson (LFP) batteries train and calibrate; every usable CALCE
    # (LiCoO2: a different chemistry) and NASA (chemistry not stated) battery is held out for test.
    traj = tuple(feat.TRAJECTORY_FEATURES)
    cross_splits = {
        c.key: ("train" if splits[c.key] != "calibration" else "calibration")
        if c.dataset == CROSS_TRAIN
        else "test"
        for c in cells
    }
    cross = Task(
        "rul_cross_dataset",
        "rul",
        rul_rows(cells, cfg, traj, feat.trajectory_features),
        rul_candidates(cfg),
        log_target=True,
    )
    if any(c.dataset == CROSS_TRAIN for c in cells) and any(
        c.dataset != CROSS_TRAIN for c in cells
    ):
        report[cross.name], _ = run_task(cross, cfg, cross_splits)

    out_dir.mkdir(parents=True, exist_ok=True)
    models_dir = out_dir / "models"
    models_dir.mkdir(exist_ok=True)
    artifacts = {}
    for name, fit in fitted.items():
        path = models_dir / f"{name}.joblib"
        joblib.dump(fit, path)
        artifacts[name] = {
            "path": f"models/{path.name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    rul_used = report["rul"]["features"]
    predictions = predictions_for(
        cells, cfg, fitted["rul"], tuple(rul_used), splits, report["rul"]["selected"]
    )
    (out_dir / "predictions.json").write_text(
        json.dumps(predictions, allow_nan=False, separators=(",", ":")), encoding="utf-8"
    )

    config_json = json.dumps(asdict(cfg), sort_keys=True)
    data_hash = hashlib.sha256("|".join(sorted(b.checksum for b in bundles)).encode()).hexdigest()
    run_id = hashlib.sha256(f"{config_json}|{data_hash}|{code_hash()}".encode()).hexdigest()[:12]
    meta = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "code_sha256": code_hash(),
        "config": asdict(cfg),
        "data_hash": data_hash,
        "data": census(bundles, cfg),
        "eol_definition": (
            "source-reported cycle life when the source documents one (cycle = life - 1, capped "
            f"at the last record); otherwise the first cycle with SOH <= {cfg.eol_pct}% of rated "
            "capacity whose forward 5-cycle median is also <= the threshold; else censored"
        ),
        "target_check_vs_reported_cycle_life": target_check(bundles, cfg),
        "splits": {
            s: sum(1 for v in splits.values() if v == s) for s in ("train", "calibration", "test")
        },
        "split_rule": "salted SHA-256 of '<dataset>:<battery>' (60/20/20), never by row",
        "libraries": _versions(),
        "artifacts": artifacts,
        "status": "experimental",
    }
    (out_dir / "run.json").write_text(json.dumps(meta, indent=2, allow_nan=False), encoding="utf-8")
    (out_dir / "metrics.json").write_text(
        json.dumps(_clean(report), indent=2, allow_nan=False), encoding="utf-8"
    )
    return {"run": meta, "metrics": report}


def _clean(value: Any) -> Any:
    """JSON has no NaN: undefined metrics become null."""
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    return value
