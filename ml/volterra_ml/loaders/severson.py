"""Severson et al. 2019 loader (Phase 6 M4): three MATLAB 7.3 (HDF5) batch files -> bundle.

Structure, as verified on the files (2026-11-15, see docs/datasets/severson-2019.md): a ``batch``
struct whose fields (``summary``, ``cycles``, ``policy_readable``, ``cycle_life``, ``barcode``,
``channel_id``, ``Vdlin``) hold one object reference per entry; 46 + 48 + 46 = 140 entries.
``summary`` has per-cycle ``QDischarge``, ``QCharge``, ``IR``, ``Tavg``, ``Tmin``, ``Tmax``,
``chargetime`` (minutes) and ``cycle``; ``cycles`` has per-sample ``t`` (minutes), ``V``, ``I``,
``T``, ``Qc``, ``Qd`` (plus the authors' interpolated ``Qdlin``/``Tdlin``/``discharge_dQdV``,
which are derived and stay in the raw files).

Decision A (as in the authors' ``Load Data.ipynb``): batch-2 entries b2c7, b2c8, b2c9, b2c15 and
b2c16 continue batch-1 cells b1c0..b1c4 and are joined to them (both locations recorded), giving
135 batteries; the 11 cells the paper excludes are kept and flagged ``paper_excluded``.

One canonical cycle per summary cycle (``cycle_type`` ``discharge``, as for all datasets: the
row describes the cycle's discharge; Severson's charge and discharge share one record).
Capacity, temperatures, internal resistance and charge time are the source's own per-cycle
summary values; voltage and current statistics come from the cycle's discharge samples
(current < 0). The files carry no absolute timestamps. Cells are read one at a time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pyarrow as pa

from volterra_ml.acquisition.sources import SEVERSON, DatasetSpec
from volterra_ml.canonical import bundle as bdl
from volterra_ml.canonical.columns import ANALYSIS_INPUTS, SAMPLE_COLUMNS
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

LOADER_NAME = "severson"
LOADER_VERSION = "1.0.0"
RATED_AH = 1.1
#: Batch-1 cell -> its batch-2 continuation (Load Data.ipynb: batch1_keys / batch2_keys).
CONTINUATIONS = {"b1c0": "b2c7", "b1c1": "b2c8", "b1c2": "b2c9", "b1c3": "b2c15", "b1c4": "b2c16"}
#: Cycles the authors add to cycle_life for the joined cells (Load Data.ipynb: add_len).
CONTINUATION_CYCLE_LIFE = {"b1c0": 662, "b1c1": 981, "b1c2": 1060, "b1c3": 208, "b1c4": 482}
PAPER_EXCLUDED = {
    **{c: "does not reach 80% capacity" for c in ("b1c8", "b1c10", "b1c12", "b1c13", "b1c22")},
    **{c: "noisy channel" for c in ("b3c2", "b3c23", "b3c32", "b3c37", "b3c42", "b3c43")},
}
EXCLUSION_SOURCE = "authors' Load Data.ipynb (data-driven-prediction-of-battery-cycle-life repo)"
SUMMARY_FIELDS = ("QDischarge", "QCharge", "IR", "Tavg", "Tmin", "Tmax", "chargetime", "cycle")
SAMPLE_FIELDS = ("t", "V", "I", "T", "Qc", "Qd")
SAMPLE_EXTRAS: dict[str, tuple[str, bool]] = {
    "time_min": ("float64", True),  # source t (minutes); time_s = time_min * 60
    "charge_ah": ("float64", True),  # source Qc
    "discharge_ah": ("float64", True),  # source Qd
    "source_member": ("string", False),  # batch file
    "source_cell": ("string", False),  # entry name, e.g. b2c7 for a joined segment
    "canonical_cycle_index": ("int32", False),
}


def sample_schema() -> pa.Schema:
    return bdl.arrow_schema({**SAMPLE_COLUMNS, **SAMPLE_EXTRAS})


def _text(f: h5py.File, ref: Any) -> str | None:
    """A MATLAB char array as text; None for objects MATLAB stored opaquely (e.g. strings)."""
    a = np.asarray(f[ref][()])
    if a.dtype != np.uint16:
        return None
    return "".join(chr(int(c)) for c in a.ravel())


def _real(a: Any, where: str) -> Any:
    arr = np.asarray(a)
    if np.iscomplexobj(arr):
        raise LoaderError(f"{where}: complex values where real values are expected")
    return arr.astype(float).ravel()


def _scalar(a: Any) -> float | None:
    if a.size != 1:
        return None
    x = float(a[0])
    return x if np.isfinite(x) else None


class _Entry:
    """One batch entry (cell or continuation segment) inside an open batch file."""

    def __init__(self, f: h5py.File, member: str, batch: int, index: int) -> None:
        b = f["batch"]
        self.f, self.member, self.index = f, member, index
        self.name = f"b{batch}c{index}"
        summary = f[b["summary"][index, 0]]
        self.summary = {
            k: _real(summary[k][()], f"{self.name} summary {k}") for k in SUMMARY_FIELDS
        }
        n = self.summary["QDischarge"].size
        if any(v.size != n for v in self.summary.values()):
            raise LoaderError(f"{self.name}: summary fields have different lengths")
        self.cycles = f[b["cycles"][index, 0]]
        if any(self.cycles[k].shape[0] != n for k in SAMPLE_FIELDS):
            raise LoaderError(f"{self.name}: {n} summary cycles but different sample records")
        self.n = n
        self.policy = _text(f, b["policy_readable"][index, 0])
        life = _real(f[b["cycle_life"][index, 0]][()], f"{self.name} cycle_life")
        self.cycle_life = _scalar(life)

    def samples(self, k: int) -> dict[str, Any]:
        return {
            key: _real(self.f[self.cycles[key][k, 0]][()], f"{self.name} cycle {k} {key}")
            for key in SAMPLE_FIELDS
        }


def _convert(
    cell: str,
    segments: list[_Entry],
    excluded: dict[str, str] = PAPER_EXCLUDED,
    continuation_life: dict[str, int] = CONTINUATION_CYCLE_LIFE,
) -> tuple[dict[str, Any], list[dict[str, Any]], pa.Table]:
    cycles: list[dict[str, Any]] = []
    parts: dict[str, list[Any]] = {name: [] for name in sample_schema().names}
    for seg in segments:
        s = seg.summary
        for k in range(seg.n):
            smp = seg.samples(k)
            t, v, i, temp = smp["t"], smp["V"], smp["I"], smp["T"]
            n = max(x.size for x in smp.values())
            dis = np.flatnonzero(i < 0) if i.size == v.size == t.size else np.array([], dtype=int)
            capacity = _scalar(s["QDischarge"][k : k + 1])
            flags = check_samples(
                t[dis] * 60.0, v[dis], i[dis], temp[dis] if temp.size == i.size else temp
            )
            if dis.size == 0 and "empty_samples" not in flags:
                flags["no_discharge_samples"] = "no samples with negative current"
            flags.update(check_capacity(capacity, RATED_AH))
            if capacity is not None and capacity < 0:
                capacity = None
            v_mean, v_min, v_max = stats(v[dis]) if dis.size else (None, None, None)
            dt = span(t[dis]) if dis.size else None
            charge_min = _scalar(s["chargetime"][k : k + 1])
            index = len(cycles)
            cycles.append(
                {
                    "external_id": cell,
                    "cycle_index": index,
                    "cycle_type": "discharge",
                    "source_cycle_index": k,
                    "start_time_local": None,
                    "capacity_ah": capacity,
                    "soh_pct": None if capacity is None else capacity / RATED_AH * 100.0,
                    "temp_mean_c": _scalar(s["Tavg"][k : k + 1]),
                    "temp_min_c": _scalar(s["Tmin"][k : k + 1]),
                    "temp_max_c": _scalar(s["Tmax"][k : k + 1]),
                    "voltage_mean_v": v_mean,
                    "voltage_min_v": v_min,
                    "voltage_max_v": v_max,
                    "current_mean_a": stats(i[dis])[0] if dis.size else None,
                    "discharge_time_s": None if dt is None else dt * 60.0,
                    "ambient_temp_c": None,
                    "internal_resistance_ohm": _scalar(s["IR"][k : k + 1]),
                    "charge_time_s": None if charge_min is None else charge_min * 60.0,
                    "source_ref_json": json.dumps(
                        {
                            "member": seg.member,
                            "cell": seg.name,
                            "array_position": k,
                            "summary_cycle": _scalar(s["cycle"][k : k + 1]),
                        },
                        sort_keys=True,
                    ),
                    "n_samples": int(n),
                    "_flags": flags,
                }
            )
            padded = [
                np.pad(x, (0, n - x.size), constant_values=np.nan)
                for x in (t, v, i, temp, smp["Qc"], smp["Qd"])
            ]
            parts["external_id"].append(pa.repeat(pa.scalar(cell, pa.string()), n))
            parts["cycle_type"].append(pa.repeat(pa.scalar("cycle", pa.string()), n))
            parts["source_cycle_index"].append(pa.array(np.full(n, k, dtype=np.int32), pa.int32()))
            parts["sample_index"].append(pa.array(np.arange(n, dtype=np.int32), pa.int32()))
            parts["time_s"].append(float_column(padded[0] * 60.0))
            parts["voltage_v"].append(float_column(padded[1]))
            parts["current_a"].append(float_column(padded[2]))
            parts["temp_c"].append(float_column(padded[3]))
            parts["aux_current_a"].append(pa.nulls(n, pa.float64()))
            parts["aux_voltage_v"].append(pa.nulls(n, pa.float64()))
            parts["time_min"].append(float_column(padded[0]))
            parts["charge_ah"].append(float_column(padded[4]))
            parts["discharge_ah"].append(float_column(padded[5]))
            parts["source_member"].append(pa.repeat(pa.scalar(seg.member, pa.string()), n))
            parts["source_cell"].append(pa.repeat(pa.scalar(seg.name, pa.string()), n))
            parts["canonical_cycle_index"].append(
                pa.array(np.full(n, index, dtype=np.int32), pa.int32())
            )

    for k, detail in check_capacity_jumps([r["capacity_ah"] for r in cycles], RATED_AH).items():
        cycles[k]["_flags"]["capacity_jump_up"] = detail
    for row in cycles:
        row["quality_flags_json"] = json.dumps(row.pop("_flags"), sort_keys=True)
        row["db_eligible"] = all(row[k] is not None for k in ANALYSIS_INPUTS)

    head = segments[0]
    dataset_flags: dict[str, str] = {}
    if cell in excluded:
        dataset_flags["paper_excluded"] = f"{excluded[cell]} ({EXCLUSION_SOURCE})"
    if len(segments) > 1:
        dataset_flags["joined_segments"] = (
            f"continued in {segments[1].member} as {segments[1].name}; "
            f"joined as in {EXCLUSION_SOURCE}"
        )
    life = head.cycle_life
    conditions = {
        "source": "Severson et al. 2019 batch files (data.matr.io)",
        "charging_policy": head.policy,
        "batch_member": head.member,
        "cycle_life_source": life,
        "cycle_life_source_joined": (
            None
            if life is None or cell not in continuation_life
            else life + continuation_life[cell]
        ),
        "segments": [{"member": s.member, "cell": s.name, "cycles": s.n} for s in segments],
        "barcode_and_channel": "stored as opaque MATLAB objects in the source; not decoded",
        "test_environment": "30 C chamber (paper)",
        "cell_model": "A123 APR18650M1A, 1.1 Ah nominal (paper)",
        "dataset_flags": dataset_flags,
    }
    first = first_positive_capacity(cycles)
    battery = {
        "external_id": cell,
        "source_battery_id": cell,
        "chemistry": "LiFePO4/graphite",
        "chemistry_basis": "stated_by_source",
        "form_factor": "18650",
        "rated_capacity_ah": RATED_AH,
        "nominal_voltage_v": None,
        "soh_reference": "rated_capacity",
        "soh_reference_capacity_ah": RATED_AH,
        "first_capacity_ah": None if first is None else first["capacity_ah"],
        "first_capacity_cycle_index": None if first is None else first["cycle_index"],
        "n_discharge_cycles": len(cycles),
        "n_cycles_with_capacity": sum(1 for r in cycles if r["capacity_ah"] is not None),
        "test_conditions_json": json.dumps(conditions, sort_keys=True),
        "source_files_json": json.dumps(
            [{"member": s.member, "entry": s.name, "used": True} for s in segments], sort_keys=True
        ),
    }
    arrays = [pa.concat_arrays(parts[name]) for name in sample_schema().names]
    return battery, cycles, pa.Table.from_arrays(arrays, schema=sample_schema())


def build_bundle(
    raw_root: Path,
    processed_root: Path,
    spec: DatasetSpec = SEVERSON,
    *,
    continuations: dict[str, str] = CONTINUATIONS,
    excluded: dict[str, str] = PAPER_EXCLUDED,
    continuation_life: dict[str, int] = CONTINUATION_CYCLE_LIFE,
) -> dict[str, Any]:
    directory, inputs = verified_raw(raw_root, spec)
    writer = BundleWriter(spec, processed_root, {"name": LOADER_NAME, "version": LOADER_VERSION})
    files = [h5py.File(directory / f.name, "r") for f in spec.files]
    try:
        sizes = [f["batch"]["summary"].shape[0] for f in files]
        names = {
            n: (b, i)
            for b, size in enumerate(sizes)
            for i in range(size)
            for n in [f"b{b + 1}c{i}"]
        }
        continuation_of = {v: k for k, v in continuations.items()}
        missing = [
            n for n in [*continuations, *continuations.values(), *excluded] if n not in names
        ]
        if missing:
            raise LoaderError(f"expected entries not in the batch files: {missing}")
        for name, (b, i) in names.items():
            if name in continuation_of:
                continue  # converted with the cell it continues
            segments = [_Entry(files[b], spec.files[b].name, b + 1, i)]
            if name in continuations:
                cb, ci = names[continuations[name]]
                segments.append(_Entry(files[cb], spec.files[cb].name, cb + 1, ci))
            battery, cycles, samples = _convert(name, segments, excluded, continuation_life)
            writer.add_cell(battery, cycles)
            writer.add_table(f"samples/{name}_cycle.parquet", samples)
        return writer.finish(inputs)
    finally:
        for f in files:
            f.close()
        writer.discard()
