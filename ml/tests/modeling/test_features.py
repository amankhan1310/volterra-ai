"""Causality: no feature at a prediction point may depend on a later cycle."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from tests.modeling.conftest import make_cell
from volterra_ml.modeling import features as feat
from volterra_ml.modeling.data import Cell


def truncated(cell: Cell, pos: int) -> Cell:
    return dataclasses.replace(
        cell,
        cycle=cell.cycle[: pos + 1].copy(),
        soh=cell.soh[: pos + 1].copy(),
        channels={k: v[: pos + 1].copy() for k, v in cell.channels.items()},
    )


def future_scrambled(cell: Cell, pos: int) -> Cell:
    rng = np.random.default_rng(99)
    soh = cell.soh.copy()
    soh[pos + 1 :] = rng.uniform(0, 200, len(soh) - pos - 1)
    channels = {}
    for k, v in cell.channels.items():
        w = v.copy()
        w[pos + 1 :] = rng.uniform(-1e3, 1e3, len(w) - pos - 1)
        channels[k] = w
    return dataclasses.replace(cell, soh=soh, channels=channels)


FAMILIES = [
    feat.rul_features,
    feat.trajectory_features,
    feat.channel_features,
    feat.signal_features,
]


@pytest.mark.parametrize("fn", FAMILIES, ids=lambda f: f.__name__)
@pytest.mark.parametrize("pos", [0, 1, 4, 9, 10, 57, 120, 298])
def test_features_equal_on_the_truncated_cell(fn, pos: int) -> None:
    cell = make_cell(life=250, observed=300, seed=3)
    full = fn(cell, pos)
    cut = fn(truncated(cell, pos), pos)
    assert full.keys() == cut.keys()
    for k in full:
        assert full[k] == pytest.approx(cut[k], nan_ok=True), k


@pytest.mark.parametrize("fn", FAMILIES, ids=lambda f: f.__name__)
@pytest.mark.parametrize("pos", [5, 50, 200])
def test_scrambling_the_future_changes_nothing(fn, pos: int) -> None:
    cell = make_cell(life=250, observed=300, seed=4)
    assert fn(cell, pos) == pytest.approx(fn(future_scrambled(cell, pos), pos), nan_ok=True)


def test_signal_features_never_contain_capacity() -> None:
    for name in feat.SIGNAL_FEATURES:
        assert not any(w in name for w in ("soh", "capacity", "discharge_time", "current")), name


def test_feature_names_match_the_dictionaries() -> None:
    cell = make_cell(life=200, observed=220, seed=5)
    assert tuple(feat.rul_features(cell, 50)) == feat.TRAJECTORY_FEATURES + feat.CHANNEL_FEATURES
    assert tuple(feat.signal_features(cell, 50)) == feat.SIGNAL_FEATURES


def test_missing_channels_stay_nan() -> None:
    cell = make_cell(life=200, observed=220, seed=6, channels=False)
    f = feat.channel_features(cell, 100)
    assert all(np.isnan(v) for v in f.values())
