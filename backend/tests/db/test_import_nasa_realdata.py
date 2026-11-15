"""Real NASA bundle -> disposable PostgreSQL database (local only; skipped in CI).

Completes the end-to-end check raw archive -> volterra_ml loader -> Parquet bundle -> database:
the bundle built from the verified download in ``$VOLTERRA_DATA_DIR`` is imported, and every
imported value is compared with the bundle. The development database is never touched.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from alembic import command
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.import_dataset import import_bundle
from app.db.models import Battery, Cycle, Dataset, DatasetFile
from app.db.seed import SYNTHETIC_BATTERY_ID, seed_synthetic_v1
from app.db.session import Database
from tests.support.database import assert_disposable, run_isolated
from tests.support.migrations import alembic_config

DATA_DIR = Path(os.environ.get("VOLTERRA_DATA_DIR", "__unset__"))
BUNDLE = DATA_DIR / "processed" / "nasa-pcoe-battery" / "2022-09-18"

pytestmark = [
    pytest.mark.db,
    pytest.mark.realdata,
    pytest.mark.anyio,
    pytest.mark.skipif(
        not (BUNDLE / "bundle_manifest.json").is_file(),
        reason="no NASA bundle in $VOLTERRA_DATA_DIR/processed (build it with volterra_ml.loaders)",
    ),
]


@pytest.fixture
async def session(empty_database_url: str) -> AsyncIterator[AsyncSession]:
    assert_disposable(empty_database_url)
    run_isolated(lambda: command.upgrade(alembic_config(empty_database_url), "head"))
    database = Database(empty_database_url)
    try:
        async with database.session() as s:
            await seed_synthetic_v1(s)
            yield s
    finally:
        await database.dispose()


async def test_real_nasa_bundle_imports_faithfully(session: AsyncSession) -> None:
    result = await import_bundle(session, BUNDLE, DATA_DIR)
    assert (result.batteries, result.cycles_imported, result.cycles_not_imported) == (34, 2769, 25)

    ds = await session.scalar(select(Dataset).where(Dataset.slug == "nasa-pcoe-battery"))
    assert ds is not None and ds.source == "nasa_pcoe" and ds.status == "ready"
    assert ds.meta["quality_report"]["flag_totals"]["capacity_missing"] == 25
    assert ds.meta["licence"]["status"] == "not_stated"

    batteries = {b.external_id: b for b in await session.scalars(select(Battery))}
    assert len(batteries) == 35  # 34 NASA cells + the synthetic battery
    b5 = batteries["B0005"]
    assert (b5.first_capacity_ah, b5.chemistry, b5.chemistry_basis) == (
        1.8564874208181574,
        None,
        "not_stated",
    )
    assert len(b5.test_conditions["source_files"]) == 1
    assert len(batteries["B0025"].test_conditions["source_files"]) == 2  # duplicate in the archive

    # Every imported cycle equals its Parquet row, bit for bit; nothing else was imported.
    parquet = {
        (r["external_id"], r["cycle_index"]): r
        for r in pq.read_table(BUNDLE / "cycles.parquet").to_pylist()
    }
    ids = {b.id: b.external_id for b in batteries.values()}
    rows = list(
        await session.scalars(
            select(Cycle).where(Cycle.battery_id != batteries[SYNTHETIC_BATTERY_ID].id)
        )
    )
    assert len(rows) == 2769
    for c in rows:
        src = parquet[(ids[c.battery_id], c.cycle_index)]
        assert src["db_eligible"]
        for col in ("capacity_ah", "soh_pct", "temp_mean_c", "voltage_mean_v", "temp_min_c",
                    "temp_max_c", "voltage_min_v", "voltage_max_v", "current_mean_a",
                    "discharge_time_s", "ambient_temp_c", "source_cycle_index"):  # fmt: skip
            assert getattr(c, col) == src[col], (ids[c.battery_id], c.cycle_index, col)
        assert c.quality_flags == json.loads(src["quality_flags_json"])
    zero = [c for c in rows if c.capacity_ah == 0.0]
    assert len(zero) == 19 and all("capacity_zero" in c.quality_flags for c in zero)

    files = int(await session.scalar(select(func.count()).select_from(DatasetFile)) or 0)
    manifest = json.loads((BUNDLE / "bundle_manifest.json").read_text())
    assert files == len(manifest["outputs"]) + 2  # + raw archive + bundle manifest

    again = await import_bundle(session, BUNDLE, DATA_DIR)
    assert again.unchanged
