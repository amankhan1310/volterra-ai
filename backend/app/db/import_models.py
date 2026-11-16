"""Import an offline Phase 7 run (``python -m volterra_ml.modeling run``) into PostgreSQL.

Run against the database in ``DATABASE_URL``::

    uv run python -m app.db.import_models <run-dir>

Guarantees:

* **Verified input.** ``run.json``, ``metrics.json`` and ``predictions.json`` are checked before
  anything is written: the run is ``experimental``, every listed model artifact exists inside the
  run directory with the recorded SHA-256, every task names a known kind and a selected model it
  compared, and every prediction is finite, non-negative and ordered (lower <= point <= upper).
* **All or nothing.** One transaction; any failure leaves the database as it was.
* **Repeatable.** A run is identified by its ``run_id``; re-importing it is a no-op.
* **No data invented.** Predictions are stored only for batteries that already exist in the
  target database (matched by dataset slug and external id); the others are counted and skipped.
  The importer never creates datasets or batteries.

The run's numbers are copied, never recomputed: the API serves them as reported.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ML_INTERVAL_BASES,
    ML_KINDS,
    ML_SPLITS,
    ML_STATUSES,
    Battery,
    Dataset,
    MlModel,
    MlPrediction,
)

RUN_SCHEMA = 1
RUL_TASK = "rul"


class ModelImportError(Exception):
    """The run directory is invalid; nothing was written."""


@dataclass(frozen=True)
class ModelImportResult:
    run_id: str
    unchanged: bool
    tasks: int
    batteries_with_predictions: int
    predictions: int
    batteries_not_in_database: int


def _load(run_dir: Path, name: str) -> Any:
    path = run_dir / name
    if not path.is_file():
        raise ModelImportError(f"{name} missing in {run_dir}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelImportError(f"{name} is not valid JSON: {exc}") from exc


def _number(value: Any, where: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ModelImportError(f"{where}: expected a finite number, got {value!r}")
    return float(value)


def verify_run(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    run = _load(run_dir, "run.json")
    metrics = _load(run_dir, "metrics.json")
    predictions = _load(run_dir, "predictions.json")
    if not isinstance(run, dict) or run.get("schema") != RUN_SCHEMA:
        raise ModelImportError(f"run.json: unsupported schema {run.get('schema')!r}")
    run_id = run.get("run_id")
    if not isinstance(run_id, str) or not 1 <= len(run_id) <= 32:
        raise ModelImportError("run.json: run_id must be a string of 1-32 characters")
    if run.get("status") not in ML_STATUSES:
        raise ModelImportError(f"run.json: status must be one of {ML_STATUSES}")
    try:
        datetime.fromisoformat(str(run.get("created_at")))
    except ValueError as exc:
        raise ModelImportError("run.json: created_at is not an ISO timestamp") from exc
    root = run_dir.resolve()
    artifacts = run.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ModelImportError("run.json: artifacts must be an object")
    for task, artifact in artifacts.items():
        path = (run_dir / str(artifact.get("path", ""))).resolve()
        if root not in path.parents or not path.is_file():
            raise ModelImportError(f"artifact of {task} is missing or outside the run directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact.get("sha256"):
            raise ModelImportError(f"artifact of {task} does not match its SHA-256")
    if not isinstance(metrics, dict) or RUL_TASK not in metrics:
        raise ModelImportError("metrics.json: the rul task is missing")
    for task, summary in metrics.items():
        if not isinstance(summary, dict) or summary.get("kind") not in ML_KINDS:
            raise ModelImportError(f"metrics.json: {task} has an unknown kind")
        if summary.get("selected") not in summary.get("models", {}):
            raise ModelImportError(f"metrics.json: {task} selected a model it did not compare")
        if len(task) > 64:
            raise ModelImportError(f"metrics.json: task name {task[:20]}... is too long")
    if not isinstance(predictions, list):
        raise ModelImportError("predictions.json must be a list")
    selected = metrics[RUL_TASK]["selected"]
    for p in predictions:
        where = f"prediction {p.get('dataset')}:{p.get('external_id')}"
        if p.get("model") != selected:
            raise ModelImportError(f"{where}: made by {p.get('model')!r}, not the selected model")
        if p.get("split") not in ML_SPLITS or p.get("interval_basis") not in ML_INTERVAL_BASES:
            raise ModelImportError(f"{where}: unknown split or interval basis")
        _number(p.get("eol_cycle"), where, optional=True)
        if bool(p.get("censored")) != (p.get("eol_cycle") is None):
            raise ModelImportError(f"{where}: censored must mean 'no EOL cycle'")
        for point in p.get("points", []):
            values = [
                _number(point.get(k), where) for k in ("cycle", "soh_pct", "rul", "lower", "upper")
            ]
            _number(point.get("actual_rul"), where, optional=True)
            _, _, rul, lower, upper = values
            assert rul is not None and lower is not None and upper is not None
            if not 0 <= lower <= rul <= upper:
                raise ModelImportError(f"{where}: interval not ordered or negative")
    return run, metrics, predictions


async def import_run(session: AsyncSession, run_dir: Path) -> ModelImportResult:
    run, metrics, predictions = verify_run(run_dir)
    run_id = str(run["run_id"])
    try:
        existing = (
            await session.scalars(select(MlModel.task).where(MlModel.run_id == run_id))
        ).all()
        if existing:
            await session.rollback()
            return ModelImportResult(run_id, True, len(existing), 0, 0, 0)
        rows = await session.execute(
            select(Battery.id, Dataset.slug, Battery.external_id).join(Dataset)
        )
        battery_ids = {(slug, eid): bid for bid, slug, eid in rows.all()}
        trained_at = datetime.fromisoformat(str(run["created_at"]))
        run_meta = {k: v for k, v in run.items() if k != "artifacts"}
        ids: dict[str, Any] = {}
        for task, summary in metrics.items():
            artifact = run["artifacts"].get(task, {})
            model = MlModel(
                run_id=run_id,
                task=task,
                kind=summary["kind"],
                selected_model=summary["selected"],
                status=run["status"],
                trained_at=trained_at,
                artifact_sha256=artifact.get("sha256"),
                metrics=summary,
                run_meta=run_meta,
            )
            session.add(model)
            await session.flush()
            ids[task] = model.id
        values: list[dict[str, Any]] = []
        matched = skipped = 0
        for p in predictions:
            battery_id = battery_ids.get((p["dataset"], p["external_id"]))
            if battery_id is None:
                skipped += 1
                continue
            matched += 1
            values.extend(_prediction_rows(ids[RUL_TASK], battery_id, p))
        if values:
            await session.execute(insert(MlPrediction), values)
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    return ModelImportResult(run_id, False, len(metrics), matched, len(values), skipped)


def _prediction_rows(model_id: Any, battery_id: Any, p: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "model_id": model_id,
            "battery_id": battery_id,
            "split": p["split"],
            "interval_basis": p["interval_basis"],
            "cycle_index": int(point["cycle"]),
            "soh_pct": point["soh_pct"],
            "rul": point["rul"],
            "lower_rul": point["lower"],
            "upper_rul": point["upper"],
            "actual_rul": point["actual_rul"],
            "past_eol": bool(point["past_eol"]),
            "eol_cycle": p["eol_cycle"],
            "censored": bool(p["censored"]),
        }
        for point in p["points"]
    ]


async def _main(argv: Sequence[str] | None = None) -> int:
    from app.core.config import get_settings
    from app.db.session import Database

    parser = argparse.ArgumentParser(prog="python -m app.db.import_models")
    parser.add_argument("run_dir", type=Path, help="run directory written by volterra_ml.modeling")
    args = parser.parse_args(argv)
    dsn = get_settings().database_dsn()
    if not dsn:
        print("DATABASE_URL is not configured (see backend/.env.example)", file=sys.stderr)
        return 2
    database = Database(dsn)
    try:
        async with database.session() as session:
            result = await import_run(session, args.run_dir)
    except ModelImportError as exc:
        print(f"import refused, nothing written: {exc}", file=sys.stderr)
        return 1
    finally:
        await database.dispose()
    state = "unchanged (already imported)" if result.unchanged else "imported"
    print(
        f"run {result.run_id}: {state}; tasks {result.tasks}, predictions {result.predictions} for "
        f"{result.batteries_with_predictions} batteries, {result.batteries_not_in_database} "
        "batteries not in this database (skipped)"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper
    sys.exit(asyncio.run(_main()))
