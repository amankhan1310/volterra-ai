"""Write canonical Parquet bundles for importer tests (generated values, never real data).

The layout and the checksum rule mirror ``volterra_ml.canonical.bundle`` (the producer), which
the backend does not depend on; ``tests/db/test_import_contract.py`` keeps the column contract
of both sides identical.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from app.db.import_dataset import BATTERY_COLUMNS, CYCLE_COLUMNS, MANIFEST_NAME, SCHEMA_VERSION

_TYPES = {"string": pa.string(), "int32": pa.int32(), "float64": pa.float64(), "bool": pa.bool_()}
RATED = 2.0


def schema(columns: dict[str, tuple[str, bool]]) -> pa.Schema:
    return pa.schema([pa.field(n, _TYPES[t], nullable=null) for n, (t, null) in columns.items()])


def battery(external_id: str = "B0005", **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "external_id": external_id,
        "source_battery_id": external_id,
        "chemistry": None,
        "chemistry_basis": "not_stated",
        "form_factor": "18650",
        "rated_capacity_ah": RATED,
        "nominal_voltage_v": None,
        "soh_reference": "rated_capacity",
        "soh_reference_capacity_ah": RATED,
        "first_capacity_ah": 1.85,
        "first_capacity_cycle_index": 0,
        "n_discharge_cycles": 3,
        "n_cycles_with_capacity": 2,
        "test_conditions_json": json.dumps({"readme_text": "Test README (generated)."}),
        "source_files_json": json.dumps([{"member": "G/B0005.mat", "sha256": "0" * 64}]),
    }
    row.update(overrides)
    return row


def cycle(
    external_id: str = "B0005", index: int = 0, capacity: float | None = 1.85, **overrides: Any
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "external_id": external_id,
        "cycle_index": index,
        "cycle_type": "discharge",
        "source_cycle_index": 2 * index + 1,
        "start_time_local": "2008-04-02T13:08:17.921000",
        "capacity_ah": capacity,
        "soh_pct": None if capacity is None else capacity / RATED * 100.0,
        "temp_mean_c": 30.5,
        "temp_min_c": 24.0,
        "temp_max_c": 38.25,
        "voltage_mean_v": 3.5,
        "voltage_min_v": 2.7,
        "voltage_max_v": 4.2,
        "current_mean_a": None,  # deliberately missing: must stay null in the database
        "discharge_time_s": 3690.0,
        "ambient_temp_c": 24.0,
        "n_samples": 197,
        "quality_flags_json": json.dumps({} if capacity else {"capacity_missing": "empty"}),
        "db_eligible": capacity is not None,
    }
    row.update(overrides)
    return row


def default_cycles() -> list[dict[str, Any]]:
    return [
        cycle(index=0, capacity=1.85),
        cycle(index=1, capacity=None),
        cycle(index=2, capacity=1.8),
    ]


def dataset_block(**overrides: Any) -> dict[str, Any]:
    block: dict[str, Any] = {
        "slug": "nasa-test",
        "source": "nasa_pcoe",
        "version": "2000-01-01",
        "name": "NASA-style test bundle (generated values)",
        "publisher": "tests",
        "landing_url": "https://example.invalid/",
        "citation": "test citation",
        "doi": None,
        "licence": {"status": "not_stated", "statement": "test licence", "usage_requirements": "x"},
        "description": "generated",
        "is_synthetic": False,
        "data_provenance": "measured",
    }
    block.update(overrides)
    return block


def write_bundle(
    data_dir: Path,
    *,
    batteries: list[dict[str, Any]] | None = None,
    cycles: list[dict[str, Any]] | None = None,
    dataset: dict[str, Any] | None = None,
    tamper: Callable[[Path], None] | None = None,
    battery_schema: pa.Schema | None = None,
) -> Path:
    """Write a signed bundle under ``data_dir/processed/<slug>/<version>``; return its path."""
    ds = dataset or dataset_block()
    out: Path = data_dir / "processed" / str(ds["slug"]) / str(ds["version"])
    out.mkdir(parents=True, exist_ok=True)
    bats = [battery()] if batteries is None else batteries
    cyc = default_cycles() if cycles is None else cycles
    pq.write_table(
        pa.Table.from_pylist(bats, schema=battery_schema or schema(BATTERY_COLUMNS)),
        out / "batteries.parquet",
    )
    pq.write_table(pa.Table.from_pylist(cyc, schema=schema(CYCLE_COLUMNS)), out / "cycles.parquet")
    (out / "samples").mkdir(exist_ok=True)
    pq.write_table(pa.table({"x": [1.0]}), out / "samples" / "B0005_discharge.parquet")
    (out / "quality_report.json").write_text(json.dumps({"cells": len(bats)}), encoding="utf-8")
    if tamper is not None:
        tamper(out)
    outputs = []
    for p in sorted(q for q in out.rglob("*") if q.is_file() and q.name != MANIFEST_NAME):
        rel = p.relative_to(out).as_posix()
        rows = pq.read_metadata(p).num_rows if p.suffix == ".parquet" else None
        outputs.append(
            {"path": rel, "rows": rows, "bytes": p.stat().st_size, "sha256": _sha(p.read_bytes())}
        )
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset": ds,
        "loader": {"name": "tests", "version": "0"},
        "inputs": [
            {
                "slug": ds["slug"],
                "version": ds["version"],
                "file": "5_Battery_Data_Set.zip",
                "bytes": 10,
                "sha256": "a" * 64,
            }
        ],
        "outputs": outputs,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    body["bundle_checksum"] = _sha(canonical)
    (out / MANIFEST_NAME).write_text(json.dumps(body, indent=2), encoding="utf-8")
    return out


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
