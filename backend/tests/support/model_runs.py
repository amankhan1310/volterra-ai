"""A generated Phase 7 run directory in the ``volterra_ml.modeling`` format (made-up values).

Used by the importer and API tests, fixture recording and the CI E2E job: it predicts for the
generated real-style batteries of ``fixture_bundles`` (``nasa-test:B0005``, ``calce-test:CS2_T``)
plus one battery that is absent from every database (it must be skipped, never created).
The numbers are fabricated test values, not results of any model.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

RUN_ID = "generated0001"
ARTIFACT = b"generated test artifact, not a model"


def _metrics_block(mae: float, batteries: int) -> dict[str, Any]:
    return {
        "n": 40,
        "mae": mae,
        "rmse": mae * 1.4,
        "bias": -1.5,
        "r2": 0.71,
        "picp": 0.9,
        "mpiw": mae * 4,
        "alpha_lambda_0.2": 0.6,
        "batteries": batteries,
    }


def _candidate(name: str, learned: bool, mae: float, kind: str) -> dict[str, Any]:
    by_dataset = {
        ds: {
            "interval_basis": basis,
            "cv": {**_metrics_block(mae + 5, 4), "batteries_per_fold": [1, 1, 1, 1, 0]},
            "calibration": {"rows": 30, "batteries": cal},
            "test": _metrics_block(mae, 1),
        }
        for ds, basis, cal in (
            ("calce-test", "dataset", 3),
            ("nasa-test", "pooled (too few calibration batteries)", 1),
        )
    }
    entry: dict[str, Any] = {
        "learned": learned,
        "cv": _metrics_block(mae + 5, 8),
        "test": _metrics_block(mae, 2),
        "interval": {
            "scale": "log1p(cycles)" if kind == "rul" else "SOH percentage points",
            "pooled_half_width": 0.4,
            "half_width_by_dataset": {"calce-test": 0.35},
        },
        "by_dataset": by_dataset,
    }
    if kind == "rul":
        entry["test_by_life_fraction"] = {
            "0.2": _metrics_block(mae * 1.5, 2),
            "0.8": _metrics_block(mae * 0.5, 2),
        }
    return entry


def _task(kind: str, horizon: int | None = None) -> dict[str, Any]:
    names = [("linear_trend", False, 300.0), ("ridge", True, 120.0), ("lightgbm", True, 60.0)]
    return {
        "kind": kind,
        "horizon": horizon,
        "features": ["cycle", "soh_now", "slope_100"],
        "rows": {"train": 80, "calibration": 30, "test": 40},
        "batteries": {"train": 8, "calibration": 4, "test": 2},
        "batteries_by_dataset": {
            "calce-test": {"train": 5, "calibration": 3, "test": 1},
            "nasa-test": {"train": 3, "calibration": 1, "test": 1},
        },
        "selected": "lightgbm",
        "selection_rule": "lowest grouped-CV MAE on the training batteries (test batteries unused)",
        "models": {n: _candidate(n, learned, mae, kind) for n, learned, mae in names},
    }


def _points(eol: float | None, cycles: list[float]) -> list[dict[str, Any]]:
    out = []
    for i, cycle in enumerate(cycles):
        rul = 200.0 - 20.0 * i
        out.append(
            {
                "cycle": cycle,
                "soh_pct": 95.0 - i,
                "rul": rul,
                "lower": rul * 0.7,
                "upper": rul * 1.4,
                "actual_rul": None if eol is None else max(0.0, eol - cycle),
                "past_eol": eol is not None and cycle >= eol,
            }
        )
    return out


def write_run(run_dir: Path, *, run_id: str = RUN_ID, status: str = "experimental") -> Path:
    (run_dir / "models").mkdir(parents=True)
    (run_dir / "models" / "rul.joblib").write_bytes(ARTIFACT)
    sha = hashlib.sha256(ARTIFACT).hexdigest()
    run = {
        "schema": 1,
        "run_id": run_id,
        "created_at": "2026-11-16T20:00:00+00:00",
        "git_sha": "0" * 40,
        "git_dirty": False,
        "code_sha256": "1" * 64,
        "config": {"eol_pct": 80.0, "interval_level": 0.9, "grid_step": 10, "seed": 7},
        "data_hash": "2" * 64,
        "data": {
            slug: {
                "version": "v1",
                "bundle_checksum": "3" * 64,
                "batteries": n,
                "excluded": [],
                "too_short": [],
                "start_below_eol": [],
                "censored": censored,
                "cycles_dropped_not_capacity": 0,
            }
            for slug, n, censored in (("calce-test", 1, []), ("nasa-test", 1, ["B0005"]))
        },
        "eol_definition": "generated test run",
        "target_check_vs_reported_cycle_life": {
            "labelled_cells": 0,
            "rule_finds_eol": 0,
            "rule_misses_eol": 0,
        },
        "splits": {"train": 1, "calibration": 0, "test": 1},
        "split_rule": "salted SHA-256 of '<dataset>:<battery>' (60/20/20), never by row",
        "libraries": {"python": "3.12", "lightgbm": "generated"},
        "artifacts": {"rul": {"path": "models/rul.joblib", "sha256": sha}},
        "status": status,
    }
    metrics = {"rul": _task("rul"), "forecast_h50": _task("forecast", 50)}
    predictions = [
        {
            "dataset": "calce-test",
            "external_id": "CS2_T",
            "split": "test",
            "eol_cycle": 150.0,
            "censored": False,
            "model": "lightgbm",
            "interval_basis": "dataset",
            "points": _points(150.0, [10.0, 50.0, 100.0, 160.0]),
        },
        {
            "dataset": "nasa-test",
            "external_id": "B0005",
            "split": "train",
            "eol_cycle": None,
            "censored": True,
            "model": "lightgbm",
            "interval_basis": "pooled",
            "points": _points(None, [0.0, 2.0]),
        },
        {
            "dataset": "absent-dataset",
            "external_id": "X9",
            "split": "test",
            "eol_cycle": 90.0,
            "censored": False,
            "model": "lightgbm",
            "interval_basis": "pooled",
            "points": _points(90.0, [10.0]),
        },
    ]
    (run_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    (run_dir / "predictions.json").write_text(json.dumps(predictions), encoding="utf-8")
    return run_dir
