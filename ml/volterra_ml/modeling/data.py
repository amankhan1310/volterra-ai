"""Load canonical bundles into per-cell series for modelling (read-only; nothing is written).

A cell's series keeps only cycles with a usable capacity measurement: cycles flagged
``capacity_missing``, ``capacity_negative``, ``capacity_zero`` or ``empty_samples`` are not
measurements of the cell's capacity and are dropped (they stay in the bundle). Other flags, such as
``capacity_jump_up`` (NASA capacity regeneration after rests), are kept: they are real behaviour.
Missing channels are NaN and are never filled in here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pyarrow.parquet as pq

FloatArray = npt.NDArray[np.float64]

#: Per-cycle signals a model may use; never capacity, SOH or discharge time (they encode SOH).
CHANNELS = (
    "temp_mean_c",
    "temp_max_c",
    "voltage_mean_v",
    "voltage_min_v",
    "internal_resistance_ohm",
    "charge_time_s",
    "ambient_temp_c",
)
NOT_A_CAPACITY_MEASUREMENT = frozenset(
    {"capacity_missing", "capacity_negative", "capacity_zero", "empty_samples"}
)
#: Battery-level dataset flags that exclude a cell from modelling (Severson's own exclusions).
EXCLUDING_FLAGS = frozenset({"paper_excluded"})


@dataclass(frozen=True)
class Cell:
    dataset: str
    external_id: str
    chemistry: str | None
    rated_capacity_ah: float
    cycle: FloatArray  # cycle_index, increasing (float for arithmetic)
    soh: FloatArray  # % of the rated capacity (decision D1)
    channels: dict[str, FloatArray] = field(repr=False)
    excluded: str | None = None
    reported_cycle_life: float | None = None

    @property
    def key(self) -> str:
        return f"{self.dataset}:{self.external_id}"

    def __len__(self) -> int:
        return len(self.cycle)


@dataclass(frozen=True)
class Bundle:
    slug: str
    version: str
    checksum: str
    cells: tuple[Cell, ...]
    dropped_cycles: int


def _array(rows: list[dict[str, Any]], key: str) -> FloatArray:
    return np.array([np.nan if r[key] is None else float(r[key]) for r in rows], dtype=np.float64)


def load_bundle(bundle_dir: Path) -> Bundle:
    manifest = json.loads((bundle_dir / "bundle_manifest.json").read_text(encoding="utf-8"))
    slug = str(manifest["dataset"]["slug"])
    batteries = pq.read_table(bundle_dir / "batteries.parquet").to_pylist()
    columns = ["external_id", "cycle_index", "soh_pct", "quality_flags_json", *CHANNELS]
    cycles = pq.read_table(bundle_dir / "cycles.parquet", columns=columns).to_pylist()
    by_cell: dict[str, list[dict[str, Any]]] = {}
    dropped = 0
    for row in cycles:
        flags = set(json.loads(row["quality_flags_json"]))
        if row["soh_pct"] is None or flags & NOT_A_CAPACITY_MEASUREMENT:
            dropped += 1
            continue
        by_cell.setdefault(row["external_id"], []).append(row)
    cells = []
    for b in batteries:
        rows = sorted(by_cell.get(b["external_id"], []), key=lambda r: r["cycle_index"])
        conditions = json.loads(b["test_conditions_json"])
        raw_flags = conditions.get("dataset_flags") or {}
        dataset_flags = json.loads(raw_flags) if isinstance(raw_flags, str) else raw_flags
        excluded = next((f for f in sorted(dataset_flags) if f in EXCLUDING_FLAGS), None)
        # The source's own end-of-life label (Severson et al.); joined cells use the joined life.
        life = conditions.get("cycle_life_source_joined") or conditions.get("cycle_life_source")
        cells.append(
            Cell(
                dataset=slug,
                external_id=b["external_id"],
                chemistry=b["chemistry"],
                rated_capacity_ah=float(b["soh_reference_capacity_ah"]),
                cycle=np.array([float(r["cycle_index"]) for r in rows], dtype=np.float64),
                soh=_array(rows, "soh_pct"),
                channels={c: _array(rows, c) for c in CHANNELS},
                excluded=excluded,
                reported_cycle_life=_float_or_none(life),
            )
        )
    return Bundle(
        slug=slug,
        version=str(manifest["dataset"]["version"]),
        checksum=str(manifest["bundle_checksum"]),
        cells=tuple(cells),
        dropped_cycles=dropped,
    )


def _float_or_none(value: object) -> float | None:
    try:
        number = float(str(value))
    except ValueError:
        return None
    return number if np.isfinite(number) else None
