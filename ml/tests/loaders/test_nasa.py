from __future__ import annotations

import json
import math

import numpy as np
import pyarrow.parquet as pq
import pytest

from tests.loaders.conftest import (
    NasaEnv,
    charge,
    discharge,
    impedance,
    mat_bytes,
    readme,
    standard_groups,
)
from volterra_ml.canonical import bundle as bdl
from volterra_ml.canonical.columns import (
    BATTERY_COLUMNS,
    CYCLE_COLUMNS,
    IMPEDANCE_COLUMNS,
    SAMPLE_COLUMNS,
)
from volterra_ml.loaders import nasa as loader


def build(env: NasaEnv) -> dict:
    return loader.build_bundle(env.raw, env.processed, env.spec)


def table(env: NasaEnv, rel: str) -> list[dict]:
    rows: list[dict] = pq.read_table(env.bundle / rel).to_pylist()
    return rows


def flags(row: dict) -> dict:
    out: dict = json.loads(row["quality_flags_json"])
    return out


def test_bundle_layout_columns_and_provenance(nasa: NasaEnv):
    nasa.install(standard_groups())
    body = build(nasa)
    assert body["schema_version"] == 2
    assert body["dataset"]["is_synthetic"] is False
    assert body["dataset"]["data_provenance"] == "measured"
    assert body["loader"]["name"] == "nasa_pcoe" and body["loader"]["version"] == "1.0.0"
    assert body["inputs"][0]["file"] == "5_Battery_Data_Set.zip"
    paths = {o["path"] for o in body["outputs"]}
    assert paths == {
        "batteries.parquet",
        "cycles.parquet",
        "quality_report.json",
        "samples/B0005_charge.parquet",
        "samples/B0005_discharge.parquet",
        "samples/B0025_charge.parquet",
        "samples/B0025_discharge.parquet",
        "impedance/B0005.parquet",
    }
    for rel, cols in (
        ("batteries.parquet", BATTERY_COLUMNS),
        ("cycles.parquet", CYCLE_COLUMNS),
        ("samples/B0005_discharge.parquet", SAMPLE_COLUMNS),
        ("impedance/B0005.parquet", IMPEDANCE_COLUMNS),
    ):
        assert pq.read_schema(nasa.bundle / rel) == bdl.arrow_schema(cols), rel
    assert bdl.verify_bundle(nasa.bundle)["bundle_checksum"] == body["bundle_checksum"]


def test_batteries_record_reference_basis_and_sources(nasa: NasaEnv):
    nasa.install(standard_groups())
    build(nasa)
    b5, b25 = table(nasa, "batteries.parquet")
    assert b5["external_id"] == b5["source_battery_id"] == "B0005"
    assert b5["chemistry"] is None and b5["chemistry_basis"] == "not_stated"
    assert b5["rated_capacity_ah"] == b5["soh_reference_capacity_ah"] == 2.0
    assert b5["soh_reference"] == "rated_capacity"
    assert b5["first_capacity_ah"] == 1.8564874208181574 and b5["first_capacity_cycle_index"] == 0
    assert (b5["n_discharge_cycles"], b5["n_cycles_with_capacity"]) == (2, 2)
    conditions = json.loads(b5["test_conditions_json"])
    assert conditions["readme_member"] == "1. Group_A.zip/README.txt"
    assert conditions["readme_text"] == readme(["B0005"]).decode("latin-1")  # verbatim
    assert conditions["ambient_temperatures_c"] == [24.0]
    # B0025 is in two groups with identical bytes: one battery, both locations recorded.
    sources = json.loads(b25["source_files_json"])
    assert [s["member"] for s in sources] == [
        "2. Group_B.zip/B0025.mat",
        "3. Group_C.zip/B0025.mat",
    ]
    assert [s["used"] for s in sources] == [True, False]
    assert sources[0]["sha256"] == sources[1]["sha256"]


