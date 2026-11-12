"""Idempotent seed of the ``synthetic-v1`` dataset (legacy prototype data, Phase 2 generator).

Run against the database in ``DATABASE_URL``::

    uv run python -m app.db.seed

Seeding twice is a no-op. If ``synthetic-v1`` already exists with *different* cycle data the
seed refuses to overwrite it. The injected-anomaly ground truth is stored in ``datasets.meta``
(internal; not exposed by public dataset endpoints).
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.synthetic import SYNTHETIC_V1, CycleRecord, generate_synthetic_v1
from app.db.models import Battery, Cycle, Dataset

SYNTHETIC_BATTERY_ID = "SYN-001"


class SeedConflictError(RuntimeError):
    """The dataset exists with different data; refusing to overwrite it."""


@dataclass(frozen=True)
class SeedResult:
    dataset_id: uuid.UUID
    battery_id: uuid.UUID
    cycles: int
    created: bool


def cycles_checksum(records: Sequence[CycleRecord]) -> str:
    """SHA-256 over the exact binary values of every cycle (``float.hex``)."""
    digest = hashlib.sha256()
    for r in records:
        line = (
            f"{r.cycle},{r.capacity_ah.hex()},{r.soh_pct.hex()},"
            f"{r.temp_c.hex()},{r.voltage_v.hex()}\n"
        )
        digest.update(line.encode("ascii"))
    return digest.hexdigest()


def synthetic_ground_truth() -> dict[str, Any]:
    """Injected anomalies of synthetic-v1 (same structure as the golden ``dataset.json``)."""
    cfg = SYNTHETIC_V1
    return {
        "temp_spike": {"cycles": list(cfg.temp_spike_cycles), "delta_c": cfg.temp_spike_c},
        "voltage_dip": {"cycles": list(cfg.voltage_dip_cycles), "delta_v": -cfg.voltage_dip_v},
        "capacity_step": {"cycles": [], "note": "none injected"},
    }


def synthetic_dataset_values(checksum: str) -> dict[str, Any]:
    cfg = SYNTHETIC_V1
    return {
        "slug": cfg.dataset_id,
        "name": "Synthetic battery dataset v1",
        "source": "synthetic",
        "version": "1",
        "licence": "Generated data (no third-party content)",
        "citation": None,
        "description": (
            f"Seeded synthetic {cfg.nominal_capacity_ah} Ah cell, {cfg.n_cycles} cycles, "
            f"reproduced from the legacy prototype (mulberry32 seed {cfg.seed}). Simulated, "
            "not measured from any vehicle."
        ),
        "status": "ready",
        "checksum": checksum,
        "meta": {
            "generator": {"prng": "mulberry32", "seed": cfg.seed, "n_cycles": cfg.n_cycles},
            "injected_anomalies": synthetic_ground_truth(),
        },
    }


def synthetic_battery_values(checksum: str) -> dict[str, Any]:
    return {
        "external_id": SYNTHETIC_BATTERY_ID,
        "chemistry": None,
        "form_factor": None,
        "nominal_capacity_ah": SYNTHETIC_V1.nominal_capacity_ah,
        "nominal_voltage_v": None,
        "eol_threshold_pct": 80.0,
        "test_conditions": {},
        "is_synthetic": True,
        "cycles_checksum": checksum,
    }


async def seed_synthetic_v1(session: AsyncSession) -> SeedResult:
    records = generate_synthetic_v1()
    checksum = cycles_checksum(records)
    slug = SYNTHETIC_V1.dataset_id

    dataset = await session.scalar(select(Dataset).where(Dataset.slug == slug))
    if dataset is None:
        dataset = Dataset(**synthetic_dataset_values(checksum))
        session.add(dataset)
        await session.flush()

    battery = await session.scalar(
        select(Battery).where(
            Battery.dataset_id == dataset.id, Battery.external_id == SYNTHETIC_BATTERY_ID
        )
    )
    if battery is not None:
        if battery.cycles_checksum != checksum:
            raise SeedConflictError(f"{slug} exists with different cycle data; not overwriting")
        count = await session.scalar(
            select(func.count(Cycle.id)).where(Cycle.battery_id == battery.id)
        )
        await session.commit()
        return SeedResult(dataset.id, battery.id, int(count or 0), created=False)

    battery = Battery(dataset_id=dataset.id, **synthetic_battery_values(checksum))
    session.add(battery)
    await session.flush()
    await session.execute(
        insert(Cycle),
        [
            {
                "battery_id": battery.id,
                "cycle_index": r.cycle,
                "cycle_type": "discharge",
                "capacity_ah": r.capacity_ah,
                "soh_pct": r.soh_pct,
                "temp_mean_c": r.temp_c,
                "voltage_mean_v": r.voltage_v,
            }
            for r in records
        ],
    )
    await session.commit()
    return SeedResult(dataset.id, battery.id, len(records), created=True)


async def _main() -> int:
    from app.core.config import get_settings
    from app.db.session import Database

    dsn = get_settings().database_dsn()
    if not dsn:
        print("DATABASE_URL is not configured (see backend/.env.example)", file=sys.stderr)
        return 1
    database = Database(dsn)
    try:
        async with database.session() as session:
            result = await seed_synthetic_v1(session)
    finally:
        await database.dispose()
    action = "Seeded" if result.created else "Already seeded"
    print(f"{action} synthetic-v1: battery {result.battery_id} with {result.cycles} cycles")
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper, exercised manually and in CI
    sys.exit(asyncio.run(_main()))
