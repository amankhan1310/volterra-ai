"""The CALCE bundle against the real workbooks (local only; skipped without the data).

Every workbook is re-read independently with python-calamine; every sample value of every
column and every per-cycle capacity is compared with the bundle in $VOLTERRA_DATA_DIR.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections import Counter

import numpy as np
import pyarrow.parquet as pq
import pytest
from python_calamine import CalamineWorkbook

from volterra_ml.acquisition.cli import default_data_dir
from volterra_ml.acquisition.sources import CALCE
from volterra_ml.canonical import bundle as bdl
from volterra_ml.loaders import calce

RAW = default_data_dir() / "raw" / CALCE.slug / CALCE.version
BUNDLE = default_data_dir() / "processed" / CALCE.slug / CALCE.version
pytestmark = [
    pytest.mark.realdata,
    pytest.mark.skipif(
        not (RAW.is_dir() and (BUNDLE / "bundle_manifest.json").is_file()),
        reason="real CALCE data or bundle not found (build it with volterra_ml.loaders)",
    ),
]


def test_bundle_verifies_and_counts():
    body = bdl.verify_bundle(BUNDLE)
    assert body["schema_version"] == 2 and body["loader"]["name"] == "calce"
    bats = pq.read_table(BUNDLE / "batteries.parquet").to_pylist()
    assert sorted(b["external_id"] for b in bats) == [c.name[:-4] for c in CALCE.files]
    books = [w for b in bats for w in json.loads(b["test_conditions_json"])["workbooks_in_order"]]
    assert len(books) == 414
    dups = sorted(w["member"] for w in books if w["duplicate_of"])
    assert dups == ["CS2_35/CS2_35_2_10_11.xlsx", "CS2_38/CS2_38_2_10_11.xlsx"]
    assert {w["member"]: w["sheet"] for w in books}["CX2_34/CX2_34_8_16_10.xlsx"] == "Sheet1"
    assert sum(w["empty_cells"] for w in books) == 1
    flagged = [
        b["external_id"] for b in bats if json.loads(b["test_conditions_json"])["dataset_flags"]
    ]
    assert flagged == ["CX2_33"]
    cycles = pq.read_table(BUNDLE / "cycles.parquet")
    assert cycles.column("temp_mean_c").null_count == cycles.num_rows  # never invented
    assert cycles.column("internal_resistance_ohm").null_count == cycles.num_rows


def test_every_sample_and_capacity_matches_the_workbooks():
    cycles = pq.read_table(BUNDLE / "cycles.parquet").to_pylist()
    by_ref = {
        (r["external_id"], json.loads(r["source_ref_json"])["member"], r["source_cycle_index"]): r
        for r in cycles
    }
    numeric = [n for n in calce.HEADER if n != "Date_Time"]
    sample_col = {"Test_Time(s)": "time_s", "Current(A)": "current_a", "Voltage(V)": "voltage_v",
                  "Cycle_Index": "source_cycle_index", **calce.EXTRA_NUMERIC}  # fmt: skip
    compared: Counter[str] = Counter()
    for f in CALCE.files:
        cell = f.name[:-4]
        samples = pq.read_table(BUNDLE / "samples" / f"{cell}_cycle.parquet")
        members = samples.column("source_member").to_numpy(zero_copy_only=False)
        with zipfile.ZipFile(RAW / f.name) as z:
            for member in sorted(set(members)):
                wb = CalamineWorkbook.from_filelike(io.BytesIO(z.read(member)))
                data = next(
                    rows
                    for name in wb.sheet_names
                    if (rows := wb.get_sheet_by_name(name).to_python(skip_empty_area=False))
                    and rows[0][:17] == list(calce.HEADER)
                )[1:]
                sel = members == member
                for name in numeric:
                    j = calce.HEADER.index(name)
                    src = np.array([np.nan if r[j] == "" else r[j] for r in data], dtype=float)
                    got = (
                        samples.column(sample_col[name])
                        .to_numpy(zero_copy_only=False)[sel]
                        .astype(float)
                    )
                    finite = np.isfinite(src)
                    assert np.array_equal(got[finite].view(np.int64), src[finite].view(np.int64)), (
                        member,
                        name,
                    )
                    assert np.all(np.isnan(got[~finite])), (member, name)  # empty -> null, never 0
                compared["samples"] += len(data)
                # per-cycle capacity: increase of the cumulative counter over each Cycle_Index run
                cyc = np.array([r[5] for r in data], dtype=float)
                qd = np.array([r[9] for r in data], dtype=float)
                cur = np.array([r[6] for r in data], dtype=float)
                starts = np.flatnonzero(np.r_[True, cyc[1:] != cyc[:-1]])
                ends = np.r_[starts[1:], cyc.size]
                prev = None
                for a, b in zip(starts, ends, strict=True):
                    base = qd[a] if prev is None else prev
                    prev = qd[b - 1]
                    row = by_ref.get((cell, member, int(cyc[a])))
                    if not np.any(cur[a:b] < 0):
                        assert row is None
                        continue
                    expected = float(qd[b - 1] - base)
                    assert row is not None, (member, cyc[a])
                    assert row["capacity_ah"] == (expected if expected >= 0 else None), (
                        member,
                        cyc[a],
                    )
                    compared["cycles"] += 1
    assert compared["samples"] > 4_000_000 and compared["cycles"] == len(cycles)
