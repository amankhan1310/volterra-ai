"""End to end on generated bundles: separation, censoring, calibration and reproducibility."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tests.modeling.conftest import generated_cells, make_cell
from volterra_ml.modeling import features as feat
from volterra_ml.modeling.__main__ import main
from volterra_ml.modeling.data import load_bundle
from volterra_ml.modeling.evaluation import split_of
from volterra_ml.modeling.experiment import (
    CROSS_TRAIN,
    Config,
    rul_rows,
    run,
)
from volterra_ml.modeling.methods import CohortLifeRul, CycleLookup, LinearTrendRul
from volterra_ml.modeling.targets import eol_cycle


@pytest.fixture(scope="module")
def result(bundles: list[Path], tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    out = tmp_path_factory.mktemp("runs") / "run"
    return out, run(bundles, out)


def test_loader_drops_placeholders_and_reads_labels(bundles: list[Path]) -> None:
    b = load_bundle(bundles[0])
    assert b.slug == "severson-2019" and b.dropped_cycles == len(b.cells)
    assert all(np.max(c.cycle) < 5000 for c in b.cells)


def test_censored_batteries_never_become_rul_targets(bundles: list[Path]) -> None:
    cells = [c for p in bundles for c in load_bundle(p).cells]
    rows = rul_rows(cells, Config(), feat.TRAJECTORY_FEATURES, feat.trajectory_features)
    censored = {c.key for c in cells if eol_cycle(c) is None}
    assert censored and not censored & set(rows.keys)
    eol = {c.key: eol_cycle(c) for c in cells}
    for key, cycle, y in zip(rows.keys, rows.cycles, rows.y, strict=True):
        life = eol[key]
        assert life is not None
        assert y == life - cycle and y > 0  # rows stop before EOL


def test_rows_of_a_battery_share_one_split(result) -> None:
    out, _ = result
    predictions = json.loads((out / "predictions.json").read_text(encoding="utf-8"))
    seen: dict[str, str] = {}
    for p in predictions:
        key = f"{p['dataset']}:{p['external_id']}"
        assert p["split"] == split_of(key)
        assert seen.setdefault(key, p["split"]) == p["split"]


def test_metrics_report_per_dataset_and_never_nan(result) -> None:
    out, res = result
    metrics = json.loads(
        (out / "metrics.json").read_text(encoding="utf-8")
    )  # allow_nan=False wrote it
    rul = metrics["rul"]
    assert set(rul["models"]) == {"linear_trend", "cohort_median", "ridge", "lightgbm"}
    assert rul["selection_rule"].startswith("lowest grouped-CV MAE")
    for model in rul["models"].values():
        for entry in model["by_dataset"].values():
            assert entry["interval_basis"] in ("dataset", "pooled (too few calibration batteries)")
            assert "batteries" in entry["cv"]
    batteries = rul["batteries_by_dataset"]
    assert sum(v["test"] for v in batteries.values()) == rul["batteries"]["test"]
    run_meta = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run_meta["status"] == "experimental"
    assert run_meta["split_rule"].startswith("salted SHA-256")
    for artifact in run_meta["artifacts"].values():
        assert (out / artifact["path"]).is_file() and len(artifact["sha256"]) == 64


def test_cross_dataset_task_tests_only_other_datasets(result) -> None:
    _, res = result
    cross = res["metrics"]["rul_cross_dataset"]
    assert set(cross["batteries_by_dataset"]) >= {CROSS_TRAIN}
    assert cross["batteries_by_dataset"][CROSS_TRAIN]["test"] == 0
    assert all(
        v["train"] == 0 and v["calibration"] == 0
        for name, v in cross["batteries_by_dataset"].items()
        if name != CROSS_TRAIN
    )


def test_predictions_flag_censoring_and_eol(result) -> None:
    out, _ = result
    predictions = json.loads((out / "predictions.json").read_text(encoding="utf-8"))
    assert any(p["censored"] for p in predictions)
    for p in predictions:
        for point in p["points"]:
            assert point["lower"] <= point["rul"] <= point["upper"]
            if p["censored"]:
                assert point["actual_rul"] is None and not point["past_eol"]


def test_a_run_is_reproducible(bundles: list[Path], tmp_path: Path, result) -> None:
    _, first = result
    again = run(bundles, tmp_path / "again")
    assert json.dumps(again["metrics"], sort_keys=True, default=str) == json.dumps(
        first["metrics"], sort_keys=True, default=str
    )
    assert again["run"]["run_id"] == first["run"]["run_id"]


def test_cli(bundles: list[Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", "--out", str(tmp_path / "x")]) == 2
    existing = tmp_path / "exists"
    existing.mkdir()
    assert main(["run", "--bundle", str(bundles[1]), "--out", str(existing)]) == 2
    assert "never overwritten" in capsys.readouterr().err


def test_baselines() -> None:
    names = feat.TRAJECTORY_FEATURES
    x = np.zeros((2, len(names)))
    x[:, names.index("cycle")] = [100.0, 300.0]
    x[:, names.index("soh_now")] = [90.0, 85.0]
    x[:, names.index("slope_100")] = [-2.0, np.nan]
    x[:, names.index("fade_per_100_overall")] = [-1.0, 0.5]
    trend = LinearTrendRul(
        names.index("cycle"),
        names.index("soh_now"),
        names.index("slope_100"),
        names.index("fade_per_100_overall"),
        eol_pct=80.0,
    )
    assert np.expm1(trend.predict(x)) == pytest.approx(
        [500.0, 3000.0]
    )  # 10 pts at 2/100; flat -> cap

    cohort = CohortLifeRul(cycle_col=0)
    lives = np.array(
        [[100.0], [200.0], [150.0], [400.0]]
    )  # cycle column; RUL to lives 300/300/500/800
    cohort.fit(
        lives, np.log1p(np.array([200.0, 100.0, 350.0, 400.0])), np.array([0.5, 0.5, 1.0, 1.0])
    )
    assert cohort.life == pytest.approx(500.0)  # battery-weighted median of 300, 500, 800
    assert np.expm1(cohort.predict(np.array([[450.0], [900.0]]))) == pytest.approx([50.0, 0.0])

    lookup = CycleLookup(cycle_col=0)
    lookup.fit(np.array([[10.0], [20.0], [120.0]]), np.array([99.0, 97.0, 90.0]), np.ones(3))
    assert lookup.predict(np.array([[30.0], [149.0], [990.0]])).tolist() == [98.0, 90.0, 90.0]


def test_generated_cells_have_the_intended_mix() -> None:
    cells = generated_cells("x", 10, 3)
    assert sum(eol_cycle(c) is None for c in cells) == 2
    assert eol_cycle(make_cell(life=200, observed=260, seed=1)) is not None
