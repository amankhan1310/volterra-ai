"""NASA PCoE Li-ion Battery Aging loader (Phase 6 M2): raw archive -> canonical Parquet bundle.

Structure, as verified on the downloaded archive (2026-11-15, see docs/datasets):

* ``5_Battery_Data_Set.zip`` holds six group zips with 38 MATLAB 5.0 files and README texts.
  B0025-B0028 appear in two groups; the copies are byte-identical, so one is used and both
  locations are recorded. Copies that differ would stop the loader (no silent choice).
* Each ``Bxxxx.mat`` has one struct named after the cell whose ``cycle`` array holds
  ``type`` (charge | discharge | impedance), ``ambient_temperature`` (deg C), ``time`` (MATLAB
  date vector, no timezone) and ``data``. Discharge data: ``Voltage_measured``,
  ``Current_measured``, ``Temperature_measured``, ``Current_load``, ``Voltage_load``, ``Time``,
  ``Capacity`` (empty in 25 cycles). Charge data uses ``Current_charge`` / ``Voltage_charge``.
  Impedance data: ``Re``, ``Rct`` and complex spectra (no frequency vector in the files).

Decisions applied: one canonical cycle per discharge (D2); SOH relative to the rated 2.0 Ah
(D1, "30% fade in rated capacity (from 2 Ah to 1.4 Ah)"); chemistry recorded as not stated;
nothing is imputed or zeroed (D3); the raw archive is verified against its MANIFEST and pin
before it is read.
"""

from __future__ import annotations

import io
import json
import math
import re
import shutil
import tempfile
import zipfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import scipy
import scipy.io

from volterra_ml.acquisition import manifest as raw_manifest
from volterra_ml.acquisition.sources import NASA_PCOE, DatasetSpec
from volterra_ml.canonical import bundle as bdl
from volterra_ml.canonical.columns import (
    BATTERY_COLUMNS,
    CYCLE_COLUMNS,
    DB_REQUIRED,
    IMPEDANCE_COLUMNS,
    SAMPLE_COLUMNS,
)
from volterra_ml.canonical.validate import (
    check_capacity,
    check_capacity_jumps,
    check_samples,
)

LOADER_NAME = "nasa_pcoe"
LOADER_VERSION = "1.0.0"
RATED_CAPACITY_AH = 2.0
RATED_CAPACITY_BASIS = (
    'NASA: "The experiments were stopped when the batteries reached end-of-life (EOL) '
    'criteria of 30% fade in rated capacity (from 2 Ah to 1.4 Ah)."'
)
FORM_FACTOR = "18650"  # NASA: "Commercially available Li-ion 18650 sized rechargeable batteries"
FloatArray = npt.NDArray[np.float64]
_CELL = re.compile(r"(B\d{4})\.mat$", re.IGNORECASE)
_README_CELL = re.compile(r"\b(B\d{4})\.mat\b")


class LoaderError(Exception):
    """The raw input cannot be converted faithfully."""


@dataclass
class _Copy:
    member: str  # "<group zip>/<member>" inside the outer archive
    sha256: str
    data: bytes


@dataclass
class _Cell:
    name: str
    copies: list[_Copy] = field(default_factory=list)
    readme_member: str | None = None
    readme_text: str | None = None


# --- reading the archive ----------------------------------------------------------------------


def _scan(archive: Path) -> dict[str, _Cell]:
    import hashlib

    cells: dict[str, _Cell] = {}
    readmes: dict[str, tuple[str, str]] = {}
    with zipfile.ZipFile(archive) as outer:
        for group in sorted(i.filename for i in outer.infolist() if i.filename.endswith(".zip")):
            gname = group.rsplit("/", 1)[-1]
            with zipfile.ZipFile(io.BytesIO(outer.read(group))) as inner:
                for info in sorted(inner.infolist(), key=lambda i: i.filename):
                    if info.is_dir():
                        continue
                    member = f"{gname}/{info.filename}"
                    m = _CELL.search(info.filename)
                    if m:
                        raw = inner.read(info)
                        cell = cells.setdefault(m.group(1).upper(), _Cell(m.group(1).upper()))
                        cell.copies.append(_Copy(member, hashlib.sha256(raw).hexdigest(), raw))
                    elif info.filename.lower().endswith(".txt"):
                        text = inner.read(info).decode("latin-1")
                        files_part = text.split("Files:", 1)[-1]
                        for cid in _README_CELL.findall(files_part):
                            readmes.setdefault(cid.upper(), (member, text))
    for name, cell in cells.items():
        digests = {c.sha256 for c in cell.copies}
        if len(digests) != 1:
            raise LoaderError(f"{name}: {len(cell.copies)} copies with different content")
        if name in readmes:
            cell.readme_member, cell.readme_text = readmes[name]
    return dict(sorted(cells.items()))