def test_cycles_keep_source_order_identifiers_and_exact_values(nasa: NasaEnv):
    nasa.install(standard_groups())
    build(nasa)
    rows = [r for r in table(nasa, "cycles.parquet") if r["external_id"] == "B0005"]
    assert [(r["cycle_index"], r["source_cycle_index"]) for r in rows] == [(0, 1), (1, 3)]
    first = rows[0]
    assert first["capacity_ah"] == 1.8564874208181574
    assert first["soh_pct"] == 1.8564874208181574 / 2.0 * 100.0
    v = np.linspace(4.2, 2.7, 5)
    temp = np.linspace(24.5, 34.25, 5)
    assert first["voltage_mean_v"] == float(np.mean(v))
    assert (first["voltage_min_v"], first["voltage_max_v"]) == (2.7, 4.2)
    assert first["temp_mean_c"] == float(np.mean(temp))
    assert first["current_mean_a"] == -2.0
    assert first["discharge_time_s"] == 4 * 9.375
    assert first["ambient_temp_c"] == 24.0 and first["n_samples"] == 5
    assert first["start_time_local"] == "2008-04-02T13:09:17.921000"
    assert flags(first) == {} and first["db_eligible"] is True
    # schema v2: provenance of the cycle; NASA reports no resistance or charge time per cycle
    assert json.loads(first["source_ref_json"]) == {
        "cycle_array_index": 1,
        "member": "1. Group_A.zip/B0005.mat",
    }
    assert first["internal_resistance_ohm"] is None and first["charge_time_s"] is None


def test_samples_are_bit_identical_to_the_source(nasa: NasaEnv):
    nasa.install(standard_groups())
    build(nasa)
    s = [r for r in table(nasa, "samples/B0005_discharge.parquet") if r["source_cycle_index"] == 1]
    assert [r["sample_index"] for r in s] == [0, 1, 2, 3, 4]
    assert [r["voltage_v"] for r in s] == list(np.linspace(4.2, 2.7, 5))
    assert [r["aux_voltage_v"] for r in s] == list(np.linspace(4.1, 2.6, 5))  # Voltage_load
    c = table(nasa, "samples/B0005_charge.parquet")
    assert {r["cycle_type"] for r in c} == {"charge"}
    assert [r["aux_current_a"] for r in c] == [1.49] * 4  # Current_charge


def test_missing_capacity_stays_missing(nasa: NasaEnv):
    cell = mat_bytes("B0050", [discharge(capacity=None), discharge(capacity=1.5)])
    nasa.install({"1. G.zip": {"B0050.mat": cell}})
    build(nasa)
    missing, ok = table(nasa, "cycles.parquet")
    assert missing["capacity_ah"] is None and missing["soh_pct"] is None  # never 0
    assert flags(missing) == {"capacity_missing": "source capacity field is empty"}
    assert missing["db_eligible"] is False
    battery = table(nasa, "batteries.parquet")[0]
    assert battery["first_capacity_ah"] == 1.5 and battery["first_capacity_cycle_index"] == 1
    assert battery["n_cycles_with_capacity"] == 1
    assert (
        battery["test_conditions_json"]
        and json.loads(battery["test_conditions_json"])["readme_text"] is None
    )


def test_zero_and_above_rated_capacity_are_flagged_not_changed(nasa: NasaEnv):
    cell = mat_bytes("B0045", [discharge(capacity=0.0), discharge(capacity=2.4441)])
    nasa.install({"1. G.zip": {"B0045.mat": cell}})
    build(nasa)
    zero, high = table(nasa, "cycles.parquet")
    assert zero["capacity_ah"] == 0.0 and "capacity_zero" in flags(zero) and zero["db_eligible"]
    assert high["capacity_ah"] == 2.4441 and "capacity_above_rated" in flags(high)
    report = json.loads((nasa.bundle / "quality_report.json").read_text())
    assert report["flag_totals"] == {"capacity_above_rated": 1, "capacity_zero": 1}


