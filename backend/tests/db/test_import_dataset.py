"""Bundle importer (Phase 6 M3) on disposable PostgreSQL databases."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from alembic import command
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.synthetic import CycleRecord
from app.db import import_dataset as imp
from app.db.import_dataset import BundleImportError, import_bundle
from app.db.models import Battery, Cycle, Dataset, DatasetFile, Scenario
from app.db.repositories import SqlRepository
from app.db.seed import SYNTHETIC_BATTERY_ID, cycles_checksum, seed_synthetic_v1
from app.db.session import Database
from tests.support import bundles as b
from tests.support.api import make_settings
from tests.support.database import assert_disposable, run_isolated
from tests.support.migrations import alembic_config

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
async def session(empty_database_url: str) -> AsyncIterator[AsyncSession]:
    """A migrated disposable database seeded with synthetic-v1 (the real dev setup)."""
    assert_disposable(empty_database_url)
    run_isolated(lambda: command.upgrade(alembic_config(empty_database_url), "head"))
    database = Database(empty_database_url)
    try:
        async with database.session() as s:
            await seed_synthetic_v1(s)
            yield s
    finally:
        await database.dispose()


async def count(session: AsyncSession, model: type, *where: Any) -> int:
    return int(await session.scalar(select(func.count()).select_from(model).where(*where)) or 0)


async def snapshot(session: AsyncSession) -> dict[str, Any]:
    """Everything the importer could touch, to prove a refused import wrote nothing."""
    return {
        "datasets": sorted((d.slug, d.checksum) for d in await session.scalars(select(Dataset))),
        "batteries": await count(session, Battery),
        "cycles": await count(session, Cycle),
        "files": await count(session, DatasetFile),
    }


async def nasa_battery(session: AsyncSession, external_id: str = "B0005") -> Battery:
    battery = await session.scalar(select(Battery).where(Battery.external_id == external_id))
    assert battery is not None
    return battery


# --- successful imports -----------------------------------------------------------------------


async def test_import_records_provenance_and_only_measured_cycles(session, tmp_path: Path):
    bundle = b.write_bundle(tmp_path)
    result = await import_bundle(session, bundle, tmp_path)
    assert (result.created, result.unchanged) == (True, False)
    assert (result.batteries, result.cycles_imported, result.cycles_not_imported) == (1, 2, 1)

    ds = await session.scalar(select(Dataset).where(Dataset.slug == "nasa-test"))
    assert ds is not None
    assert (ds.source, ds.status, ds.version) == ("nasa_pcoe", "ready", "2000-01-01")
    assert (ds.publisher, ds.landing_url, ds.licence) == (
        "tests",
        "https://example.invalid/",
        "test licence",
    )
    assert ds.checksum == result.bundle_checksum
    assert ds.meta["data_provenance"] == "measured"
    assert ds.meta["licence"]["status"] == "not_stated"
    assert ds.meta["bundle_path"] == "processed/nasa-test/2000-01-01"

    bat = await nasa_battery(session)
    assert bat.is_synthetic is False
    assert (bat.chemistry, bat.chemistry_basis, bat.form_factor) == (None, "not_stated", "18650")
    assert (bat.nominal_capacity_ah, bat.soh_reference, bat.soh_reference_capacity_ah) == (
        2.0,
        "rated_capacity",
        2.0,
    )
    assert (bat.first_capacity_ah, bat.first_capacity_cycle_index) == (1.85, 0)
    assert bat.test_conditions["readme_text"] == "Test README (generated)."
    assert bat.test_conditions["discharge_cycles_in_source"] == 3
    assert bat.test_conditions["source_files"][0]["member"] == "G/B0005.mat"

    cycles = list(
        await session.scalars(
            select(Cycle).where(Cycle.battery_id == bat.id).order_by(Cycle.cycle_index)
        )
    )
    assert [(c.cycle_index, c.source_cycle_index) for c in cycles] == [(0, 1), (2, 5)]  # gap kept
    first = cycles[0]
    assert (first.capacity_ah, first.soh_pct) == (1.85, 1.85 / 2.0 * 100.0)
    assert (first.temp_mean_c, first.voltage_mean_v, first.ambient_temp_c) == (30.5, 3.5, 24.0)
    assert first.current_mean_a is None  # missing in the source: null, never 0
    assert first.charge_time_s is None  # likewise (schema v2 column)
    assert first.internal_resistance_ohm == 0.0185  # schema v2 column, as reported
    assert first.start_time is None  # the source has no timezone
    assert first.quality_flags == {}
    assert first.source_ref == {"member": "G/B0005.mat"}  # schema v2, persisted (0003)
    records = [
        CycleRecord(c.cycle_index, c.capacity_ah, c.soh_pct, c.temp_mean_c, c.voltage_mean_v)
        for c in cycles
    ]
    assert bat.cycles_checksum == cycles_checksum(records)


async def test_dataset_files_use_relative_paths_and_link_batteries(session, tmp_path: Path):
    bundle = b.write_bundle(tmp_path)
    await import_bundle(session, bundle, tmp_path)
    files = {f.path: f for f in await session.scalars(select(DatasetFile))}
    assert set(files) == {
        "raw/nasa-test/2000-01-01/5_Battery_Data_Set.zip",
        "processed/nasa-test/2000-01-01/bundle_manifest.json",
        "processed/nasa-test/2000-01-01/batteries.parquet",
        "processed/nasa-test/2000-01-01/cycles.parquet",
        "processed/nasa-test/2000-01-01/quality_report.json",
        "processed/nasa-test/2000-01-01/samples/B0005_discharge.parquet",
    }
    bat = await nasa_battery(session)
    sample = files["processed/nasa-test/2000-01-01/samples/B0005_discharge.parquet"]
    assert (sample.kind, sample.format, sample.battery_id, sample.rows) == (
        "samples",
        "parquet",
        bat.id,
        1,
    )
    assert files["raw/nasa-test/2000-01-01/5_Battery_Data_Set.zip"].kind == "raw"
    manifest = files["processed/nasa-test/2000-01-01/bundle_manifest.json"]
    assert manifest.bytes == (bundle / "bundle_manifest.json").stat().st_size
    assert all(not p.startswith(("/", "C:", "D:")) for p in files)


async def test_reimporting_the_same_bundle_is_a_no_op(session, tmp_path: Path):
    bundle = b.write_bundle(tmp_path)
    await import_bundle(session, bundle, tmp_path)
    before = await snapshot(session)
    again = await import_bundle(session, bundle, tmp_path)
    assert (again.created, again.unchanged) == (False, True)
    assert await snapshot(session) == before


async def test_changed_bundle_updates_in_place_and_keeps_scenarios(session, tmp_path: Path):
    await import_bundle(session, b.write_bundle(tmp_path), tmp_path)
    bat = await nasa_battery(session)
    session.add(Scenario(battery_id=bat.id, name="kept", params={"T": 25}))
    await session.commit()
    changed = b.write_bundle(
        tmp_path,
        batteries=[b.battery(first_capacity_ah=1.9)],
        cycles=[b.cycle(index=0, capacity=1.9), b.cycle(index=1, capacity=1.7)],
    )
    result = await import_bundle(session, changed, tmp_path)
    assert (result.created, result.unchanged, result.cycles_imported) == (False, False, 2)
    again = await nasa_battery(session)
    assert again.id == bat.id and again.first_capacity_ah == 1.9
    caps = list(
        await session.scalars(
            select(Cycle.capacity_ah).where(Cycle.battery_id == bat.id).order_by(Cycle.cycle_index)
        )
    )
    assert caps == [1.9, 1.7]
    assert await count(session, Scenario, Scenario.battery_id == bat.id) == 1
    assert await count(session, Dataset, Dataset.slug == "nasa-test") == 1


async def test_synthetic_dataset_is_untouched(session, tmp_path: Path):
    syn = await nasa_battery(session, SYNTHETIC_BATTERY_ID)
    before = (syn.cycles_checksum, await count(session, Cycle, Cycle.battery_id == syn.id))
    await import_bundle(session, b.write_bundle(tmp_path), tmp_path)
    after = await nasa_battery(session, SYNTHETIC_BATTERY_ID)
    assert (
        after.cycles_checksum,
        await count(session, Cycle, Cycle.battery_id == syn.id),
    ) == before
    assert (after.chemistry_basis, after.soh_reference, after.first_capacity_ah) == (
        None,
        None,
        None,
    )
    synthetic = await session.scalar(select(Dataset).where(Dataset.slug == "synthetic-v1"))
    assert synthetic is not None and synthetic.publisher is None


async def test_imported_battery_loads_through_the_repository(session, tmp_path: Path):
    await import_bundle(session, b.write_bundle(tmp_path), tmp_path)
    bat = await nasa_battery(session)
    records = await SqlRepository(session).load_records(bat.id)
    assert [(r.cycle, r.capacity_ah) for r in records] == [(0, 1.85), (2, 1.8)]


# --- refused imports write nothing ------------------------------------------------------------


def _drop_column(out: Path) -> None:
    import pyarrow.parquet as pq

    t = pq.read_table(out / "cycles.parquet").drop_columns(["n_samples"])
    pq.write_table(t, out / "cycles.parquet")


def _wrong_type(out: Path) -> None:
    import pyarrow.parquet as pq

    t = pq.read_table(out / "cycles.parquet")
    t = t.set_column(
        t.schema.get_field_index("n_samples"), "n_samples", t.column("n_samples").cast(pa.int64())
    )
    pq.write_table(t, out / "cycles.parquet")


def _null_required(out: Path) -> None:
    import pyarrow.parquet as pq

    t = pq.read_table(out / "batteries.parquet")
    fields = [f.with_nullable(True) for f in t.schema]
    t = pa.Table.from_pylist(
        [{**t.to_pylist()[0], "source_battery_id": None}], schema=pa.schema(fields)
    )
    pq.write_table(t, out / "batteries.parquet")


def _orphan_samples(out: Path) -> None:
    import pyarrow.parquet as pq

    pq.write_table(pa.table({"x": [1.0]}), out / "samples" / "B0099_discharge.parquet")


def _unexpected_file(out: Path) -> None:
    (out / "notes.txt").write_text("x")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"dataset": b.dataset_block(is_synthetic=True)}, "only real"),
        ({"dataset": b.dataset_block(source="synthetic")}, "cannot be imported"),
        ({"batteries": [b.battery(), b.battery()]}, "duplicate external_id"),
        ({"batteries": [b.battery(chemistry="x" * 33)]}, "chemistry longer than 32 characters"),
        (
            {"batteries": [b.battery(rated_capacity_ah=0.0, soh_reference_capacity_ah=0.0)]},
            "must be positive",
        ),
        ({"batteries": [b.battery(soh_reference_capacity_ah=1.9)]}, "must reference the rated"),
        ({"cycles": [b.cycle(), b.cycle()]}, "duplicate cycle"),
        ({"cycles": [b.cycle(external_id="B0099")]}, "not in batteries.parquet"),
        ({"cycles": [b.cycle(cycle_type="charge")]}, "invalid index or cycle type"),
        ({"cycles": [b.cycle(capacity=None, db_eligible=True)]}, "db_eligible does not match"),
        ({"cycles": [b.cycle(capacity=-0.5)]}, "negative capacity"),
        ({"cycles": [b.cycle(soh_pct=50.0)]}, "soh_pct is not capacity"),
        ({"cycles": [b.cycle(temp_max_c=float("inf"))]}, "temp_max_c is not finite"),
        ({"cycles": [b.cycle(internal_resistance_ohm=float("nan"))]}, "internal_resistance_ohm"),
        ({"cycles": [b.cycle(source_ref_json="[1, 2]")]}, "source_ref_json must be a JSON object"),
        ({"tamper": _drop_column}, "differ from the contract"),
        ({"tamper": _wrong_type}, "has type int64"),
        ({"tamper": _null_required}, "contains nulls"),
        ({"tamper": _orphan_samples}, "battery 'B0099' not in batteries.parquet"),
        ({"tamper": _unexpected_file}, "unexpected bundle file 'notes.txt'"),
    ],
)
async def test_invalid_bundles_are_refused_before_writing(session, tmp_path: Path, kwargs, message):
    before = await snapshot(session)
    bundle = b.write_bundle(tmp_path, **kwargs)
    with pytest.raises(BundleImportError, match=message):
        await import_bundle(session, bundle, tmp_path)
    assert await snapshot(session) == before


@pytest.mark.parametrize("damage", ["modify", "remove", "extra", "checksum", "schema", "missing"])
async def test_damaged_bundles_are_refused(session, tmp_path: Path, damage: str):
    bundle = b.write_bundle(tmp_path)
    manifest = bundle / "bundle_manifest.json"
    body = json.loads(manifest.read_text())
    if damage == "modify":
        (bundle / "quality_report.json").write_text('{"cells": 99}')
        match = "content differs"
    elif damage == "remove":
        (bundle / "quality_report.json").unlink()
        match = "missing \\['quality_report.json'\\]"
    elif damage == "extra":
        (bundle / "extra.json").write_text("{}")
        match = "extra \\['extra.json'\\]"
    elif damage == "checksum":
        body["loader"]["version"] = "changed"
        manifest.write_text(json.dumps(body))
        match = "bundle_checksum does not match"
    elif damage == "schema":
        body["schema_version"] = 99
        manifest.write_text(json.dumps(body))
        match = "unsupported bundle schema_version 99"
    else:
        manifest.unlink()
        match = "no bundle_manifest.json"
    before = await snapshot(session)
    with pytest.raises(BundleImportError, match=match):
        await import_bundle(session, bundle, tmp_path)
    assert await snapshot(session) == before


async def test_bundle_outside_the_data_directory_is_refused(session, tmp_path: Path):
    bundle = b.write_bundle(tmp_path / "elsewhere")
    with pytest.raises(BundleImportError, match="inside the data directory"):
        await import_bundle(session, bundle, tmp_path / "data")


async def test_existing_dataset_with_another_source_is_never_overwritten(session, tmp_path: Path):
    bundle = b.write_bundle(tmp_path, dataset=b.dataset_block(slug="synthetic-v1"))
    before = await snapshot(session)
    with pytest.raises(BundleImportError, match="exists with source 'synthetic'"):
        await import_bundle(session, bundle, tmp_path)
    assert await snapshot(session) == before


async def test_batteries_are_never_deleted_by_a_reimport(session, tmp_path: Path):
    two = [b.battery("B0005"), b.battery("B0006")]
    await import_bundle(session, b.write_bundle(tmp_path, batteries=two), tmp_path)
    before = await snapshot(session)
    with pytest.raises(BundleImportError, match="\\['B0006'\\] exist in the database"):
        await import_bundle(
            session, b.write_bundle(tmp_path, batteries=[b.battery("B0005")]), tmp_path
        )
    assert await snapshot(session) == before


async def test_a_failure_part_way_rolls_everything_back(session, tmp_path: Path, monkeypatch):
    before = await snapshot(session)

    def boom(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("disk failure while recording files")

    monkeypatch.setattr(imp, "_file_rows", boom)  # after datasets, batteries and cycles
    with pytest.raises(RuntimeError, match="disk failure"):
        await import_bundle(session, b.write_bundle(tmp_path), tmp_path)
    assert await snapshot(session) == before


# --- command line -----------------------------------------------------------------------------


async def test_cli_imports_and_reports(
    empty_database_url: str, tmp_path: Path, monkeypatch, capsys
):
    run_isolated(lambda: command.upgrade(alembic_config(empty_database_url), "head"))
    settings = make_settings(database_url=empty_database_url)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    bundle = b.write_bundle(tmp_path)
    monkeypatch.setenv("VOLTERRA_DATA_DIR", str(tmp_path))
    assert await imp._main([str(bundle)]) == 0
    out = capsys.readouterr().out
    assert "nasa-test: created; batteries 1, cycles imported 2, kept in Parquet only 1" in out
    assert await imp._main([str(bundle), "--data-dir", str(tmp_path)]) == 0
    assert "unchanged (already imported)" in capsys.readouterr().out
    (bundle / "quality_report.json").write_text("{}")
    assert await imp._main([str(bundle)]) == 1
    assert "import refused, nothing written" in capsys.readouterr().err
    assert "postgresql" not in out and "@" not in out


async def test_cli_needs_a_data_dir_and_a_database(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.delenv("VOLTERRA_DATA_DIR", raising=False)
    assert await imp._main([str(tmp_path)]) == 2
    assert "set VOLTERRA_DATA_DIR" in capsys.readouterr().err
    monkeypatch.setattr("app.core.config.get_settings", lambda: make_settings())
    assert await imp._main([str(tmp_path), "--data-dir", str(tmp_path)]) == 2
    assert "DATABASE_URL is not configured" in capsys.readouterr().err