def _real(value: Any, what: str) -> Any:
    """``value`` as a numpy array; a complex array is an error, never silently truncated."""
    a = np.asarray(value)
    if np.iscomplexobj(a):
        raise LoaderError(f"{what}: complex values where real values are expected")
    return a


def _array(value: Any, what: str = "array") -> FloatArray:
    return np.asarray(_real(value, what), dtype=float).ravel()


def _scalar(value: Any, what: str = "scalar") -> float | None:
    a = _real(value, what).ravel()
    if a.size != 1:
        return None
    x = float(a[0])
    return x if math.isfinite(x) else None


def _maybe_complex(value: Any) -> tuple[float | None, float | None]:
    """(real part, imaginary part or None) of a scalar that the source sometimes stores complex."""
    a = np.asarray(value).ravel()
    if a.size != 1:
        return None, None
    z = complex(a[0])
    if not (math.isfinite(z.real) and math.isfinite(z.imag)):
        return None, None
    return z.real, (z.imag if np.iscomplexobj(a) else None)


def _local_time(datevec: Any) -> str | None:
    v = np.asarray(datevec, dtype=float).ravel()
    if v.size != 6 or not np.all(np.isfinite(v)):
        return None
    y, mo, d, h, mi = (int(x) for x in v[:5])
    if any(float(x) != int(x) for x in v[:5]):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{v[5]:09.6f}"


def _stats(a: FloatArray) -> tuple[float | None, float | None, float | None]:
    finite = a[np.isfinite(a)]
    if finite.size == 0:
        return None, None, None
    return float(np.mean(finite)), float(np.min(finite)), float(np.max(finite))


def _complex_parts(value: Any) -> tuple[list[float] | None, list[float] | None]:
    a = np.asarray(value).ravel()
    if a.size == 0:
        return None, None
    c = a.astype(complex)
    return [float(x) for x in c.real], [float(x) for x in c.imag]


# --- conversion -------------------------------------------------------------------------------


def _padded(a: FloatArray, n: int) -> FloatArray:
    """``a`` extended to ``n`` values with NaN (missing), never with zeros."""
    if a.size == n:
        return a
    out = np.full(n, np.nan)
    out[: a.size] = a
    return out


@dataclass
class CellResult:
    battery: dict[str, Any]
    cycles: list[dict[str, Any]]
    samples: dict[str, pa.Table]  # cycle_type -> per-sample table (SAMPLE_COLUMNS)
    impedance: list[dict[str, Any]]


def _sample_table(name: str, kind: str, parts: list[tuple[int, list[FloatArray]]]) -> pa.Table:
    """Columnar per-sample table; non-finite values become null, finite values keep their bits."""
    src = np.concatenate([np.full(p[1][0].size, p[0], dtype=np.int32) for p in parts])
    idx = np.concatenate([np.arange(p[1][0].size, dtype=np.int32) for p in parts])
    floats = [np.concatenate([p[1][j] for p in parts]) for j in range(6)]
    n = src.size
    columns: dict[str, Any] = {
        "external_id": pa.repeat(pa.scalar(name, pa.string()), n),
        "cycle_type": pa.repeat(pa.scalar(kind, pa.string()), n),
        "source_cycle_index": pa.array(src, pa.int32()),
        "sample_index": pa.array(idx, pa.int32()),
    }
    names = ("time_s", "voltage_v", "current_a", "temp_c", "aux_current_a", "aux_voltage_v")
    for col, values in zip(names, floats, strict=True):
        columns[col] = pa.array(values, pa.float64(), mask=~np.isfinite(values))
    return pa.table(columns, schema=bdl.arrow_schema(SAMPLE_COLUMNS))


