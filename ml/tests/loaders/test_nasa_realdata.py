"""The NASA loader against the real downloaded archive (local only; skipped in CI).

Every canonical value is compared with the source file, read independently with scipy: the
capacity of every discharge and every per-sample value of every cell, bit for bit.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest
import scipy.io

from volterra_ml.acquisition.cli import default_data_dir
from volterra_ml.acquisition.sources import NASA_PCOE
from volterra_ml.loaders import nasa as loader

RAW = default_data_dir() / "raw" / NASA_PCOE.slug / NASA_PCOE.version / NASA_PCOE.files[0].name
pytestmark = [
    pytest.mark.realdata,
    pytest.mark.skipif(not RAW.is_file(), reason=f"real NASA archive not found ({RAW.name})"),
]


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("processed")
    loader.build_bundle(default_data_dir() / "raw", out, NASA_PCOE)
    return out / NASA_PCOE.slug / NASA_PCOE.version


def source_cells() -> dict[str, object]:
    cells: dict[str, object] = {}
    with zipfile.ZipFile(RAW) as outer:
        for g in outer.infolist():
            if not g.filename.endswith(".zip"):
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(g))) as inner:
                for m in inner.infolist():
                    name = m.filename.rsplit("/", 1)[-1][:-4]
                    if m.filename.endswith(".mat") and name not in cells:
                        mat = scipy.io.loadmat(io.BytesIO(inner.read(m)), struct_as_record=False)
                        cells[name] = mat[name][0, 0].cycle
    return cells


def test_counts_match_the_verified_inspection(bundle: Path):
    batteries = pq.read_table(bundle / "batteries.parquet").to_pylist()
    cycles = pq.read_table(bundle / "cycles.parquet").to_pylist()
    assert len(batteries) == 34
    assert len(cycles) == 2794
    assert sum(r["capacity_ah"] is not None for r in cycles) == 2769
    assert sum(r["db_eligible"] for r in cycles) == 2769
    b5 = next(b for b in batteries if b["external_id"] == "B0005")
    assert b5["n_discharge_cycles"] == 168
    dupes = [b for b in batteries if b["external_id"] in ("B0025", "B0026", "B0027", "B0028")]
    assert all(len(json.loads(b["source_files_json"])) == 2 for b in dupes)
    report = json.loads((bundle / "quality_report.json").read_text())
    assert report["flag_totals"] == {
        "capacity_above_rated": 11,
        "capacity_jump_up": 100,
        "capacity_missing": 25,
        "capacity_zero": 19,
        "voltage_above_4_5v": 3,
        "voltage_below_1_5v": 36,
    }
    assert report["impedance_flag_totals"] == {"rct_complex": 9, "re_complex": 9}


CHANNELS = {  # canonical column -> source field, per operation type
    "discharge": {
        "time_s": "Time",
        "voltage_v": "Voltage_measured",
        "current_a": "Current_measured",
        "temp_c": "Temperature_measured",
        "aux_current_a": "Current_load",
        "aux_voltage_v": "Voltage_load",
    },
    "charge": {
        "time_s": "Time",
        "voltage_v": "Voltage_measured",
        "current_a": "Current_measured",
        "temp_c": "Temperature_measured",
        "aux_current_a": "Current_charge",
        "aux_voltage_v": "Voltage_charge",
    },
}


def test_every_value_matches_the_source_files(bundle: Path):
    cycles = pq.read_table(bundle / "cycles.parquet").to_pylist()
    by_cell: dict[str, list[dict]] = {}
    for r in cycles:
        by_cell.setdefault(r["external_id"], []).append(r)
    compared = {"discharge": 0, "charge": 0}
    nulls_from_non_finite = 0
    for name, cyc in source_cells().items():
        rows = iter(by_cell[name])
        tables = {
            kind: pq.read_table(bundle / "samples" / f"{name}_{kind}.parquet") for kind in CHANNELS
        }
        index = {kind: t.column("source_cycle_index").to_numpy() for kind, t in tables.items()}
        for k in range(cyc.shape[1]):  # type: ignore[attr-defined]
            c = cyc[0, k]  # type: ignore[index]
            kind = str(c.type[0])
            if kind not in CHANNELS:
                continue
            d = c.data[0, 0]
            if kind == "discharge":
                row = next(rows)
                assert row["source_cycle_index"] == k
                cap = np.asarray(d.Capacity).ravel()
                assert row["capacity_ah"] == (float(cap[0]) if cap.size == 1 else None)
            sel = index[kind] == k
            for column, field in CHANNELS[kind].items():
                src = np.asarray(getattr(d, field), dtype=float).ravel()
                got = tables[kind].column(column).to_numpy(zero_copy_only=False)[sel]
                finite = np.isfinite(src)
                # Finite values bit for bit; non-finite source values are null (NaN here), never 0.
                assert np.array_equal(got[finite].view(np.int64), src[finite].view(np.int64)), (
                    name,
                    k,
                    column,
                )
                assert np.all(np.isnan(got[~finite])), (name, k, column)
                nulls_from_non_finite += int((~finite).sum())
                compared[kind] += src.size
        assert next(rows, None) is None
    assert compared["discharge"] > 500_000 and compared["charge"] > 1_000_000
    assert nulls_from_non_finite > 0  # the 25 charge cycles with non-finite source values


def test_processed_bundle_on_disk_matches_a_fresh_build(bundle: Path):
    on_disk = default_data_dir() / "processed" / NASA_PCOE.slug / NASA_PCOE.version
    if not on_disk.is_dir():
        pytest.skip("no processed bundle in VOLTERRA_DATA_DIR")
    fresh = json.loads((bundle / "bundle_manifest.json").read_text())
    disk = json.loads((on_disk / "bundle_manifest.json").read_text())
    if disk["loader"] == fresh["loader"]:  # same library versions: byte-identical bundle
        assert disk == fresh
        return
    # Other numpy/scipy/pyarrow versions write different bytes; the data must still be equal.
    rows = {o["path"]: o["rows"] for o in disk["outputs"]}
    assert rows == {o["path"]: o["rows"] for o in fresh["outputs"]}
    for name in ("batteries.parquet", "cycles.parquet"):
        assert pq.read_table(on_disk / name).equals(pq.read_table(bundle / name)), name