def test_capacity_jumps_are_flagged_and_kept(nasa: NasaEnv):
    caps = [1.80, 1.70, None, 1.78, 1.77]
    cell = mat_bytes("B0030", [discharge(capacity=c) for c in caps])
    nasa.install({"1. G.zip": {"B0030.mat": cell}})
    build(nasa)
    rows = table(nasa, "cycles.parquet")
    assert [r["capacity_ah"] for r in rows] == caps
    assert [("capacity_jump_up" in flags(r)) for r in rows] == [False, False, False, True, False]
    assert flags(rows[3])["capacity_jump_up"] == "+0.08 Ah vs cycle 1"


def test_bad_samples_are_flagged_and_non_finite_values_become_null(nasa: NasaEnv):
    temp = np.array([25.0, np.nan, 26.0, 27.0, 28.0])
    cell = mat_bytes(
        "B0052",
        [
            discharge(voltage=np.array([0.3, 0.29, 0.28, 0.27, 0.26]), temp=temp),
            discharge(time=np.array([0.0, 5.0, 5.0, 4.0, 9.0])),
            discharge(voltage=np.array([4.6, 4.2, 3.9, 3.0, 2.7])),
        ],
    )
    nasa.install({"1. G.zip": {"B0052.mat": cell}})
    build(nasa)
    low, unordered, high = table(nasa, "cycles.parquet")
    assert flags(low) == {
        "non_finite_values": "1 non-finite sample values",
        "voltage_below_1_5v": "min 0.26 V",
    }
    assert low["temp_mean_c"] == float(np.mean([25.0, 26.0, 27.0, 28.0]))  # finite values only
    assert flags(unordered) == {"time_not_increasing": "time vector is not strictly increasing"}
    assert flags(high) == {"voltage_above_4_5v": "max 4.6 V"}
    s = [r for r in table(nasa, "samples/B0052_discharge.parquet") if r["source_cycle_index"] == 0]
    assert [r["temp_c"] for r in s] == [25.0, None, 26.0, 27.0, 28.0]


def test_unequal_arrays_are_padded_with_nulls_not_zeros(nasa: NasaEnv):
    d = discharge(n=4)
    d["data"]["Temperature_measured"] = np.asarray([[25.0, 26.0]])
    nasa.install({"1. G.zip": {"B0060.mat": mat_bytes("B0060", [d])}})
    build(nasa)
    (cycle,) = table(nasa, "cycles.parquet")
    assert flags(cycle) == {"unequal_array_lengths": "lengths 2,4"}
    s = table(nasa, "samples/B0060_discharge.parquet")
    assert [r["temp_c"] for r in s] == [25.0, 26.0, None, None]


def test_empty_samples_are_flagged(nasa: NasaEnv):
    d = discharge(n=0, capacity=None)
    nasa.install({"1. G.zip": {"B0061.mat": mat_bytes("B0061", [d, charge()])}})
    build(nasa)
    (cycle,) = table(nasa, "cycles.parquet")
    assert flags(cycle)["empty_samples"] == "no samples" and cycle["n_samples"] == 0
    assert cycle["voltage_mean_v"] is None and cycle["discharge_time_s"] is None
    paths = {o["path"] for o in bdl.load_manifest(nasa.bundle)["outputs"]}
    assert "samples/B0061_discharge.parquet" not in paths


def test_complex_impedance_fits_keep_both_parts_and_are_flagged(nasa: NasaEnv):
    cell = mat_bytes("B0049", [impedance(re=0.0499 - 0.0293j, rct=0.0499 + 0.0293j), impedance()])
    nasa.install({"1. G.zip": {"B0049.mat": cell}})
    build(nasa)
    odd, normal = table(nasa, "impedance/B0049.parquet")
    assert (odd["re_ohm"], odd["re_ohm_im"]) == (0.0499, -0.0293)
    assert (odd["rct_ohm"], odd["rct_ohm_im"]) == (0.0499, 0.0293)
    assert set(flags(odd)) == {"re_complex", "rct_complex"}
    assert (normal["re_ohm"], normal["re_ohm_im"], flags(normal)) == (0.0446, None, {})
    assert normal["battery_impedance_re"] == [0.25, 0.5]
    assert normal["battery_impedance_im"] == [-0.125, 0.0625]