def convert_cell(cell: _Cell) -> CellResult:
    copy = cell.copies[0]
    mat = scipy.io.loadmat(io.BytesIO(copy.data), struct_as_record=False)
    if cell.name not in mat:
        raise LoaderError(f"{cell.name}: struct {cell.name!r} not found in {copy.member}")
    cycles = mat[cell.name][0, 0].cycle
    rows: list[dict[str, Any]] = []
    parts: dict[str, list[tuple[int, list[FloatArray]]]] = {"charge": [], "discharge": []}
    impedance: list[dict[str, Any]] = []
    ambients: set[float] = set()
    for src in range(cycles.shape[1]):
        c = cycles[0, src]
        kind = str(np.asarray(c.type).ravel()[0])
        where = f"{cell.name} cycle {src}"
        ambient = _scalar(c.ambient_temperature, f"{where} ambient_temperature")
        if ambient is not None:
            ambients.add(ambient)
        start = _local_time(_real(c.time, f"{where} time"))
        d = c.data[0, 0]
        if kind == "impedance":
            bi_re, bi_im = _complex_parts(d.Battery_impedance)
            ri_re, ri_im = _complex_parts(d.Rectified_Impedance)
            re, re_im = _maybe_complex(d.Re)
            rct, rct_im = _maybe_complex(d.Rct)
            imp_flags = {}
            if re_im is not None:
                imp_flags["re_complex"] = "source Re is complex; real and imaginary parts kept"
            if rct_im is not None:
                imp_flags["rct_complex"] = "source Rct is complex; real and imaginary parts kept"
            impedance.append(
                {
                    "external_id": cell.name,
                    "source_cycle_index": src,
                    "start_time_local": start,
                    "ambient_temp_c": ambient,
                    "re_ohm": re,
                    "re_ohm_im": re_im,
                    "rct_ohm": rct,
                    "rct_ohm_im": rct_im,
                    "battery_impedance_re": bi_re,
                    "battery_impedance_im": bi_im,
                    "rectified_impedance_re": ri_re,
                    "rectified_impedance_im": ri_im,
                    "quality_flags_json": json.dumps(imp_flags, sort_keys=True),
                }
            )
            continue
        if kind not in ("charge", "discharge"):
            raise LoaderError(f"{cell.name}: unknown cycle type {kind!r} at index {src}")
        aux_i = d.Current_load if kind == "discharge" else d.Current_charge
        aux_v = d.Voltage_load if kind == "discharge" else d.Voltage_charge
        t, v, i, temp, ai, av = (
            _array(x, f"{where} {kind} data")
            for x in (d.Time, d.Voltage_measured, d.Current_measured, d.Temperature_measured,
                      aux_i, aux_v)
        )  # fmt: skip
        n = max(t.size, v.size, i.size, temp.size, ai.size, av.size)
        if n:
            parts[kind].append((src, [_padded(a, n) for a in (t, v, i, temp, ai, av)]))
        if kind != "discharge":
            continue
        flags = check_samples(list(t), list(v), list(i), list(temp))
        capacity = _scalar(d.Capacity, f"{where} Capacity")
        flags.update(check_capacity(capacity, RATED_CAPACITY_AH))
        if capacity is not None and capacity < 0:
            capacity = None
        t_mean, t_min, t_max = _stats(temp)
        v_mean, v_min, v_max = _stats(v)
        i_mean, _, _ = _stats(i)
        finite_t = t[np.isfinite(t)]
        row: dict[str, Any] = {
            "external_id": cell.name,
            "cycle_index": len(rows),
            "cycle_type": "discharge",
            "source_cycle_index": src,
            "start_time_local": start,
            "capacity_ah": capacity,
            "soh_pct": None if capacity is None else capacity / RATED_CAPACITY_AH * 100.0,
            "temp_mean_c": t_mean,
            "temp_min_c": t_min,
            "temp_max_c": t_max,
            "voltage_mean_v": v_mean,
            "voltage_min_v": v_min,
            "voltage_max_v": v_max,
            "current_mean_a": i_mean,
            "discharge_time_s": (float(finite_t[-1] - finite_t[0]) if finite_t.size > 1 else None),
            "ambient_temp_c": ambient,
            "n_samples": int(n),
            "quality_flags_json": json.dumps(flags, sort_keys=True),
        }
        row["db_eligible"] = all(row[k] is not None for k in DB_REQUIRED)
        rows.append(row)

    for k, detail in check_capacity_jumps(
        [r["capacity_ah"] for r in rows], RATED_CAPACITY_AH
    ).items():
        cycle_flags = json.loads(rows[k]["quality_flags_json"])
        cycle_flags["capacity_jump_up"] = detail
        rows[k]["quality_flags_json"] = json.dumps(cycle_flags, sort_keys=True)
    with_cap = [r for r in rows if r["capacity_ah"] is not None]
    first = with_cap[0] if with_cap else None
    test_conditions = {
        "source": "NASA PCoE README for this cell's group (verbatim)",
        "readme_member": cell.readme_member,
        "readme_text": cell.readme_text,
        "ambient_temperatures_c": sorted(ambients),
        "rated_capacity_basis": RATED_CAPACITY_BASIS,
    }
    battery = {
        "external_id": cell.name,
        "source_battery_id": cell.name,
        "chemistry": None,
        "chemistry_basis": "not_stated",
        "form_factor": FORM_FACTOR,
        "rated_capacity_ah": RATED_CAPACITY_AH,
        "nominal_voltage_v": None,
        "soh_reference": "rated_capacity",
        "soh_reference_capacity_ah": RATED_CAPACITY_AH,
        "first_capacity_ah": None if first is None else first["capacity_ah"],
        "first_capacity_cycle_index": None if first is None else first["cycle_index"],
        "n_discharge_cycles": len(rows),
        "n_cycles_with_capacity": len(with_cap),
        "test_conditions_json": json.dumps(test_conditions, sort_keys=True),
        "source_files_json": json.dumps(
            [
                {"member": c.member, "sha256": c.sha256, "used": k == 0}
                for k, c in enumerate(cell.copies)
            ],
            sort_keys=True,
        ),
    }
    samples = {kind: _sample_table(cell.name, kind, p) for kind, p in parts.items() if p}
    return CellResult(battery, rows, samples, impedance)


