"""Parquet bundles: the hand-over format from ``volterra_ml`` loaders to the backend importer.

Layout (``<data>/processed/<slug>/<version>/``)::

    bundle_manifest.json      schema version, loader, raw inputs, outputs (rows, bytes, SHA-256)
    batteries.parquet         one row per cell (BATTERY_COLUMNS)
    cycles.parquet            one row per discharge cycle (CYCLE_COLUMNS)
    samples/<id>_<type>.parquet   per-sample traces (SAMPLE_COLUMNS)
    impedance/<id>.parquet    impedance spectra (IMPEDANCE_COLUMNS), when the source has them
    quality_report.json       flag counts per cell

Bundles are deterministic: the same raw input and library versions give byte-identical files,
and ``bundle_checksum`` (over inputs and outputs, no timestamps) identifies the content. A bundle
is built in a temporary folder and moved into place only when complete.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from volterra_ml.acquisition.manifest import sha256_file
from volterra_ml.acquisition.safety import ensure_git_ignored
from volterra_ml.canonical.columns import SCHEMA_VERSION

MANIFEST_NAME = "bundle_manifest.json"
_TYPES: dict[str, pa.DataType] = {
    "string": pa.string(),
    "int32": pa.int32(),
    "int64": pa.int64(),
    "float64": pa.float64(),
    "bool": pa.bool_(),
    "list<float64>": pa.list_(pa.float64()),
}


class BundleError(Exception):
    """A bundle is incomplete, altered or does not match the contract."""


def arrow_schema(columns: Mapping[str, tuple[str, bool]]) -> pa.Schema:
    return pa.schema([pa.field(n, _TYPES[t], nullable=null) for n, (t, null) in columns.items()])


def make_table(
    columns: Mapping[str, tuple[str, bool]], rows: Sequence[Mapping[str, Any]]
) -> pa.Table:
    schema = arrow_schema(columns)
    data = {name: [row[name] for row in rows] for name in columns}
    table = pa.table(data, schema=schema)
    for name, (_, nullable) in columns.items():
        if not nullable and table.column(name).null_count:
            raise BundleError(f"column {name!r} must not contain nulls")
    return table


def write_parquet(table: pa.Table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd", write_statistics=True)


@dataclass(frozen=True)
class OutputFile:
    path: str  # relative to the bundle folder, forward slashes
    rows: int | None
    bytes: int
    sha256: str


def bundle_dir(processed_root: Path, slug: str, version: str) -> Path:
    return processed_root / slug / version


def finalize(
    tmp: Path,
    final: Path,
    *,
    dataset: Mapping[str, Any],
    loader: Mapping[str, str],
    inputs: Sequence[Mapping[str, Any]],
    row_counts: Mapping[str, int],
) -> dict[str, Any]:
    """Write the manifest into ``tmp`` and move it to ``final`` atomically. Returns the manifest."""
    outputs = []
    for path in sorted(p for p in tmp.rglob("*") if p.is_file()):
        rel = path.relative_to(tmp).as_posix()
        outputs.append(
            OutputFile(rel, row_counts.get(rel), path.stat().st_size, sha256_file(path)).__dict__
        )
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset": dict(dataset),
        "loader": dict(loader),
        "inputs": list(inputs),
        "outputs": outputs,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    body["bundle_checksum"] = hashlib.sha256(canonical).hexdigest()
    (tmp / MANIFEST_NAME).write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")

    ensure_git_ignored(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    old = final.with_name(final.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if final.exists():
        os.replace(final, old)
    os.replace(tmp, final)
    if old.exists():
        shutil.rmtree(old)
    return body


def load_manifest(directory: Path) -> dict[str, Any]:
    path = directory / MANIFEST_NAME
    if not path.is_file():
        raise BundleError(f"{directory}: no {MANIFEST_NAME}")
    body: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if body.get("schema_version") != SCHEMA_VERSION:
        raise BundleError(f"unsupported bundle schema_version {body.get('schema_version')!r}")
    return body


def verify_bundle(directory: Path) -> dict[str, Any]:
    """Re-hash every output and recompute the bundle checksum; raise on any difference."""
    body = load_manifest(directory)
    expected = {o["path"] for o in body["outputs"]}
    present = {
        p.relative_to(directory).as_posix()
        for p in directory.rglob("*")
        if p.is_file() and p.name != MANIFEST_NAME
    }
    if present != expected:
        missing, extra = sorted(expected - present), sorted(present - expected)
        raise BundleError(f"bundle files differ from manifest: missing {missing}, extra {extra}")
    for out in body["outputs"]:
        path = directory / out["path"]
        if path.stat().st_size != out["bytes"] or sha256_file(path) != out["sha256"]:
            raise BundleError(f"{out['path']}: content differs from the manifest")
    unsigned = {k: v for k, v in body.items() if k != "bundle_checksum"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(canonical).hexdigest() != body.get("bundle_checksum"):
        raise BundleError("bundle_checksum does not match the manifest content")
    return body
