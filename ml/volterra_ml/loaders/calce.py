"""CALCE CS2/CX2 loader (Phase 6 M4): 12 cell archives of Arbin workbooks -> canonical bundle.

Structure, as verified on all 414 workbooks (2026-11-15, see docs/datasets/calce-cs2-cx2.md):

* One zip per cell with ``<cell>_M_D_YY.xlsx`` workbooks. The name date is not zero-padded, so
  files are ordered by their **first sample time** (then name), never lexically.
* Each workbook has one data sheet with the 17-column Arbin header (``Channel_1-NNN``, once
  ``Sheet1``); it is chosen by its header, not its name. There is no temperature column.
* ``Cycle_Index`` restarts in every workbook and ``Discharge_Capacity(Ah)`` accumulates over the
  workbook, so a cycle's discharge capacity is the counter's increase over that cycle.
* Two workbooks repeat earlier ones row for row (``CS2_35_2_10_11``, ``CS2_38_2_10_11``); they
  are recorded and skipped. Any other overlap in time stops the loader.
* CX2_33 also contains three ``.txt`` exports of another tester (decision C): recorded as
  unconverted source files, the battery is flagged ``earlier_history_not_converted``.

One canonical cycle per (workbook, Cycle_Index) group that contains discharge samples
(current < 0). Temperature stays null (D3). The tester's ``Internal_Resistance(Ohm)`` is a held
reading that changes within a cycle, so the per-cycle value stays null; the full series is kept
in the samples. Every sample keeps its workbook, sheet and worksheet row.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
from python_calamine import CalamineWorkbook

from volterra_ml.acquisition.sources import CALCE, DatasetSpec
from volterra_ml.canonical import bundle as bdl
from volterra_ml.canonical.columns import DB_REQUIRED, SAMPLE_COLUMNS
from volterra_ml.canonical.validate import (
    check_capacity,
    check_capacity_jumps,
    check_samples,
    first_positive_capacity,
)
from volterra_ml.loaders.common import (
    BundleWriter,
    LoaderError,
    float_column,
    span,
    stats,
    verified_raw,
)

LOADER_NAME = "calce"
LOADER_VERSION = "1.0.0"
HEADER = (
    "Data_Point", "Test_Time(s)", "Date_Time", "Step_Time(s)", "Step_Index", "Cycle_Index",
    "Current(A)", "Voltage(V)", "Charge_Capacity(Ah)", "Discharge_Capacity(Ah)",
    "Charge_Energy(Wh)", "Discharge_Energy(Wh)", "dV/dt(V/s)", "Internal_Resistance(Ohm)",
    "Is_FC_Data", "AC_Impedance(Ohm)", "ACI_Phase_Angle(Deg)",
)  # fmt: skip
#: Source column -> extra sample column (all numeric columns other than the core ones).
EXTRA_NUMERIC = {
    "Data_Point": "data_point",
    "Step_Time(s)": "step_time_s",
    "Step_Index": "step_index",
    "Charge_Capacity(Ah)": "charge_capacity_ah",
    "Discharge_Capacity(Ah)": "discharge_capacity_ah",
    "Charge_Energy(Wh)": "charge_energy_wh",
    "Discharge_Energy(Wh)": "discharge_energy_wh",
    "dV/dt(V/s)": "dv_dt_v_per_s",
    "Internal_Resistance(Ohm)": "internal_resistance_ohm",
    "Is_FC_Data": "is_fc_data",
    "AC_Impedance(Ohm)": "ac_impedance_ohm",
    "ACI_Phase_Angle(Deg)": "aci_phase_angle_deg",
}
#: Extra sample columns after the core SAMPLE_COLUMNS (documented in canonical-schema.md).
SAMPLE_EXTRAS: dict[str, tuple[str, bool]] = {
    "source_member": ("string", False),
    "source_sheet": ("string", False),
    "source_row": ("int32", False),  # worksheet row (header = row 1)
    "date_time_local": ("string", True),
    **{name: ("float64", True) for name in EXTRA_NUMERIC.values()},
    "canonical_cycle_index": ("int32", True),  # null for groups without discharge
}
RATED_AH = {"CS2": 1.1, "CX2": 1.35}
PROTOCOL = (
    'CALCE: "All tests underwent the same charging profile which was a standard constant '
    "current/constant voltage protocol with a constant current rate of 0.5C until the voltage "
    "reached 4.2V and then 4.2V was sustained until the charging current dropped to below "
    '0.05A. Unless specified, the discharge cut off voltage for these batteries was 2.7V."'
)
_NAME = re.compile(r"^(C[SX]2_\d+)_(\d{1,2})_(\d{1,2})_(\d{2})\.xlsx$", re.IGNORECASE)
_COL = {name: k for k, name in enumerate(HEADER)}


@dataclass
class _Workbook:
    member: str
    sha256: str
    sheet: str
    values: Any  # float64 matrix (rows x 17); the Date_Time column is NaN here
    times: list[str]  # Date_Time per row, ISO 8601 local time
    name_date: date
    first: datetime
    last: datetime
    content_hash: str
    duplicate_of: str | None = None
    empty_cells: int = 0

    def col(self, name: str) -> Any:
        return self.values[:, _COL[name]]

    @property
    def n(self) -> int:
        return int(self.values.shape[0])


def _as_datetime(value: Any, where: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):  # calamine returns midnight timestamps as dates
        return datetime(value.year, value.month, value.day)
    raise LoaderError(f"{where}: Date_Time {value!r} is not a timestamp")


def _read_workbook(member: str, data: bytes) -> _Workbook:
    m = _NAME.match(member.rsplit("/", 1)[-1])
    if not m:
        raise LoaderError(f"{member}: unexpected workbook name")
    wb = CalamineWorkbook.from_filelike(io.BytesIO(data))
    found = []
    for name in wb.sheet_names:
        rows = wb.get_sheet_by_name(name).to_python(skip_empty_area=False)
        if rows and tuple(rows[0][: len(HEADER)]) == HEADER:
            found.append((name, rows))
    if len(found) != 1:
        raise LoaderError(f"{member}: expected one data sheet, found {len(found)}")
    sheet, rows = found[0]
    if len(rows) < 2:
        raise LoaderError(f"{member}: data sheet {sheet!r} has no rows")
    stamps = [_as_datetime(r[2], f"{member} row {k + 2}") for k, r in enumerate(rows[1:], 0)]
    # An empty numeric cell is missing (NaN -> null), never zero; other text stops the loader.
    empty = sum(1 for r in rows[1:] for j in range(len(HEADER)) if j != 2 and r[j] == "")
    numeric = [
        [(float("nan") if j == 2 or r[j] == "" else r[j]) for j in range(len(HEADER))]
        for r in rows[1:]
    ]
    del rows
    try:
        values = np.array(numeric, dtype=float)
    except (TypeError, ValueError) as exc:
        raise LoaderError(f"{member}: non-numeric value in a numeric column ({exc})") from None
    del numeric
    times = [t.isoformat() for t in stamps]
    digest = hashlib.sha256(values.tobytes())
    digest.update("\n".join(times).encode())
    return _Workbook(
        member=member,
        sha256=hashlib.sha256(data).hexdigest(),
        sheet=sheet,
        values=values,
        times=times,
        name_date=date(2000 + int(m.group(4)), int(m.group(2)), int(m.group(3))),
        first=min(stamps),
        last=max(stamps),
        content_hash=digest.hexdigest(),
        empty_cells=empty,
    )


def _order(workbooks: list[_Workbook]) -> list[_Workbook]:
    """Chronological order; exact repeats are marked, any other overlap is an error."""
    ordered = sorted(workbooks, key=lambda w: (w.first, w.name_date, w.member))
    seen: dict[str, str] = {}
    last_end: datetime | None = None
    last_member = ""
    for wb in ordered:
        if wb.content_hash in seen:
            wb.duplicate_of = seen[wb.content_hash]
            continue
        if last_end is not None and wb.first < last_end:
            raise LoaderError(f"{wb.member} overlaps {last_member} and is not an exact repeat")
        seen[wb.content_hash] = wb.member
        last_end, last_member = wb.last, wb.member
    return ordered


def convert_cell(
    cell: str, zip_bytes: bytes, spec: DatasetSpec = CALCE
) -> tuple[dict[str, Any], list[dict[str, Any]], pa.Table]:
    rated = RATED_AH[cell[:3].upper()]
    workbooks: list[_Workbook] = []
    texts: list[dict[str, Any]] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for member in sorted(z.namelist()):
            if member.endswith("/"):
                continue
            data = z.read(member)
            if member.lower().endswith(".xlsx"):
                workbooks.append(_read_workbook(member, data))
            else:
                texts.append(
                    {
                        "member": member,
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
    if not workbooks:
        raise LoaderError(f"{cell}: no workbooks")
    ordered = _order(workbooks)

    cycles: list[dict[str, Any]] = []
    sample_parts: list[dict[str, Any]] = []
    for wb in ordered:
        if wb.duplicate_of is not None:
            continue
        cyc = wb.col("Cycle_Index")
        cur = wb.col("Current(A)")
        volt = wb.col("Voltage(V)")
        ttime = wb.col("Test_Time(s)")
        qd = wb.col("Discharge_Capacity(Ah)")
        # runs of equal Cycle_Index, in file order
        starts = np.flatnonzero(np.r_[True, cyc[1:] != cyc[:-1]])
        ends = np.r_[starts[1:], cyc.size]
        canonical = np.full(cyc.size, -1, dtype=np.int64)
        prev_qd_end: float | None = None
        for g, (a, b) in enumerate(zip(starts, ends, strict=True)):
            base = qd[a] if prev_qd_end is None else prev_qd_end
            prev_qd_end = float(qd[b - 1])
            dis = np.flatnonzero(cur[a:b] < 0) + a
            if dis.size == 0:
                continue
            chg = np.flatnonzero(cur[a:b] > 0) + a
            capacity: float | None = float(qd[b - 1] - base)
            flags = check_samples(ttime[dis], volt[dis], cur[dis], None)
            flags.update(check_capacity(capacity, rated))
            missing = int(np.isnan(np.delete(wb.values[a:b], _COL["Date_Time"], axis=1)).sum())
            if missing:
                flags["empty_source_cells"] = f"{missing} empty cell(s) in the source workbook"
            if capacity is not None and capacity < 0:
                capacity = None
            if g == len(starts) - 1 and cur[b - 1] < 0:
                flags["file_ends_during_discharge"] = (
                    "the workbook's last sample is a discharge sample; capacity may be partial"
                )
            v_mean, v_min, v_max = stats(volt[dis])
            index = len(cycles)
            canonical[a:b] = index
            row: dict[str, Any] = {
                "external_id": cell,
                "cycle_index": index,
                "cycle_type": "discharge",
                "source_cycle_index": int(cyc[a]),
                "start_time_local": wb.times[a],
                "capacity_ah": capacity,
                "soh_pct": None if capacity is None else capacity / rated * 100.0,
                "temp_mean_c": None,
                "temp_min_c": None,
                "temp_max_c": None,
                "voltage_mean_v": v_mean,
                "voltage_min_v": v_min,
                "voltage_max_v": v_max,
                "current_mean_a": stats(cur[dis])[0],
                "discharge_time_s": span(ttime[dis]),
                "ambient_temp_c": None,
                "internal_resistance_ohm": None,  # held tester reading, see module docstring
                "charge_time_s": span(ttime[chg]),
                "source_ref_json": json.dumps(
                    {
                        "member": wb.member,
                        "sheet": wb.sheet,
                        "cycle_index_in_file": int(cyc[a]),
                        "first_row": int(a) + 2,
                        "last_row": int(b) + 1,
                    },
                    sort_keys=True,
                ),
                "n_samples": int(b - a),
                "quality_flags_json": "",
            }
            row["_flags"] = flags
            cycles.append(row)
        sample_parts.append({"wb": wb, "canonical": canonical})

    for k, detail in check_capacity_jumps([r["capacity_ah"] for r in cycles], rated).items():
        cycles[k]["_flags"]["capacity_jump_up"] = detail
    for row in cycles:
        row["quality_flags_json"] = json.dumps(row.pop("_flags"), sort_keys=True)
        row["db_eligible"] = all(row[k] is not None for k in DB_REQUIRED)

    first = first_positive_capacity(cycles)
    dataset_flags: dict[str, str] = {}
    if texts:
        dataset_flags["earlier_history_not_converted"] = (
            f"{len(texts)} text export(s) of another tester precede the workbooks and are not "
            "converted (undocumented format); cycle numbering starts at the first workbook"
        )
    conditions = {
        "source": "CALCE data page (verbatim)",
        "protocol": PROTOCOL,
        "cell_test": spec.file(f"{cell}.zip").description,
        "rated_capacity_basis": f"CALCE: capacity rating {int(rated * 1000)}mAh",
        "workbooks_in_order": [
            {
                "member": wb.member,
                "sheet": wb.sheet,
                "rows": wb.n,
                "first_sample": wb.first.isoformat(),
                "last_sample": wb.last.isoformat(),
                "duplicate_of": wb.duplicate_of,
                "empty_cells": wb.empty_cells,
            }
            for wb in ordered
        ],
        "unconverted_source_files": texts,
        "temperature": "not measured in these workbooks",
        "dataset_flags": dataset_flags,
    }
    battery = {
        "external_id": cell,
        "source_battery_id": cell,
        "chemistry": "LiCoO2 cathode",
        "chemistry_basis": "stated_by_source",
        "form_factor": "prismatic",
        "rated_capacity_ah": rated,
        "nominal_voltage_v": None,
        "soh_reference": "rated_capacity",
        "soh_reference_capacity_ah": rated,
        "first_capacity_ah": None if first is None else first["capacity_ah"],
        "first_capacity_cycle_index": None if first is None else first["cycle_index"],
        "n_discharge_cycles": len(cycles),
        "n_cycles_with_capacity": sum(1 for r in cycles if r["capacity_ah"] is not None),
        "test_conditions_json": json.dumps(conditions, sort_keys=True),
        "source_files_json": json.dumps(
            [
                {"member": wb.member, "sha256": wb.sha256, "used": wb.duplicate_of is None}
                for wb in sorted(workbooks, key=lambda w: w.member)
            ]
            + [{**t, "used": False} for t in texts],
            sort_keys=True,
        ),
    }
    return battery, cycles, _sample_table(cell, sample_parts)


def sample_schema() -> pa.Schema:
    return bdl.arrow_schema({**SAMPLE_COLUMNS, **SAMPLE_EXTRAS})


def _sample_table(cell: str, parts: list[dict[str, Any]]) -> pa.Table:
    cols: dict[str, list[Any]] = {name: [] for name in sample_schema().names}
    for p in parts:
        wb, canonical = p["wb"], p["canonical"]
        n = wb.n
        cols["external_id"].append(pa.repeat(pa.scalar(cell, pa.string()), n))
        cols["cycle_type"].append(pa.repeat(pa.scalar("cycle", pa.string()), n))
        cols["source_cycle_index"].append(
            pa.array(wb.col("Cycle_Index").astype(np.int32), pa.int32())
        )
        cols["sample_index"].append(pa.array(np.arange(n, dtype=np.int32), pa.int32()))
        cols["time_s"].append(float_column(wb.col("Test_Time(s)")))
        cols["voltage_v"].append(float_column(wb.col("Voltage(V)")))
        cols["current_a"].append(float_column(wb.col("Current(A)")))
        for name in ("temp_c", "aux_current_a", "aux_voltage_v"):
            cols[name].append(pa.nulls(n, pa.float64()))
        cols["source_member"].append(pa.repeat(pa.scalar(wb.member, pa.string()), n))
        cols["source_sheet"].append(pa.repeat(pa.scalar(wb.sheet, pa.string()), n))
        cols["source_row"].append(pa.array(np.arange(2, n + 2, dtype=np.int32), pa.int32()))
        cols["date_time_local"].append(pa.array(wb.times, pa.string()))
        for src, dst in EXTRA_NUMERIC.items():
            cols[dst].append(float_column(wb.col(src)))
        cols["canonical_cycle_index"].append(
            pa.array(canonical.astype(np.int32), pa.int32(), mask=canonical < 0)
        )
    arrays = [pa.concat_arrays(cols[name]) for name in sample_schema().names]
    return pa.Table.from_arrays(arrays, schema=sample_schema())


def build_bundle(raw_root: Path, processed_root: Path, spec: DatasetSpec = CALCE) -> dict[str, Any]:
    directory, inputs = verified_raw(raw_root, spec)
    writer = BundleWriter(spec, processed_root, {"name": LOADER_NAME, "version": LOADER_VERSION})
    try:
        for f in spec.files:
            cell = f.name[: -len(".zip")]
            battery, cycles, samples = convert_cell(cell, (directory / f.name).read_bytes(), spec)
            writer.add_cell(battery, cycles)
            writer.add_table(f"samples/{cell}_cycle.parquet", samples)
        return writer.finish(inputs)
    finally:
        writer.discard()