# --- bundle -----------------------------------------------------------------------------------


def _raw_archive(raw_root: Path, spec: DatasetSpec) -> tuple[Path, dict[str, Any]]:
    report = raw_manifest.verify(raw_root, spec)
    if not report.ok:
        problems = "; ".join(f"{p.file}: {p.message}" for p in report.problems)
        raise LoaderError(f"raw data failed verification, nothing converted: {problems}")
    remote = spec.files[0]
    record = raw_manifest.load(report.directory)
    assert record is not None
    rec = record.files[remote.name]
    return report.directory / remote.name, {
        "slug": spec.slug,
        "version": spec.version,
        "file": remote.name,
        "bytes": rec.bytes,
        "sha256": rec.sha256,
    }


def _quality_report(results: Sequence[CellResult]) -> dict[str, Any]:
    per_cell: dict[str, dict[str, int]] = {}
    totals: dict[str, int] = {}
    for r in results:
        counts: dict[str, int] = {}
        for row in r.cycles:
            for flag in json.loads(row["quality_flags_json"]):
                counts[flag] = counts.get(flag, 0) + 1
                totals[flag] = totals.get(flag, 0) + 1
        per_cell[r.battery["external_id"]] = dict(sorted(counts.items()))
    cycles = [row for r in results for row in r.cycles]
    impedance: dict[str, int] = {}
    for r in results:
        for rec in r.impedance:
            for flag in json.loads(rec["quality_flags_json"]):
                impedance[flag] = impedance.get(flag, 0) + 1
    return {
        "cells": len(results),
        "discharge_cycles": len(cycles),
        "db_eligible_cycles": sum(1 for row in cycles if row["db_eligible"]),
        "impedance_records": sum(len(r.impedance) for r in results),
        "flag_totals": dict(sorted(totals.items())),
        "impedance_flag_totals": dict(sorted(impedance.items())),
        "flags_per_cell": per_cell,
    }


def build_bundle(
    raw_root: Path, processed_root: Path, spec: DatasetSpec = NASA_PCOE
) -> dict[str, Any]:
    """Convert the verified raw archive into a canonical bundle; returns its manifest."""
    archive, raw_input = _raw_archive(raw_root, spec)
    cells = _scan(archive)
    results = [convert_cell(cell) for cell in cells.values()]

    final = bdl.bundle_dir(processed_root, spec.slug, spec.version)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{spec.version}.tmp-", dir=final.parent))
    try:
        counts: dict[str, int] = {}

        def put(rel: str, columns: dict[str, tuple[str, bool]], rows: list[dict[str, Any]]) -> None:
            table = bdl.make_table(columns, rows)
            bdl.write_parquet(table, tmp / rel)
            counts[rel] = table.num_rows

        put("batteries.parquet", BATTERY_COLUMNS, [r.battery for r in results])
        put("cycles.parquet", CYCLE_COLUMNS, [row for r in results for row in r.cycles])
        for r in results:
            bid = r.battery["external_id"]
            for kind, table in r.samples.items():
                rel = f"samples/{bid}_{kind}.parquet"
                bdl.write_parquet(table, tmp / rel)
                counts[rel] = table.num_rows
            if r.impedance:
                put(f"impedance/{bid}.parquet", IMPEDANCE_COLUMNS, r.impedance)
        (tmp / "quality_report.json").write_text(
            json.dumps(_quality_report(results), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return bdl.finalize(
            tmp,
            final,
            dataset={
                "slug": spec.slug,
                "source": spec.source,
                "version": spec.version,
                "name": spec.name,
                "publisher": spec.publisher,
                "landing_url": spec.landing_url,
                "citation": spec.citation,
                "doi": spec.doi,
                "licence": {
                    "status": spec.licence.status,
                    "statement": spec.licence.statement,
                    "usage_requirements": spec.licence.usage_requirements,
                },
                "description": spec.description,
                "is_synthetic": False,
                "data_provenance": "measured",
            },
            loader={
                "name": LOADER_NAME,
                "version": LOADER_VERSION,
                "numpy": np.__version__,
                "scipy": scipy.__version__,
                "pyarrow": pa.__version__,
            },
            inputs=[raw_input],
            row_counts=counts,
        )
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)


def iter_cells(archive: Path) -> Iterator[CellResult]:
    """Convert cell by cell (used by validation tests against the source files)."""
    for cell in _scan(archive).values():
        yield convert_cell(cell)
