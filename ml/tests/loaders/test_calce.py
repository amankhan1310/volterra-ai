"""CALCE loader on generated Arbin-style workbooks (generated values, never real data)."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from tests.loaders.xlsx import xlsx_bytes
from volterra_ml.acquisition import manifest as mf
from volterra_ml.acquisition.fetch import Fetcher
from volterra_ml.acquisition.sources import DatasetSpec, Licence, RemoteFile
from volterra_ml.canonical import bundle as bdl
from volterra_ml.loaders import calce
from volterra_ml.loaders.common import LoaderError

HEADER = list(calce.HEADER)


def arbin_rows(
    start: datetime, cycles: list[tuple[float, float]], *, end_in_discharge: bool = False
) -> list[list[Any]]:
    """Rows for cycles of (charge Ah, discharge Ah): 4 charge, 4 discharge and 1 rest row each.

    Discharge_Capacity accumulates over the workbook, like the Arbin exports.
    """
    rows: list[list[Any]] = [HEADER]
    t, qc, qd, point = 0.0, 0.0, 0.0, 0
    for c, (charge, discharge) in enumerate(cycles, start=1):
        phases = (
            [(0.55, charge / 4, 0.0, 4.0)] * 4
            + [(-1.1, 0.0, discharge / 4, 3.2)] * 4
            + [(0.0, 0.0, 0.0, 3.0)]
        )
        if end_in_discharge and c == len(cycles):
            phases = phases[:6]
        for k, (current, dqc, dqd, volt) in enumerate(phases):
            point += 1
            t += 30.0
            qc += dqc
            qd += dqd
            stamp = start + timedelta(seconds=t)
            rows.append(
                [point, t, stamp, 30.0, 1 + k // 4, c, current, volt - 0.01 * k, qc, qd,
                 qc * 4, qd * 3.7, 1e-4, 0.09 if k else 0.0, 0, 0, 0]
            )  # fmt: skip
    return rows


def workbook(
    start: datetime, cycles: list[tuple[float, float]], *, sheet: str = "Channel_1-008", **kw: Any
) -> bytes:
    info = [["TEST REPORT"], ["generated"]]
    return xlsx_bytes([("Info", info), (sheet, arbin_rows(start, cycles, **kw))])


def cell_zip(cell: str, files: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, data in files.items():
            z.writestr(f"{cell}/{name}", data)
    return out.getvalue()


def spec(cells: list[str]) -> DatasetSpec:
    return DatasetSpec(
        slug="calce-test",
        source="calce",
        name="CALCE-style test archives (generated values, not real data)",
        version="2000-01-01",
        publisher="tests",
        landing_url="https://example.invalid/",
        citation="test citation",
        doi=None,
        licence=Licence("all_rights_reserved", "test", False, "cite"),
        chemistry_stated="LiCoO2 cathode",
        description="generated",
        files=tuple(
            RemoteFile(f"{c}.zip", f"https://example.invalid/{c}.zip", "test cell") for c in cells
        ),
    )


def convert(cell: str, files: dict[str, bytes]) -> tuple[dict[str, Any], list[dict[str, Any]], Any]:
    return calce.convert_cell(cell, cell_zip(cell, files), spec([cell]))


def flags(row: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = json.loads(row["quality_flags_json"])
    return out


T0 = datetime(2010, 9, 2, 14, 0, 0)
T1 = datetime(2010, 10, 4, 14, 0, 0)


def test_workbooks_are_ordered_by_time_not_by_name_and_capacities_use_the_counter():
    # "CS2_35_10_04_10" sorts before "CS2_35_9_7_10" as text, but it is later in time.
    battery, cycles, samples = convert(
        "CS2_35",
        {
            "CS2_35_10_04_10.xlsx": workbook(T1, [(1.0, 0.95)]),
            "CS2_35_9_7_10.xlsx": workbook(T0, [(1.1, 1.08), (1.1, 1.06)]),
        },
    )
    assert [r["capacity_ah"] for r in cycles] == pytest.approx([1.08, 1.06, 0.95])
    assert [r["cycle_index"] for r in cycles] == [0, 1, 2]
    assert [r["source_cycle_index"] for r in cycles] == [1, 2, 1]  # restarts per workbook
    refs = [json.loads(r["source_ref_json"]) for r in cycles]
    assert refs[0] == {
        "cycle_index_in_file": 1,
        "first_row": 2,
        "last_row": 10,
        "member": "CS2_35/CS2_35_9_7_10.xlsx",
        "sheet": "Channel_1-008",
    }
    assert refs[2]["member"] == "CS2_35/CS2_35_10_04_10.xlsx"
    order = [w["member"] for w in json.loads(battery["test_conditions_json"])["workbooks_in_order"]]
    assert order == ["CS2_35/CS2_35_9_7_10.xlsx", "CS2_35/CS2_35_10_04_10.xlsx"]
    first = cycles[0]
    assert first["soh_pct"] == pytest.approx(1.08 / 1.1 * 100)
    assert first["temp_mean_c"] is None and first["ambient_temp_c"] is None  # not measured
    assert first["internal_resistance_ohm"] is None  # held tester reading: kept in samples only
    assert first["charge_time_s"] == 90.0 and first["discharge_time_s"] == 90.0
    assert first["voltage_mean_v"] == pytest.approx(3.2 - 0.01 * 5.5)
    assert first["start_time_local"].startswith("2010-09-02T14:00")
    assert first["db_eligible"] is False  # temperature is required by the database until M5
    assert battery["rated_capacity_ah"] == 1.1 and battery["chemistry_basis"] == "stated_by_source"
    assert (battery["first_capacity_ah"], battery["n_discharge_cycles"]) == (pytest.approx(1.08), 3)


def test_samples_keep_every_source_column_and_row():
    _, _, samples = convert("CS2_35", {"CS2_35_9_7_10.xlsx": workbook(T0, [(1.1, 1.08)])})
    rows = samples.to_pylist()
    src = arbin_rows(T0, [(1.1, 1.08)])[1:]
    assert len(rows) == len(src) == 9
    for row, s in zip(rows, src, strict=True):
        assert row["source_row"] == s[0] + 1 and row["source_sheet"] == "Channel_1-008"
        assert (row["time_s"], row["current_a"], row["voltage_v"]) == (s[1], s[6], s[7])
        assert row["discharge_capacity_ah"] == s[9] and row["internal_resistance_ohm"] == s[13]
        assert row["temp_c"] is None and row["canonical_cycle_index"] == 0
    assert set(calce.sample_schema().names) >= {"date_time_local", "step_index", "dv_dt_v_per_s"}


def test_exact_repeat_is_skipped_and_recorded_but_other_overlaps_stop_the_loader():
    data = workbook(T0, [(1.1, 1.0)])
    battery, cycles, _ = convert(
        "CS2_38", {"CS2_38_2_4_11.xlsx": data, "CS2_38_2_10_11.xlsx": data}
    )
    assert len(cycles) == 1
    books = json.loads(battery["test_conditions_json"])["workbooks_in_order"]
    assert [b["duplicate_of"] for b in books] == [None, "CS2_38/CS2_38_2_4_11.xlsx"]
    used = {s["member"]: s["used"] for s in json.loads(battery["source_files_json"])}
    assert used == {"CS2_38/CS2_38_2_10_11.xlsx": False, "CS2_38/CS2_38_2_4_11.xlsx": True}
    with pytest.raises(LoaderError, match="overlaps .* not an exact repeat"):
        convert(
            "CS2_38",
            {"CS2_38_2_4_11.xlsx": data, "CS2_38_2_10_11.xlsx": workbook(T0, [(1.1, 0.9)])},
        )


def test_sheet_is_chosen_by_header_and_odd_workbooks_fail():
    _, cycles, _ = convert(
        "CX2_34", {"CX2_34_8_16_10.xlsx": workbook(T0, [(1.3, 1.2)], sheet="Sheet1")}
    )
    assert json.loads(cycles[0]["source_ref_json"])["sheet"] == "Sheet1"
    two = xlsx_bytes([("A", arbin_rows(T0, [(1, 1)])), ("B", arbin_rows(T0, [(1, 1)]))])
    with pytest.raises(LoaderError, match="expected one data sheet, found 2"):
        convert("CX2_34", {"CX2_34_8_16_10.xlsx": two})
    with pytest.raises(LoaderError, match="unexpected workbook name"):
        convert("CX2_34", {"CX2_34_august.xlsx": workbook(T0, [(1, 1)])})
    bad = arbin_rows(T0, [(1.1, 1.0)])
    bad[3][7] = "n/a"  # text in a numeric column
    with pytest.raises(LoaderError, match="non-numeric value"):
        convert("CX2_34", {"CX2_34_9_7_10.xlsx": xlsx_bytes([("Channel_1-001", bad)])})
    with pytest.raises(LoaderError, match="no workbooks"):
        convert("CX2_34", {"notes.txt": b"x"})


def test_midnight_timestamps_truncated_discharges_and_cycles_without_discharge():
    rows = arbin_rows(
        datetime(2010, 9, 6, 23, 59, 30), [(1.1, 1.0), (1.1, 0.5)], end_in_discharge=True
    )
    rows.append(
        [999, 1e6, date(2010, 9, 9), 1, 1, 9, 0.5, 4.1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    )  # charge only
    _, cycles, samples = convert(
        "CS2_33", {"CS2_33_9_7_10.xlsx": xlsx_bytes([("Channel_1-006", rows)])}
    )
    assert len(cycles) == 2  # cycle 9 has no discharge: kept in samples, no canonical cycle
    assert "file_ends_during_discharge" not in flags(cycles[1])  # file ends in a charge
    stamps = samples.column("date_time_local").to_pylist()
    assert stamps[-1] == "2010-09-09T00:00:00"  # date-only cell converted, not dropped
    assert samples.column("canonical_cycle_index").to_pylist()[-1] is None
    _, cycles, _ = convert(
        "CS2_33",
        {"CS2_33_9_7_10.xlsx": workbook(T0, [(1.1, 1.0), (1.1, 0.6)], end_in_discharge=True)},
    )
    assert "file_ends_during_discharge" in flags(cycles[1])


def test_text_exports_are_recorded_and_flagged_not_converted():
    battery, _, _ = convert(
        "CX2_33",
        {
            "CX2_33_9_7_10.xlsx": workbook(T0, [(1.3, 1.29)]),
            "cx2_33_6_17_10.txt": b"Time\tmV\n0\t3900\n",
        },
    )
    tc = json.loads(battery["test_conditions_json"])
    assert [u["member"] for u in tc["unconverted_source_files"]] == ["CX2_33/cx2_33_6_17_10.txt"]
    assert "earlier_history_not_converted" in tc["dataset_flags"]
    assert battery["rated_capacity_ah"] == 1.35
    sources = json.loads(battery["source_files_json"])
    assert {s["member"]: s["used"] for s in sources}["CX2_33/cx2_33_6_17_10.txt"] is False


def test_build_bundle_end_to_end(tmp_path: Path):
    cells = ["CS2_35", "CX2_33"]
    s = spec(cells)
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "CS2_35.zip").write_bytes(
        cell_zip("CS2_35", {"CS2_35_9_7_10.xlsx": workbook(T0, [(1.1, 1.08)])})
    )
    (manual / "CX2_33.zip").write_bytes(
        cell_zip("CX2_33", {"CX2_33_9_7_10.xlsx": workbook(T0, [(1.3, 0.0)])})
    )
    raw = tmp_path / "raw"
    directory = mf.dataset_dir(raw, s)
    m = mf.Manifest.for_spec(s)
    for f in s.files:
        rec = Fetcher(progress=None).copy_local(f, manual, directory)
        m.files[rec.name] = rec
    mf.save(directory, m)
    body = calce.build_bundle(raw, tmp_path / "processed", s)
    out = tmp_path / "processed" / s.slug / s.version
    assert bdl.verify_bundle(out)["bundle_checksum"] == body["bundle_checksum"]
    assert {o["path"] for o in body["outputs"]} >= {
        "samples/CS2_35_cycle.parquet",
        "samples/CX2_33_cycle.parquet",
    }
    report = json.loads((out / "quality_report.json").read_text())
    assert report["cells"] == 2 and report["flag_totals"] == {"capacity_zero": 1}
    assert pq.read_table(out / "cycles.parquet").num_rows == 2
    assert body["loader"]["name"] == "calce"
    again = calce.build_bundle(raw, tmp_path / "processed", s)
    assert again["bundle_checksum"] == body["bundle_checksum"]  # deterministic rebuild


def test_empty_numeric_cells_become_null_and_are_flagged():
    rows = arbin_rows(T0, [(1.1, 1.0), (1.1, 0.98)])
    rows[1][1] = ""  # e.g. CS2_33_11_10_10.xlsx: empty Test_Time(s) in the first data row
    battery, cycles, samples = convert(
        "CS2_33", {"CS2_33_11_10_10.xlsx": xlsx_bytes([("Channel_1-006", rows)])}
    )
    assert samples.column("time_s").to_pylist()[0] is None  # missing, never 0
    assert flags(cycles[0])["empty_source_cells"] == "1 empty cell(s) in the source workbook"
    assert "empty_source_cells" not in flags(cycles[1])
    assert cycles[0]["capacity_ah"] == pytest.approx(1.0)
    books = json.loads(battery["test_conditions_json"])["workbooks_in_order"]
    assert books[0]["empty_cells"] == 1