def test_complex_values_where_real_values_are_expected_stop_the_loader(nasa: NasaEnv):
    d = discharge()
    d["data"]["Capacity"] = np.asarray([[1.8 + 0.1j]])
    nasa.install({"1. G.zip": {"B0062.mat": mat_bytes("B0062", [d])}})
    with pytest.raises(loader.LoaderError, match="Capacity: complex values"):
        build(nasa)
    assert not nasa.bundle.exists()


def test_duplicate_copies_that_differ_stop_the_loader(nasa: NasaEnv):
    nasa.install(
        {
            "1. A.zip": {"B0025.mat": mat_bytes("B0025", [discharge(capacity=1.9)])},
            "2. B.zip": {"B0025.mat": mat_bytes("B0025", [discharge(capacity=1.8)])},
        }
    )
    with pytest.raises(loader.LoaderError, match="B0025: 2 copies with different content"):
        build(nasa)


@pytest.mark.parametrize(
    ("cycles", "struct", "message"),
    [
        ([{"type": "rest", "ambient": 24.0, "data": {"x": 1.0}}], None, "unknown cycle type"),
        ([discharge()], "Other", "struct 'B0070' not found"),
    ],
)
def test_unexpected_structure_stops_the_loader(nasa: NasaEnv, cycles, struct, message):
    nasa.install({"1. G.zip": {"B0070.mat": mat_bytes("B0070", cycles, struct_name=struct)}})
    with pytest.raises(loader.LoaderError, match=message):
        build(nasa)


def test_raw_data_is_verified_before_conversion(nasa: NasaEnv):
    nasa.install(standard_groups())
    raw = nasa.raw / nasa.spec.slug / nasa.spec.version / "5_Battery_Data_Set.zip"
    raw.chmod(0o644)
    raw.write_bytes(raw.read_bytes() + b"tampered")
    with pytest.raises(loader.LoaderError, match="raw data failed verification"):
        build(nasa)
    assert not nasa.bundle.exists()


def test_rebuild_is_byte_identical_and_replaces_atomically(nasa: NasaEnv):
    nasa.install(standard_groups())
    first = build(nasa)
    files = {
        p.relative_to(nasa.bundle): p.read_bytes() for p in nasa.bundle.rglob("*") if p.is_file()
    }
    second = build(nasa)
    assert second["bundle_checksum"] == first["bundle_checksum"]
    again = {
        p.relative_to(nasa.bundle): p.read_bytes() for p in nasa.bundle.rglob("*") if p.is_file()
    }
    assert again == files
    assert sorted(p.name for p in nasa.bundle.parent.iterdir()) == [nasa.spec.version]


def test_local_time_rejects_malformed_date_vectors():
    assert loader._local_time(np.array([2008, 4, 2, 13, 8, 17.5])) == "2008-04-02T13:08:17.500000"
    assert loader._local_time(np.array([2008, 4, 2])) is None
    assert loader._local_time(np.array([2008, 4.5, 2, 13, 8, 1.0])) is None
    assert loader._local_time(np.array([2008, 4, 2, 13, 8, math.nan])) is None


def test_scalars_and_complex_helpers():
    assert loader._scalar(np.zeros((0, 0))) is None
    assert loader._scalar(np.array([[math.inf]])) is None
    assert loader._maybe_complex(np.zeros((0, 0))) == (None, None)
    assert loader._maybe_complex(np.array([[complex(math.nan, 1)]])) == (None, None)
    assert loader._complex_parts(np.zeros((0, 0))) == (None, None)


def test_iter_cells_matches_the_bundle(nasa: NasaEnv):
    nasa.install(standard_groups())
    archive = nasa.raw / nasa.spec.slug / nasa.spec.version / "5_Battery_Data_Set.zip"
    names = [r.battery["external_id"] for r in loader.iter_cells(archive)]
    assert names == ["B0005", "B0025"]
