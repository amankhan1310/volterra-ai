"""Real-data API (Phase 6 M5) on a disposable database with generated canonical bundles.

Two generated bundles exercise every real-data path without real data (decision D8):

* ``nasa-test``: a NASA-style cell with two imported cycles (too short for the analytics) and
  discharge samples linked by ``source_cycle_index``;
* ``calce-test``: a CALCE-style cell with 230 cycles and **no temperature channel**, samples
  linked by ``canonical_cycle_index``, a battery-level source note, and a Severson-style
  placeholder cycle (capacity 0, no samples) that must stay out of the database.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from alembic import command
from fastapi import FastAPI

from app.db.import_dataset import import_bundle
from app.db.seed import seed_synthetic_v1
from app.db.session import Database
from app.main import create_app
from app.services.analysis import MIN_CYCLES_V1
from tests.support import bundles as b
from tests.support.api import client_for, make_settings
from tests.support.database import assert_disposable, disposable_database, run_isolated
from tests.support.migrations import alembic_config

pytestmark = [pytest.mark.db, pytest.mark.anyio]

CALCE_CYCLES = MIN_CYCLES_V1 + 9  # long enough for the analytics, but no temperature
LONG_CYCLE = 7  # the CALCE-style cycle with many samples (downsampling)
LONG_SAMPLES = 5001
SAMPLE_SCHEMA = {
    "external_id": pa.string(),
    "cycle_type": pa.string(),
    "source_cycle_index": pa.int32(),
    "sample_index": pa.int32(),
    "time_s": pa.float64(),
    "voltage_v": pa.float64(),
    "current_a": pa.float64(),
    "temp_c": pa.float64(),
}


def _samples(rows: list[dict[str, Any]], extra: dict[str, pa.DataType] | None = None) -> pa.Table:
    fields = {**SAMPLE_SCHEMA, **(extra or {})}
    return pa.Table.from_pylist(rows, schema=pa.schema(list(fields.items())))


def _sample(external_id: str, kind: str, src: int, i: int, **extra: Any) -> dict[str, Any]:
    return {
        "external_id": external_id,
        "cycle_type": kind,
        "source_cycle_index": src,
        "sample_index": i,
        "time_s": float(i),
        "voltage_v": 4.2 - i * 1e-4,
        "current_a": -2.0 if kind == "discharge" else 1.5,
        "temp_c": None if "canonical_cycle_index" in extra else 24.0 + i * 0.01,
        **extra,
    }


def nasa_samples(out: Path) -> None:
    """Discharge samples of cycles 0 (source 1) and 2 (source 5), a charge, and a NaN value."""
    rows = [_sample("B0005", "discharge", 1, i) for i in range(4)]
    rows += [_sample("B0005", "discharge", 5, i) for i in range(3)]
    rows[1]["voltage_v"] = float("nan")
    pq.write_table(_samples(rows), out / "samples" / "B0005_discharge.parquet")
    charge = [_sample("B0005", "charge", 1, i) for i in range(2)]
    pq.write_table(_samples(charge), out / "samples" / "B0005_charge.parquet")


def calce_samples(out: Path) -> None:
    extra = {"canonical_cycle_index": pa.int32()}
    rows = [
        _sample("CS2_T", "charge" if i < 2 else "discharge", 3, i, canonical_cycle_index=c)
        for c in range(3)
        for i in range(5)
    ]
    rows += [
        _sample("CS2_T", "discharge", 9, i, canonical_cycle_index=LONG_CYCLE)
        for i in range(LONG_SAMPLES)
    ]
    rows.append(_sample("CS2_T", "charge", 10, 0, canonical_cycle_index=None))  # no discharge
    (out / "samples" / "B0005_discharge.parquet").unlink()  # the default placeholder file
    pq.write_table(_samples(rows, extra), out / "samples" / "CS2_T_cycle.parquet")


def calce_bundle(data_dir: Path) -> Path:
    rated = 1.1
    no_temp = {"temp_mean_c": None, "temp_min_c": None, "temp_max_c": None, "ambient_temp_c": None}
    cycles = [
        b.cycle(
            "CS2_T",
            i,
            capacity=1.05,
            soh_pct=1.05 / rated * 100.0,
            db_eligible=False,
            quality_flags_json=json.dumps({"capacity_jump_up": "x"} if i == 3 else {}),
            **no_temp,
        )
        for i in range(CALCE_CYCLES)
    ]
    cycles.append(  # Severson-style placeholder: capacity 0 and not a single sample
        b.cycle(
            "CS2_T",
            CALCE_CYCLES,
            capacity=0.0,
            soh_pct=0.0,
            voltage_mean_v=None,
            voltage_min_v=None,
            voltage_max_v=None,
            n_samples=0,
            db_eligible=False,
            quality_flags_json=json.dumps({"capacity_zero": "x", "empty_samples": "x"}),
            **no_temp,
        )
    )
    conditions = {"dataset_flags": {"earlier_history_not_converted": "3 text exports"}}
    battery = b.battery(
        "CS2_T",
        rated_capacity_ah=rated,
        soh_reference_capacity_ah=rated,
        test_conditions_json=json.dumps(conditions),
    )
    dataset = b.dataset_block(slug="calce-test", source="calce", name="CALCE-style (generated)")
    return b.write_bundle(
        data_dir, batteries=[battery], cycles=cycles, dataset=dataset, tamper=calce_samples
    )


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("data")


@pytest.fixture(scope="module")
def database_url(admin_database_url: str, data_dir: Path) -> Iterator[str]:
    """Synthetic-v1 plus both generated bundles, imported once for the module."""
    with disposable_database(admin_database_url) as url:
        assert_disposable(url)
        run_isolated(lambda: command.upgrade(alembic_config(url), "head"))

        async def load() -> list[Any]:
            database = Database(url)
            try:
                async with database.session() as session:
                    await seed_synthetic_v1(session)
                results = []
                for bundle in (
                    b.write_bundle(data_dir, tamper=nasa_samples),
                    calce_bundle(data_dir),
                ):
                    async with database.session() as session:
                        results.append(await import_bundle(session, bundle, data_dir))
                return results
            finally:
                await database.dispose()

        results = run_isolated(lambda: __import__("asyncio").run(load()))
        assert [(r.slug, r.cycles_imported, r.cycles_not_imported) for r in results] == [
            ("nasa-test", 2, 1),  # the cycle without capacity stays in Parquet
            ("calce-test", CALCE_CYCLES, 1),  # imported without temperature; placeholder kept out
        ]
        yield url


@pytest.fixture
async def client(database_url: str, data_dir: Path) -> AsyncIterator[httpx.AsyncClient]:
    database = Database(database_url)
    app: FastAPI = create_app(make_settings(data_dir=data_dir), database=database)
    try:
        async with client_for(app) as c:
            yield c
    finally:
        await database.dispose()


async def batteries(client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
    items = (await client.get("/api/v1/batteries")).json()["items"]
    return {i["external_id"]: i for i in items}


async def test_synthetic_comes_first_and_availability_explains_every_battery(client) -> None:
    items = (await client.get("/api/v1/batteries")).json()["items"]
    assert [(i["external_id"], i["dataset"]) for i in items] == [
        ("SYN-001", "synthetic-v1"),
        ("CS2_T", "calce-test"),
        ("B0005", "nasa-test"),
    ]
    by_id = {i["external_id"]: i for i in items}
    assert by_id["SYN-001"]["analysis"] == {
        "available": True,
        "reason": None,
        "message": None,
        "min_cycles": MIN_CYCLES_V1,
    }
    calce = by_id["CS2_T"]
    assert (calce["data_provenance"], calce["is_synthetic"]) == ("measured", False)
    assert (calce["cycle_count"], calce["incomplete_cycle_count"]) == (CALCE_CYCLES, CALCE_CYCLES)
    assert calce["flagged_cycle_count"] == 1
    assert calce["flags"] == [{"code": "earlier_history_not_converted", "detail": "3 text exports"}]
    assert calce["analysis"]["reason"] == "missing_measurement"
    assert f"{CALCE_CYCLES} of {CALCE_CYCLES} cycles" in calce["analysis"]["message"]
    nasa = by_id["B0005"]
    assert (nasa["cycle_count"], nasa["incomplete_cycle_count"], nasa["flags"]) == (2, 0, [])
    assert nasa["analysis"]["available"] is False
    assert nasa["analysis"]["reason"] == "insufficient_data"
    single = (await client.get(f"/api/v1/batteries/{calce['id']}")).json()
    assert single == calce
    datasets = (await client.get("/api/v1/datasets")).json()["items"]
    assert [d["slug"] for d in datasets] == ["synthetic-v1", "calce-test", "nasa-test"]


@pytest.mark.parametrize(
    ("battery", "code"), [("CS2_T", "missing_measurement"), ("B0005", "insufficient_data")]
)
@pytest.mark.parametrize(
    "path",
    ["summary", "forecast", "backtest", "insights", "anomalies", "simulator", "advisor",
     "summary?algorithm=v2", "anomalies?algorithm=v2"],
)  # fmt: skip
async def test_analytics_refuse_with_the_agreed_error(client, battery, code, path) -> None:
    ids = await batteries(client)
    response = await client.get(f"/api/v1/batteries/{ids[battery]['id']}/{path}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


async def test_simulate_refuses_missing_temperature(client) -> None:
    ids = await batteries(client)
    params = {
        "temp_c": 25,
        "c_rate": 1,
        "dod_pct": 80,
        "horizon_cycles": 600,
        "start_soh_pct": 100,
        "eol_pct": 80,
    }
    response = await client.post(
        f"/api/v1/batteries/{ids['CS2_T']['id']}/simulate", json={"params": params}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "missing_measurement"


async def test_cycles_keep_missing_values_null_and_show_flags(client) -> None:
    ids = await batteries(client)
    calce = (await client.get(f"/api/v1/batteries/{ids['CS2_T']['id']}/cycles")).json()
    assert len(calce["items"]) == CALCE_CYCLES
    first = calce["items"][3]
    assert (first["cycle"], first["temp_c"], first["voltage_v"]) == (3, None, 3.5)
    assert first["quality_flags"] == ["capacity_jump_up"]
    assert (first["internal_resistance_ohm"], first["charge_time_s"]) == (0.0185, None)
    assert calce["provenance"] == "measured"
    assert calce["context"]["note"] and "not validated on real cells" in calce["context"]["note"]
    assert calce["units"]["internal_resistance_ohm"] == "Ω"
    nasa = (await client.get(f"/api/v1/batteries/{ids['B0005']['id']}/cycles")).json()
    assert [(c["cycle"], c["capacity_ah"], c["temp_c"]) for c in nasa["items"]] == [
        (0, 1.85, 30.5),
        (2, 1.8, 30.5),
    ]


async def test_twin_works_for_short_cells_and_refuses_missing_measurements(client) -> None:
    ids = await batteries(client)
    nasa = await client.get(f"/api/v1/batteries/{ids['B0005']['id']}/twin", params={"cycle": 2})
    assert nasa.status_code == 200
    assert nasa.json()["pack"]["temperature"] == {
        "value": 30.5,
        "unit": "°C",
        "provenance": "measured",
    }
    calce = await client.get(f"/api/v1/batteries/{ids['CS2_T']['id']}/twin")
    assert calce.status_code == 422 and calce.json()["error"]["code"] == "missing_measurement"
    gone = await client.get(f"/api/v1/batteries/{ids['B0005']['id']}/twin", params={"cycle": 1})
    assert gone.json()["error"]["message"] == "Cycle 1 not found (cycles 0..2)"


async def test_nasa_samples_follow_the_source_cycle_index(client) -> None:
    ids = await batteries(client)
    url = f"/api/v1/batteries/{ids['B0005']['id']}/cycles/0/samples"
    body = (await client.get(url)).json()
    assert (body["cycle"], body["cycle_types"], body["total_samples"]) == (0, ["discharge"], 4)
    assert (body["returned_samples"], body["downsampled"]) == (4, False)
    assert [s["time_s"] for s in body["items"]] == [0.0, 1.0, 2.0, 3.0]
    assert body["items"][1]["voltage_v"] is None  # NaN in the source is returned as null
    assert body["items"][0] == {
        "position": 0,
        "time_s": 0.0,
        "voltage_v": 4.2,
        "current_a": -2.0,
        "temp_c": 24.0,
    }
    assert body["units"] == {"time_s": "s", "voltage_v": "V", "current_a": "A", "temp_c": "°C"}
    second = (await client.get(f"/api/v1/batteries/{ids['B0005']['id']}/cycles/2/samples")).json()
    assert second["total_samples"] == 3


async def test_calce_samples_are_the_whole_cycle_and_downsampled_deterministically(client) -> None:
    ids = await batteries(client)
    base = f"/api/v1/batteries/{ids['CS2_T']['id']}/cycles"
    short = (await client.get(f"{base}/1/samples")).json()
    assert (short["cycle_types"], short["total_samples"]) == (["charge", "discharge"], 5)
    assert [s["temp_c"] for s in short["items"]] == [None] * 5
    long_url = f"{base}/{LONG_CYCLE}/samples"
    long = (await client.get(long_url, params={"max_points": 1000})).json()
    assert (long["total_samples"], long["returned_samples"], long["downsampled"]) == (
        LONG_SAMPLES,
        1000,
        True,
    )
    positions = [s["position"] for s in long["items"]]
    assert positions[0] == 0 and positions[-1] == LONG_SAMPLES - 1
    assert positions == sorted(set(positions))
    assert all(s["time_s"] == float(s["position"]) for s in long["items"])  # values copied
    assert (await client.get(long_url, params={"max_points": 1000})).json() == long
    default = (await client.get(long_url)).json()
    assert default["returned_samples"] == 2000
    no_data = (await client.get(f"{base}/{CALCE_CYCLES - 1}/samples")).json()
    assert (no_data["total_samples"], no_data["items"]) == (0, [])


async def test_sample_errors(client, database_url: str) -> None:
    ids = await batteries(client)
    synthetic = await client.get(f"/api/v1/batteries/{ids['SYN-001']['id']}/cycles/0/samples")
    assert synthetic.status_code == 422 and synthetic.json()["error"]["code"] == "no_samples"
    base = f"/api/v1/batteries/{ids['CS2_T']['id']}/cycles"
    missing = await client.get(f"{base}/{CALCE_CYCLES}/samples")  # the placeholder: not imported
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "cycle_not_found"
    for bad in (1, 20001):
        response = await client.get(f"{base}/0/samples", params={"max_points": bad})
        assert response.status_code == 422

    database = Database(database_url)
    try:
        app = create_app(make_settings(), database=database)  # no VOLTERRA_DATA_DIR
        async with client_for(app) as c:
            unconfigured = await c.get(f"{base}/0/samples")
        app = create_app(make_settings(data_dir=Path("missing-data-dir")), database=database)
        async with client_for(app) as c:
            absent = await c.get(f"{base}/0/samples")
    finally:
        await database.dispose()
    for response in (unconfigured, absent):
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "samples_unavailable"
        assert "missing-data-dir" not in response.text  # no server paths in errors
