"""Model-run import and the models API on PostgreSQL (disposable database, generated data only)."""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from fastapi import FastAPI
from sqlalchemy import func, select

from app.db import import_models as imp
from app.db.import_dataset import import_bundle
from app.db.import_models import ModelImportError, import_run, verify_run
from app.db.models import MlModel, MlPrediction
from app.db.seed import seed_synthetic_v1
from app.db.session import Database
from app.main import create_app
from tests.db.test_real_data_api import calce_bundle, nasa_samples
from tests.support import bundles as b
from tests.support.api import client_for, make_settings
from tests.support.database import assert_disposable, disposable_database, run_isolated
from tests.support.migrations import alembic_config
from tests.support.model_runs import RUN_ID, write_run

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("data")


@pytest.fixture(scope="module")
def database_url(admin_database_url: str, data_dir: Path) -> Iterator[str]:
    with disposable_database(admin_database_url) as url:
        assert_disposable(url)
        run_isolated(lambda: command.upgrade(alembic_config(url), "head"))

        async def load() -> None:
            database = Database(url)
            try:
                async with database.session() as session:
                    await seed_synthetic_v1(session)
                for bundle in (
                    b.write_bundle(data_dir, tamper=nasa_samples),
                    calce_bundle(data_dir),
                ):
                    async with database.session() as session:
                        await import_bundle(session, bundle, data_dir)
            finally:
                await database.dispose()

        run_isolated(lambda: asyncio.run(load()))
        yield url


async def _with_session(url: str, fn: Any) -> Any:
    database = Database(url)
    try:
        async with database.session() as session:
            return await fn(session)
    finally:
        await database.dispose()


async def _counts(url: str) -> tuple[int, int]:
    async def count(session: Any) -> tuple[int, int]:
        models = await session.scalar(select(func.count()).select_from(MlModel))
        preds = await session.scalar(select(func.count()).select_from(MlPrediction))
        return int(models), int(preds)

    return await _with_session(url, count)  # type: ignore[no-any-return]


def _tampered(tmp_path: Path, change: Any) -> Path:
    run_dir = write_run(tmp_path / "run")
    change(run_dir)
    return run_dir


def _edit(name: str, fn: Any) -> Any:
    def apply(run_dir: Path) -> None:
        path = run_dir / name
        data = json.loads(path.read_text(encoding="utf-8"))
        fn(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    return apply


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: (d / "models" / "rul.joblib").write_bytes(b"swapped"), "SHA-256"),
        (_edit("run.json", lambda r: r.update(status="production")), "status"),
        (_edit("run.json", lambda r: r.update(schema=9)), "schema"),
        (_edit("run.json", lambda r: r["artifacts"]["rul"].update(path="../x")), "outside"),
        (_edit("metrics.json", lambda m: m["rul"].update(selected="oracle")), "did not compare"),
        (_edit("metrics.json", lambda m: m["rul"].update(kind="magic")), "unknown kind"),
        (_edit("predictions.json", lambda p: p[0]["points"][0].update(lower=999.0)), "ordered"),
        (_edit("predictions.json", lambda p: p[0]["points"][0].update(rul=float("nan"))), "finite"),
        (_edit("predictions.json", lambda p: p[0].update(split="holdout")), "split"),
        (_edit("predictions.json", lambda p: p[0].update(censored=True)), "censored"),
        (_edit("predictions.json", lambda p: p[0].update(model="ridge")), "not the selected"),
        (lambda d: (d / "metrics.json").unlink(), "missing"),
        (lambda d: (d / "metrics.json").write_text("{", encoding="utf-8"), "valid JSON"),
    ],
)
def test_invalid_runs_are_refused_before_writing(tmp_path: Path, change: Any, message: str) -> None:
    with pytest.raises(ModelImportError, match=message):
        verify_run(_tampered(tmp_path, change))


async def test_import_is_complete_skips_unknown_batteries_and_is_repeatable(
    database_url: str, tmp_path: Path
) -> None:
    refused = _tampered(tmp_path / "bad", _edit("run.json", lambda r: r.update(status="x")))
    with pytest.raises(ModelImportError):
        await _with_session(database_url, lambda s: import_run(s, refused))
    assert await _counts(database_url) == (0, 0)

    run_dir = write_run(tmp_path / "good")
    first = await _with_session(database_url, lambda s: import_run(s, run_dir))
    assert (first.unchanged, first.tasks, first.batteries_with_predictions) == (False, 2, 2)
    assert (first.predictions, first.batteries_not_in_database) == (6, 1)
    again = await _with_session(database_url, lambda s: import_run(s, run_dir))
    assert again.unchanged and await _counts(database_url) == (2, 6)


