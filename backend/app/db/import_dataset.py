"""Import a canonical Parquet bundle (Phase 6 M3) into PostgreSQL.

Run against the database in ``DATABASE_URL``::

    uv run python -m app.db.import_dataset <data-dir>/processed/<slug>/<version> [--data-dir D]

Guarantees:

* **Verified input.** Every bundle file is re-hashed against ``bundle_manifest.json`` and the
  bundle checksum is recomputed before anything is read; columns are checked against the
  canonical contract and every row against the database rules. Any problem rejects the whole
  bundle before a single row is written.
* **All or nothing.** The import runs in one transaction; a failure part-way leaves the database
  exactly as it was.
* **Repeatable.** Re-importing the same bundle (same checksum) is a no-op. A changed bundle
  updates the dataset and each battery *in place* (scenarios stay attached) and replaces that
  battery's cycles; a battery that would disappear stops the import instead of being deleted.
* **Provenance.** Dataset publisher, licence, citation and DOI; per-battery source identifiers,
  chemistry basis, SOH reference and first measured capacity; per-cycle source position and
  quality flags; and every raw and processed file (relative path, size, SHA-256) are recorded.
* **Nothing invented.** Only cycles the loader marked ``db_eligible`` (all analysis inputs
  measured) enter ``cycles``; the others stay in the Parquet bundle with their flags. The
  synthetic dataset can never be overwritten.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.synthetic import CycleRecord
from app.db.models import DATASET_SOURCES, Battery, Cycle, Dataset, DatasetFile
from app.db.seed import cycles_checksum

SCHEMA_VERSION = 2
MANIFEST_NAME = "bundle_manifest.json"
IMPORTABLE_SOURCES = tuple(s for s in DATASET_SOURCES if s not in ("synthetic", "upload"))

#: The columns this importer reads, with their Arrow types and nullability. Must equal the
#: contract in ml/volterra_ml/canonical/columns.py (tests/db/test_import_contract.py).
BATTERY_COLUMNS: dict[str, tuple[str, bool]] = {
    "external_id": ("string", False),
    "source_battery_id": ("string", False),
    "chemistry": ("string", True),
    "chemistry_basis": ("string", False),
    "form_factor": ("string", True),
    "rated_capacity_ah": ("float64", False),
    "nominal_voltage_v": ("float64", True),
    "soh_reference": ("string", False),
    "soh_reference_capacity_ah": ("float64", False),
    "first_capacity_ah": ("float64", True),
    "first_capacity_cycle_index": ("int32", True),
    "n_discharge_cycles": ("int32", False),
    "n_cycles_with_capacity": ("int32", False),
    "test_conditions_json": ("string", False),
    "source_files_json": ("string", False),
}
CYCLE_COLUMNS: dict[str, tuple[str, bool]] = {
    "external_id": ("string", False),
    "cycle_index": ("int32", False),
    "cycle_type": ("string", False),
    "source_cycle_index": ("int32", False),
    "start_time_local": ("string", True),
    "capacity_ah": ("float64", True),
    "soh_pct": ("float64", True),
    "temp_mean_c": ("float64", True),
    "temp_min_c": ("float64", True),
    "temp_max_c": ("float64", True),
    "voltage_mean_v": ("float64", True),
    "voltage_min_v": ("float64", True),
    "voltage_max_v": ("float64", True),
    "current_mean_a": ("float64", True),
    "discharge_time_s": ("float64", True),
    "ambient_temp_c": ("float64", True),
    "internal_resistance_ohm": ("float64", True),
    "charge_time_s": ("float64", True),
    "source_ref_json": ("string", True),
    "n_samples": ("int32", False),
    "quality_flags_json": ("string", False),
    "db_eligible": ("bool", False),
}
DB_REQUIRED = ("capacity_ah", "soh_pct", "temp_mean_c", "voltage_mean_v")
#: Canonical cycle column -> ``cycles`` table column, for the optional measurements.
OPTIONAL_CYCLE_COLUMNS = {
    "temp_min_c": "temp_min_c",
    "temp_max_c": "temp_max_c",
    "voltage_min_v": "voltage_min_v",
    "voltage_max_v": "voltage_max_v",
    "current_mean_a": "current_mean_a",
    "discharge_time_s": "discharge_time_s",
    "ambient_temp_c": "ambient_temp_c",
    "internal_resistance_ohm": "internal_resistance_ohm",
    "charge_time_s": "charge_time_s",
}
#: Database column lengths (app/db/models.py) checked before anything is written.
TEXT_LIMITS = {"external_id": 64, "chemistry": 32, "form_factor": 32}
_ARROW = {"string": pa.string(), "int32": pa.int32(), "float64": pa.float64(), "bool": pa.bool_()}


class BundleImportError(Exception):
    """The bundle is invalid or conflicts with the database; nothing was written."""


@dataclass(frozen=True)
class ImportResult:
    slug: str
    created: bool
    unchanged: bool
    batteries: int
    cycles_imported: int
    cycles_not_imported: int
    files: int
    bundle_checksum: str


# --- reading and verifying the bundle ---------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_bundle(directory: Path) -> dict[str, Any]:
    """Re-hash every output, recompute the bundle checksum; return the manifest."""
    path = directory / MANIFEST_NAME
    if not path.is_file():
        raise BundleImportError(f"{directory}: no {MANIFEST_NAME}")
    body: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if body.get("schema_version") != SCHEMA_VERSION:
        raise BundleImportError(f"unsupported bundle schema_version {body.get('schema_version')!r}")
    expected = {o["path"] for o in body["outputs"]}
    present = {
        p.relative_to(directory).as_posix()
        for p in directory.rglob("*")
        if p.is_file() and p.name != MANIFEST_NAME
    }
    if present != expected:
        raise BundleImportError(
            f"bundle files differ from its manifest: missing {sorted(expected - present)}, "
            f"extra {sorted(present - expected)}"
        )
    for out in body["outputs"]:
        file = directory / out["path"]
        if file.stat().st_size != out["bytes"] or _sha256(file) != out["sha256"]:
            raise BundleImportError(f"{out['path']}: content differs from the bundle manifest")
    unsigned = {k: v for k, v in body.items() if k != "bundle_checksum"}
    digest = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != body.get("bundle_checksum"):
        raise BundleImportError("bundle_checksum does not match the bundle manifest")
    return body


def _read(directory: Path, name: str, columns: dict[str, tuple[str, bool]]) -> list[dict[str, Any]]:
    table = pq.read_table(directory / name)
    if table.schema.names != list(columns):
        raise BundleImportError(f"{name}: columns {table.schema.names} differ from the contract")
    for field in table.schema:
        type_name, nullable = columns[field.name]
        if field.type != _ARROW[type_name]:
            raise BundleImportError(f"{name}: column {field.name!r} has type {field.type}")
        if not nullable and table.column(field.name).null_count:
            raise BundleImportError(f"{name}: column {field.name!r} contains nulls")
    rows: list[dict[str, Any]] = table.to_pylist()
    return rows


def _finite(x: Any) -> bool:
    return isinstance(x, float) and math.isfinite(x)


def _check(
    dataset: dict[str, Any], batteries: list[dict[str, Any]], cycles: list[dict[str, Any]]
) -> None:
    if dataset.get("is_synthetic") is not False:
        raise BundleImportError("only real (non-synthetic) datasets can be imported")
    if dataset.get("source") not in IMPORTABLE_SOURCES:
        raise BundleImportError(f"dataset source {dataset.get('source')!r} cannot be imported")
    ids = [b["external_id"] for b in batteries]
    if not ids or len(ids) != len(set(ids)):
        raise BundleImportError("batteries.parquet: empty or duplicate external_id")
    for b in batteries:
        if not (_finite(b["rated_capacity_ah"]) and b["rated_capacity_ah"] > 0):
            raise BundleImportError(f"{b['external_id']}: rated capacity must be positive")
        if b["soh_reference"] != "rated_capacity" or (
            b["soh_reference_capacity_ah"] != b["rated_capacity_ah"]
        ):
            raise BundleImportError(f"{b['external_id']}: SOH must reference the rated capacity")
        json.loads(b["test_conditions_json"])
        json.loads(b["source_files_json"])
    for b in batteries:
        for column, limit in TEXT_LIMITS.items():
            value = b[column]
            if value is not None and len(value) > limit:
                raise BundleImportError(
                    f"{b['external_id']}: {column} longer than {limit} characters"
                )
    reference = {b["external_id"]: b["soh_reference_capacity_ah"] for b in batteries}
    seen: set[tuple[str, int]] = set()
    for c in cycles:
        key = (c["external_id"], c["cycle_index"])
        where = f"cycle {key[0]}/{key[1]}"
        if c["external_id"] not in reference:
            raise BundleImportError(f"{where}: battery not in batteries.parquet")
        if key in seen:
            raise BundleImportError(f"{where}: duplicate cycle")
        seen.add(key)
        if c["cycle_index"] < 0 or c["source_cycle_index"] < 0 or c["cycle_type"] != "discharge":
            raise BundleImportError(f"{where}: invalid index or cycle type")
        json.loads(c["quality_flags_json"])
        if c["source_ref_json"] is not None and not isinstance(
            json.loads(c["source_ref_json"]), dict
        ):
            raise BundleImportError(f"{where}: source_ref_json must be a JSON object")
        complete = all(_finite(c[k]) for k in DB_REQUIRED)
        if c["db_eligible"] != complete:
            raise BundleImportError(f"{where}: db_eligible does not match its measurements")
        if not complete:
            continue
        if c["capacity_ah"] < 0:
            raise BundleImportError(f"{where}: negative capacity")
        if c["soh_pct"] != c["capacity_ah"] / reference[c["external_id"]] * 100.0:
            raise BundleImportError(f"{where}: soh_pct is not capacity / reference capacity")
        for k in OPTIONAL_CYCLE_COLUMNS:
            if c[k] is not None and not _finite(c[k]):
                raise BundleImportError(f"{where}: {k} is not finite")


# --- writing ----------------------------------------------------------------------------------


def output_kind(rel: str) -> tuple[str, str | None]:
    """(``dataset_files.kind``, battery external id or None) of a bundle output path."""
    top, _, rest = rel.partition("/")
    if top == "samples" and rest.endswith(".parquet"):
        return "samples", rest.rsplit("_", 1)[0]
    if top == "impedance" and rest.endswith(".parquet"):
        return "impedance", rest[: -len(".parquet")]
    if rel in ("batteries.parquet", "cycles.parquet"):
        return rel[: -len(".parquet")], None
    if rel.endswith(".json") and "/" not in rel:
        return "report", None
    raise BundleImportError(f"unexpected bundle file {rel!r}")


def _check_outputs(body: dict[str, Any], batteries: list[dict[str, Any]]) -> None:
    known = {b["external_id"] for b in batteries}
    for out in body["outputs"]:
        _, battery = output_kind(out["path"])
        if battery is not None and battery not in known:
            raise BundleImportError(f"{out['path']}: battery {battery!r} not in batteries.parquet")


def _file_rows(
    body: dict[str, Any], bundle_dir: Path, bundle_rel: str, battery_ids: dict[str, uuid.UUID]
) -> list[dict[str, Any]]:
    manifest = bundle_dir / MANIFEST_NAME
    rows: list[dict[str, Any]] = []
    for raw in body["inputs"]:
        rows.append(
            {
                "battery_id": None,
                "kind": "raw",
                "path": f"raw/{raw['slug']}/{raw['version']}/{raw['file']}",
                "format": raw["file"].rsplit(".", 1)[-1].lower(),
                "bytes": raw["bytes"],
                "sha256": raw["sha256"],
                "rows": None,
            }
        )
    rows.append(
        {
            "battery_id": None,
            "kind": "bundle_manifest",
            "path": f"{bundle_rel}/{MANIFEST_NAME}",
            "format": "json",
            "bytes": manifest.stat().st_size,
            "sha256": _sha256(manifest),
            "rows": None,
        }
    )
    for out in body["outputs"]:
        rel: str = out["path"]
        kind, battery = output_kind(rel)
        rows.append(
            {
                "battery_id": None if battery is None else battery_ids[battery],
                "kind": kind,
                "path": f"{bundle_rel}/{rel}",
                "format": rel.rsplit(".", 1)[-1].lower(),
                "bytes": out["bytes"],
                "sha256": out["sha256"],
                "rows": out["rows"],
            }
        )
    return rows


def _relative(bundle_dir: Path, data_dir: Path) -> str:
    try:
        return bundle_dir.resolve().relative_to(data_dir.resolve()).as_posix()
    except ValueError:
        raise BundleImportError("the bundle must be inside the data directory") from None


async def import_bundle(session: AsyncSession, bundle_dir: Path, data_dir: Path) -> ImportResult:
    """Verify and import one bundle in a single transaction (commits on success)."""
    body = verify_bundle(bundle_dir)
    bundle_rel = _relative(bundle_dir, data_dir)
    batteries = _read(bundle_dir, "batteries.parquet", BATTERY_COLUMNS)
    cycles = _read(bundle_dir, "cycles.parquet", CYCLE_COLUMNS)
    meta_ds: dict[str, Any] = body["dataset"]
    _check(meta_ds, batteries, cycles)
    _check_outputs(body, batteries)
    checksum: str = body["bundle_checksum"]
    report = json.loads((bundle_dir / "quality_report.json").read_text(encoding="utf-8"))
    eligible = [c for c in cycles if c["db_eligible"]]

    try:
        dataset = await session.scalar(select(Dataset).where(Dataset.slug == meta_ds["slug"]))
        created = dataset is None
        if dataset is not None:
            if dataset.source != meta_ds["source"]:
                raise BundleImportError(
                    f"{dataset.slug} exists with source {dataset.source!r}; not overwriting"
                )
            if dataset.checksum == checksum and dataset.status == "ready":
                await session.rollback()
                return ImportResult(
                    meta_ds["slug"], False, True, len(batteries), len(eligible),
                    len(cycles) - len(eligible), 0, checksum,
                )  # fmt: skip
        values = {
            "slug": meta_ds["slug"],
            "name": meta_ds["name"],
            "source": meta_ds["source"],
            "version": meta_ds["version"],
            "licence": meta_ds["licence"]["statement"],
            "citation": meta_ds["citation"],
            "description": meta_ds["description"],
            "publisher": meta_ds["publisher"],
            "landing_url": meta_ds["landing_url"],
            "doi": meta_ds["doi"],
            "status": "ready",
            "checksum": checksum,
            "meta": {
                "licence": meta_ds["licence"],
                "data_provenance": meta_ds.get("data_provenance"),
                "loader": body["loader"],
                "inputs": body["inputs"],
                "bundle_path": bundle_rel,
                "quality_report": report,
            },
        }
        if dataset is None:
            dataset = Dataset(**values)
            session.add(dataset)
        else:
            for key, value in values.items():
                setattr(dataset, key, value)
        await session.flush()

        existing = {
            b.external_id: b
            for b in await session.scalars(select(Battery).where(Battery.dataset_id == dataset.id))
        }
        missing = sorted(set(existing) - {b["external_id"] for b in batteries})
        if missing:
            raise BundleImportError(
                f"batteries {missing} exist in the database but not in the bundle; not deleting"
            )
        by_battery: dict[str, list[dict[str, Any]]] = {}
        for c in eligible:
            by_battery.setdefault(c["external_id"], []).append(c)
        ids: dict[str, uuid.UUID] = {}
        for b in batteries:
            rows = sorted(by_battery.get(b["external_id"], []), key=lambda c: c["cycle_index"])
            records = [
                CycleRecord(c["cycle_index"], c["capacity_ah"], c["soh_pct"], c["temp_mean_c"],
                            c["voltage_mean_v"])
                for c in rows
            ]  # fmt: skip
            conditions = json.loads(b["test_conditions_json"])
            conditions["source_files"] = json.loads(b["source_files_json"])
            conditions["discharge_cycles_in_source"] = b["n_discharge_cycles"]
            conditions["discharge_cycles_with_capacity"] = b["n_cycles_with_capacity"]
            fields = {
                "chemistry": b["chemistry"],
                "chemistry_basis": b["chemistry_basis"],
                "form_factor": b["form_factor"],
                "nominal_capacity_ah": b["rated_capacity_ah"],
                "nominal_voltage_v": b["nominal_voltage_v"],
                "soh_reference": b["soh_reference"],
                "soh_reference_capacity_ah": b["soh_reference_capacity_ah"],
                "first_capacity_ah": b["first_capacity_ah"],
                "first_capacity_cycle_index": b["first_capacity_cycle_index"],
                "test_conditions": conditions,
                "is_synthetic": False,
                "cycles_checksum": cycles_checksum(records),
            }
            battery = existing.get(b["external_id"])
            if battery is None:
                battery = Battery(dataset_id=dataset.id, external_id=b["external_id"], **fields)
                session.add(battery)
            else:
                for key, value in fields.items():
                    setattr(battery, key, value)
            await session.flush()
            ids[b["external_id"]] = battery.id
            await session.execute(delete(Cycle).where(Cycle.battery_id == battery.id))
            if rows:
                await session.execute(
                    insert(Cycle),
                    [
                        {
                            "battery_id": battery.id,
                            "cycle_index": c["cycle_index"],
                            "cycle_type": c["cycle_type"],
                            "source_cycle_index": c["source_cycle_index"],
                            "start_time": None,  # the source gives local time without a zone
                            "capacity_ah": c["capacity_ah"],
                            "soh_pct": c["soh_pct"],
                            "temp_mean_c": c["temp_mean_c"],
                            "voltage_mean_v": c["voltage_mean_v"],
                            **{col: c[k] for k, col in OPTIONAL_CYCLE_COLUMNS.items()},
                            "quality_flags": json.loads(c["quality_flags_json"]),
                            "source_ref": (
                                None
                                if c["source_ref_json"] is None
                                else json.loads(c["source_ref_json"])
                            ),
                        }
                        for c in rows
                    ],
                )

        files = _file_rows(body, bundle_dir, bundle_rel, ids)
        await session.execute(delete(DatasetFile).where(DatasetFile.dataset_id == dataset.id))
        await session.execute(insert(DatasetFile), [{"dataset_id": dataset.id, **f} for f in files])
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    return ImportResult(
        meta_ds["slug"], created, False, len(batteries), len(eligible),
        len(cycles) - len(eligible), len(files), checksum,
    )  # fmt: skip


# --- command line -----------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.db.import_dataset")
    p.add_argument("bundle", type=Path, help="<data-dir>/processed/<slug>/<version>")
    p.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="data directory the bundle lives in (default: $VOLTERRA_DATA_DIR)",
    )
    return p


async def _main(argv: Sequence[str] | None = None) -> int:
    from app.core.config import get_settings
    from app.db.session import Database

    args = _parser().parse_args(argv)
    data_dir = args.data_dir or (
        Path(os.environ["VOLTERRA_DATA_DIR"]) if os.environ.get("VOLTERRA_DATA_DIR") else None
    )
    if data_dir is None:
        print("set VOLTERRA_DATA_DIR or pass --data-dir", file=sys.stderr)
        return 2
    dsn = get_settings().database_dsn()
    if not dsn:
        print("DATABASE_URL is not configured (see backend/.env.example)", file=sys.stderr)
        return 2
    database = Database(dsn)
    try:
        async with database.session() as session:
            result = await import_bundle(session, args.bundle, data_dir)
    except BundleImportError as exc:
        print(f"import refused, nothing written: {exc}", file=sys.stderr)
        return 1
    finally:
        await database.dispose()
    state = (
        "unchanged (already imported)"
        if result.unchanged
        else ("created" if result.created else "updated")
    )
    print(
        f"{result.slug}: {state}; batteries {result.batteries}, cycles imported "
        f"{result.cycles_imported}, kept in Parquet only {result.cycles_not_imported}, "
        f"files {result.files}, bundle {result.bundle_checksum[:12]}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper
    sys.exit(asyncio.run(_main()))
