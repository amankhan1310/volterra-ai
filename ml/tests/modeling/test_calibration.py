"""Phase 8 evidence on generated bundles (made-up values): matched pairs and fast charging."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest

from tests.modeling.conftest import make_cell, write_bundle
from volterra_ml import calibration as cal
from volterra_ml.modeling.data import load_bundle


def _nasa(root: Path) -> Path:
    cells = []
    for i, (low, high) in enumerate(cal.NASA_PAIRS):
        cells.append(make_cell(life=400, observed=30, seed=i, dataset="nasa", eid=low))
        cells.append(make_cell(life=130, observed=40, seed=10 + i, dataset="nasa", eid=high))
    return write_bundle(root, "nasa-pcoe-battery", cells)


def _severson(root: Path) -> Path:
    cells = []
    for i in range(30):
        life = 400 + 40 * i
        c = make_cell(life=life, observed=life, seed=20 + i, dataset="sev", eid=f"b{i}")
        charge = np.full(len(c), 600.0 + 8.0 * i)  # longer charge (lower C) -> longer life
        c = dataclasses.replace(
            c, channels={**c.channels, "charge_time_s": charge}, reported_cycle_life=float(life)
        )
        cells.append(c)
    return write_bundle(root, "severson-2019", cells)


def test_matched_pairs_and_fast_charge(tmp_path: Path) -> None:
    nasa = cal.nasa_matched(load_bundle(_nasa(tmp_path)))
    assert nasa["observed_ratio"] > 1.5  # the high-temperature twins fade faster here
    lo, hi = nasa["observed_ratio_ci90"]
    assert lo <= nasa["observed_ratio"] <= hi
    assert nasa["assumed_factor_for_this_delta"] == pytest.approx(np.exp(0.06 * 19))
    assert "load" in nasa["confounder"] and len(nasa["pairs"]) == 4
    lo_c, hi_c = nasa["implied_exp_per_c_ci90"]
    assert lo_c <= nasa["implied_exp_per_c_if_all_temperature"] <= hi_c
    assert nasa["use"].startswith("exploratory only")

    sev = cal.severson_fast_charge(load_bundle(_severson(tmp_path)))
    assert sev["cells"] == 30 and sev["b_per_c"] < 0  # faster charging, shorter life
    assert sev["b_per_c_ci90"][0] <= sev["b_per_c"] <= sev["b_per_c_ci90"][1]


def test_fade_window_must_exist(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fewer than"):
        cal.fade_per_100(make_cell(life=100, observed=10, seed=1))


def test_cli_writes_evidence_and_keeps_coefficients_assumed(tmp_path: Path, capsys) -> None:
    _nasa(tmp_path)
    sev = tmp_path / "processed" / "severson-2019" / "2019-03-11"
    nasa = tmp_path / "processed" / "nasa-pcoe-battery" / "2022-09-18"
    (tmp_path / "processed" / "severson-2019" / "v1").mkdir(parents=True, exist_ok=True)
    _severson(tmp_path / "sev")
    (tmp_path / "processed" / "nasa-pcoe-battery" / "v1").rename(nasa)
    (tmp_path / "sev" / "processed" / "severson-2019" / "v1").rename(sev)
    out = tmp_path / "evidence.json"
    assert cal.main(["--data-dir", str(tmp_path), "--out", str(out)]) == 0
    body = json.loads(out.read_text(encoding="utf-8"))
    assert {body[k]["provenance"] for k in ("temperature", "c_rate", "dod")} == {"assumed"}
    assert body["status"] == "evidence, not calibration"
    assert "fade ratio" in capsys.readouterr().out
