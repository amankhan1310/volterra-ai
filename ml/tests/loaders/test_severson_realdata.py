"""The Severson bundle against the real HDF5 batch files (local only; skipped without the data).

Every cell's per-cycle values are compared with the source summaries read independently with
h5py; every sample of three cells (joined, excluded, regular) is compared bit for bit.
"""

from __future__ import annotations

import json

import h5py
import numpy as np
import pyarrow.parquet as pq
import pytest

from volterra_ml.acquisition.cli import default_data_dir
from volterra_ml.acquisition.sources import SEVERSON
from volterra_ml.canonical import bundle as bdl
from volterra_ml.loaders import severson as sv

RAW = default_data_dir() / "raw" / SEVERSON.slug / SEVERSON.version
BUNDLE = default_data_dir() / "processed" / SEVERSON.slug / SEVERSON.version
pytestmark = [
    pytest.mark.realdata,
    pytest.mark.skipif(
        not (RAW.is_dir() and (BUNDLE / "bundle_manifest.json").is_file()),
        reason="real Severson data or bundle not found (build it with volterra_ml.loaders)",
    ),
]


def entries() -> dict[str, tuple[str, int, h5py.File]]:
    out = {}
    for b, f in enumerate(SEVERSON.files):
        h = h5py.File(RAW / f.name, "r")
        for i in range(h["batch"]["summary"].shape[0]):
            out[f"b{b + 1}c{i}"] = (f.name, i, h)
    return out


def summary(h: h5py.File, i: int, key: str) -> np.ndarray:
    return np.asarray(h[h["batch"]["summary"][i, 0]][key][()], dtype=float).ravel()


def test_bundle_verifies_and_has_135_batteries():
    body = bdl.verify_bundle(BUNDLE)
    assert body["schema_version"] == 2 and body["loader"]["name"] == "severson"
    bats = pq.read_table(BUNDLE / "batteries.parquet").to_pylist()
    assert len(bats) == 135
    flags = {b["external_id"]: json.loads(b["test_conditions_json"])["dataset_flags"] for b in bats}
    assert sorted(k for k, v in flags.items() if "paper_excluded" in v) == sorted(sv.PAPER_EXCLUDED)
    assert sorted(k for k, v in flags.items() if "joined_segments" in v) == sorted(sv.CONTINUATIONS)
    assert not set(sv.CONTINUATIONS.values()) & set(flags)  # continuations are not separate cells


def test_every_cycle_value_matches_the_source_summaries():
    src = entries()
    cycles = pq.read_table(BUNDLE / "cycles.parquet").to_pylist()
    by_cell: dict[str, list[dict]] = {}
    for r in cycles:
        by_cell.setdefault(r["external_id"], []).append(r)
    total = 0
    for cell, rows in by_cell.items():
        names = [cell] + ([sv.CONTINUATIONS[cell]] if cell in sv.CONTINUATIONS else [])
        expected = {
            k: np.concatenate([summary(src[n][2], src[n][1], k) for n in names])
            for k in ("QDischarge", "IR", "Tavg", "Tmin", "Tmax", "chargetime")
        }
        assert len(rows) == expected["QDischarge"].size, cell
        for k, row in enumerate(rows):
            for col, key, scale in (
                ("capacity_ah", "QDischarge", 1.0),
                ("internal_resistance_ohm", "IR", 1.0),
                ("temp_mean_c", "Tavg", 1.0),
                ("temp_min_c", "Tmin", 1.0),
                ("temp_max_c", "Tmax", 1.0),
                ("charge_time_s", "chargetime", 60.0),
            ):
                x = expected[key][k]
                assert row[col] == (x * scale if np.isfinite(x) else None), (cell, k, col)
        total += len(rows)
    all_entries = sum(summary(h, i, "QDischarge").size for _, i, h in src.values())
    assert total == all_entries  # nothing dropped: 140 entries -> 135 batteries, same cycles


@pytest.mark.parametrize("cell", ["b1c0", "b1c8", "b3c45"])
def test_samples_match_the_source_bit_for_bit(cell: str):
    src = entries()
    table = pq.read_table(BUNDLE / "samples" / f"{cell}_cycle.parquet")
    names = [cell] + ([sv.CONTINUATIONS[cell]] if cell in sv.CONTINUATIONS else [])
    got = {
        c: table.column(c).to_numpy(zero_copy_only=False).astype(float)
        for c in ("time_min", "voltage_v", "current_a", "temp_c", "charge_ah", "discharge_ah")
    }
    pos = 0
    for n in names:
        _, i, h = src[n]
        cyc = h[h["batch"]["cycles"][i, 0]]
        for k in range(cyc["V"].shape[0]):
            arrays = {
                key: np.asarray(h[cyc[key][k, 0]][()], dtype=float).ravel()
                for key in ("t", "V", "I", "T", "Qc", "Qd")
            }
            m = max(a.size for a in arrays.values())
            for col, key in (
                ("time_min", "t"),
                ("voltage_v", "V"),
                ("current_a", "I"),
                ("temp_c", "T"),
                ("charge_ah", "Qc"),
                ("discharge_ah", "Qd"),
            ):
                a = arrays[key]
                seg = got[col][pos : pos + a.size]
                fin = np.isfinite(a)
                assert np.array_equal(seg[fin].view(np.int64), a[fin].view(np.int64)), (n, k, col)
            pos += m
    assert pos == table.num_rows