@pytest.fixture
async def client(
    database_url: str, data_dir: Path, tmp_path: Path
) -> AsyncIterator[httpx.AsyncClient]:
    run_dir = write_run(tmp_path / "run")
    await _with_session(database_url, lambda s: import_run(s, run_dir))
    database = Database(database_url)
    app: FastAPI = create_app(make_settings(data_dir=data_dir), database=database)
    try:
        async with client_for(app) as c:
            yield c
    finally:
        await database.dispose()


async def _ids(client: httpx.AsyncClient) -> dict[str, str]:
    items = (await client.get("/api/v1/batteries")).json()["items"]
    return {i["external_id"]: i["id"] for i in items}


async def test_models_endpoint_serves_the_run_as_reported(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/models")).json()
    assert body["run"]["run_id"] == RUN_ID and body["run"]["status"] == "experimental"
    assert body["run"]["interval_level"] == 0.9 and "Not production-validated" in body["note"]
    rul = next(t for t in body["tasks"] if t["task"] == "rul")
    assert rul["selected_model"] == "lightgbm" and rul["kind"] == "rul"
    lgbm = next(c for c in rul["candidates"] if c["name"] == "lightgbm")
    assert (
        lgbm["selected"] and lgbm["test"]["mae"] == 60.0 and lgbm["test"]["alpha_lambda_20"] == 0.6
    )
    calce = next(d for d in lgbm["datasets"] if d["dataset"] == "calce-test")
    assert calce["interval_basis"] == "dataset" and calce["interval_half_width"] == 0.35
    assert calce["calibration"] == {"rows": 30, "batteries": 3}
    assert calce["cv"]["batteries_per_fold"] == [1, 1, 1, 1, 0]
    nasa = next(d for d in lgbm["datasets"] if d["dataset"] == "nasa-test")
    assert nasa["interval_half_width"] == 0.4  # pooled fallback
    assert [f["fraction"] for f in lgbm["by_life_fraction"]] == ["0.2", "0.8"]
    forecast = next(t for t in body["tasks"] if t["task"] == "forecast_h50")
    assert forecast["horizon_cycles"] == 50


async def test_rul_predictions_carry_provenance_intervals_and_split(
    client: httpx.AsyncClient,
) -> None:
    ids = await _ids(client)
    body = (await client.get(f"/api/v1/batteries/{ids['CS2_T']}/rul-predictions")).json()
    assert body["split"] == "test" and body["in_sample"] is False and body["censored"] is False
    assert body["model"]["model"] == "lightgbm" and body["context"]["note"]
    first = body["points"][0]
    assert first["rul"] == {
        "point": 200.0,
        "lower": 140.0,
        "upper": 280.0,
        "level": 0.9,
        "method": "split_conformal_dataset",
        "unit": "cycles",
        "provenance": "predicted",
    }
    assert first["soh"]["provenance"] == "measured" and first["actual_rul"]["value"] == 140.0
    assert body["points"][-1]["past_eol"] is True

    nasa = (await client.get(f"/api/v1/batteries/{ids['B0005']}/rul-predictions")).json()
    assert nasa["in_sample"] is True and nasa["censored"] is True
    assert all(p["actual_rul"] is None for p in nasa["points"])

    synthetic = await client.get(f"/api/v1/batteries/{ids['SYN-001']}/rul-predictions")
    assert synthetic.status_code == 404
    assert synthetic.json()["error"]["code"] == "predictions_not_found"


def test_the_generated_run_has_no_real_values(tmp_path: Path) -> None:
    run_dir = write_run(tmp_path / "run")
    assert json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["eol_definition"] == (
        "generated test run"
    )
    shutil.rmtree(run_dir)


async def test_cli_imports_refuses_and_needs_a_database(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("app.core.config.get_settings", lambda: make_settings())
    assert await imp._main([str(tmp_path)]) == 2
    assert "DATABASE_URL is not configured" in capsys.readouterr().err
    settings = make_settings(database_url=database_url)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    run_dir = write_run(tmp_path / "cli", run_id="generatedcli")
    assert await imp._main([str(run_dir)]) == 0
    out = capsys.readouterr().out
    assert "run generatedcli: imported; tasks 2, predictions 6 for 2 batteries, 1" in out
    assert "postgresql" not in out and "@" not in out
    assert await imp._main([str(run_dir)]) == 0
    assert "unchanged (already imported)" in capsys.readouterr().out
    (run_dir / "models" / "rul.joblib").write_bytes(b"swapped")
    assert await imp._main([str(run_dir)]) == 1
    assert "import refused, nothing written" in capsys.readouterr().err
