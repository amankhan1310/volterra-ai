"""Shared building blocks for the CALCE and Severson loaders (Phase 6 M4).

* :func:`verified_raw` re-hashes the raw files against MANIFEST.json and the registry pins before
  anything is read.
* :class:`BundleWriter` writes a canonical bundle *cell by cell*: per-sample tables go straight to
  Parquet, only battery and cycle rows stay in memory, so large sources (Severson: ~10^8
  samples) never have to fit in memory at once.
* :func:`quality_report` counts cycle flags and battery-level ``dataset_flags``.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import scipy

from volterra_ml.acquisition import manifest as raw_manifest
from volterra_ml.acquisition.sources import DatasetSpec
from volterra_ml.canonical import bundle as bdl
from volterra_ml.canonical.columns import BATTERY_COLUMNS, CYCLE_COLUMNS


class LoaderError(Exception):
    """The raw input cannot be converted faithfully."""


def verified_raw(raw_root: Path, spec: DatasetSpec) -> tuple[Path, list[dict[str, Any]]]:
    """The verified raw folder and its input records (file, size, SHA-256) for the manifest."""
    report = raw_manifest.verify(raw_root, spec)
    if not report.ok:
        problems = "; ".join(f"{p.file}: {p.message}" for p in report.problems)
        raise LoaderError(f"raw data failed verification, nothing converted: {problems}")
    record = raw_manifest.load(report.directory)
    assert record is not None
    inputs = [
        {
            "slug": spec.slug,
            "version": spec.version,
            "file": f.name,
            "bytes": record.files[f.name].bytes,
            "sha256": record.files[f.name].sha256,
        }
        for f in spec.files
    ]
    return report.directory, inputs


def dataset_block(spec: DatasetSpec) -> dict[str, Any]:
    return {
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
    }


def quality_report(batteries: list[dict[str, Any]], cycles: list[dict[str, Any]]) -> dict[str, Any]:
    per_cell: dict[str, dict[str, int]] = {}
    totals: dict[str, int] = {}
    for row in cycles:
        cell = per_cell.setdefault(row["external_id"], {})
        for flag in json.loads(row["quality_flags_json"]):
            cell[flag] = cell.get(flag, 0) + 1
            totals[flag] = totals.get(flag, 0) + 1
    battery_flags: dict[str, list[str]] = {}
    for b in batteries:
        for flag in json.loads(b["test_conditions_json"]).get("dataset_flags", {}):
            battery_flags.setdefault(flag, []).append(b["external_id"])
    return {
        "cells": len(batteries),
        "discharge_cycles": len(cycles),
        "db_eligible_cycles": sum(1 for r in cycles if r["db_eligible"]),
        "flag_totals": dict(sorted(totals.items())),
        "battery_flags": {k: sorted(v) for k, v in sorted(battery_flags.items())},
        "flags_per_cell": {k: dict(sorted(v.items())) for k, v in sorted(per_cell.items())},
    }


@dataclass
class BundleWriter:
    """Collects one dataset's bundle in a temporary folder next to its final location."""

    spec: DatasetSpec
    processed_root: Path
    loader: dict[str, str]
    batteries: list[dict[str, Any]] = field(default_factory=list)
    cycles: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.final = bdl.bundle_dir(self.processed_root, self.spec.slug, self.spec.version)
        self.final.parent.mkdir(parents=True, exist_ok=True)
        self.tmp = Path(
            tempfile.mkdtemp(prefix=f".{self.spec.version}.tmp-", dir=self.final.parent)
        )

    def add_table(self, rel: str, table: pa.Table) -> None:
        bdl.write_parquet(table, self.tmp / rel)
        self.counts[rel] = table.num_rows

    def add_cell(self, battery: dict[str, Any], cycles: list[dict[str, Any]]) -> None:
        self.batteries.append(battery)
        self.cycles.extend(cycles)

    def finish(self, inputs: list[dict[str, Any]]) -> dict[str, Any]:
        self.add_table("batteries.parquet", bdl.make_table(BATTERY_COLUMNS, self.batteries))
        self.add_table("cycles.parquet", bdl.make_table(CYCLE_COLUMNS, self.cycles))
        report = quality_report(self.batteries, self.cycles)
        (self.tmp / "quality_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return bdl.finalize(
            self.tmp,
            self.final,
            dataset=dataset_block(self.spec),
            loader={
                **self.loader,
                "numpy": np.__version__,
                "scipy": scipy.__version__,
                "pyarrow": pa.__version__,
            },
            inputs=inputs,
            row_counts=self.counts,
        )

    def discard(self) -> None:
        if self.tmp.exists():
            shutil.rmtree(self.tmp)


def float_column(values: Any) -> pa.Array:
    """float64 Arrow array; non-finite values become null (never zero)."""
    arr = np.asarray(values, dtype=float)
    return pa.array(arr, pa.float64(), mask=~np.isfinite(arr))


def stats(a: Any) -> tuple[float | None, float | None, float | None]:
    finite = np.asarray(a, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return None, None, None
    return float(np.mean(finite)), float(np.min(finite)), float(np.max(finite))


def span(t: Any) -> float | None:
    finite = np.asarray(t, dtype=float)
    finite = finite[np.isfinite(finite)]
    return float(finite[-1] - finite[0]) if finite.size > 1 else None
