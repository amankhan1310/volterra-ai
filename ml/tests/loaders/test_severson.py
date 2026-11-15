"""Severson loader on generated MATLAB 7.3-style HDF5 batch files (generated values only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pyarrow.parquet as pq
import pytest

from volterra_ml.acquisition import manifest as mf
from volterra_ml.acquisition.fetch import Fetcher
from volterra_ml.acquisition.sources import DatasetSpec, Licence, RemoteFile
from volterra_ml.canonical import bundle as bdl
from volterra_ml.loaders import severson as sv
from volterra_ml.loaders.common import LoaderError

NAMES = ("batch1.mat", "batch2.mat", "batch3.mat")


def cycle_arrays(k: int, capacity: float, n: int = 6) -> dict[str, Any]:
    """One cycle: charge (I > 0) then discharge (I < 0); t in minutes."""
    t = np.arange(n, dtype=float) * 1.5 + k
    i = np.array([4.4] * (n // 2) + [-4.4] * (n - n // 2))
    v = np.linspace(3.5, 2.0, n)
    temp = np.linspace(30.0, 34.0, n)
    qc = np.linspace(0.0, capacity, n)
    qd = np.r_[np.zeros(n // 2), np.linspace(0.1, capacity, n - n // 2)]
    return {"t": t, "V": v, "I": i, "T": temp, "Qc": qc, "Qd": qd,
            "Qdlin": np.zeros(4), "Tdlin": np.zeros(4), "discharge_dQdV": np.zeros(4)}  # fmt: skip


def write_batch(path: Path, entries: list[dict[str, Any]]) -> None:
    """Mimic the MATLAB 7.3 layout: batch/<field> is an (n, 1) array of object references."""
    with h5py.File(path, "w") as f:
        refs = f.create_group("#refs#")
        counter = [0]

        def store(data: Any) -> Any:
            counter[0] += 1
            return refs.create_dataset(f"r{counter[0]}", data=data).ref

        def struct(fields: dict[str, Any]) -> Any:
            counter[0] += 1
            g = refs.create_group(f"g{counter[0]}")
            for k, v in fields.items():
                g.create_dataset(k, data=v)
            return g.ref

        batch = f.create_group("batch")
        n = len(entries)
        cols: dict[str, list[Any]] = {
            k: []
            for k in (
                "summary",
                "cycles",
                "policy_readable",
                "cycle_life",
                "barcode",
                "channel_id",
                "Vdlin",
            )
        }
        for e in entries:
            caps = e["caps"]
            m = len(caps)
            summary = {
                "QDischarge": np.array([caps], dtype=float),
                "QCharge": np.array([caps], dtype=float),
                "IR": np.array([[0.016 + 0.0001 * k for k in range(m)]]),
                "Tavg": np.array([[31.0 + k for k in range(m)]]),
                "Tmin": np.array([[29.0] * m]),
                "Tmax": np.array([[35.0] * m]),
                "chargetime": np.array([[12.0 + k for k in range(m)]]),
                "cycle": np.array([[float(k + 1) for k in range(m)]]),
            }
            per_cycle = [e.get("arrays", cycle_arrays)(k, c) for k, c in enumerate(caps)]
            cyc_group: dict[str, Any] = {}
            for key in per_cycle[0] if per_cycle else ("t", "V", "I", "T", "Qc", "Qd"):
                cyc_group[key] = np.array(
                    [[store(np.atleast_2d(pc[key]))] for pc in per_cycle], dtype=h5py.ref_dtype
                ).reshape(m, 1)
            cols["summary"].append(struct(summary))
            cols["cycles"].append(struct(cyc_group))
            cols["policy_readable"].append(
                store(np.array([[ord(c)] for c in e["policy"]], dtype=np.uint16))
            )
            cols["cycle_life"].append(store(np.array([[e.get("life", float(m + 1))]])))
            cols["barcode"].append(store(np.array([[3707764736, 2, 1, 1, 1, 1]], dtype=np.uint32)))
            cols["channel_id"].append(
                store(np.array([[3707764736, 2, 1, 1, 1, 1]], dtype=np.uint32))
            )
            cols["Vdlin"].append(store(np.zeros((1, 4))))
        for k, v in cols.items():
            batch.create_dataset(k, data=np.array(v, dtype=h5py.ref_dtype).reshape(n, 1))


def entry(caps: list[float], policy: str = "4C(80%)-4C", **kw: Any) -> dict[str, Any]:
    return {"caps": caps, "policy": policy, **kw}


def spec() -> DatasetSpec:
    return DatasetSpec(
        slug="severson-test",
        source="severson",
        name="Severson-style test batches (generated values, not real data)",
        version="2000-01-01",
        publisher="tests",
        landing_url="https://example.invalid/",
        citation="test citation",
        doi=None,
        licence=Licence("cc_by_4_0", "test", True, "credit"),
        chemistry_stated="LiFePO4/graphite",
        description="generated",
        files=tuple(RemoteFile(n, f"https://example.invalid/{n}", "test batch") for n in NAMES),
    )


def install(tmp_path: Path, batches: list[list[dict[str, Any]]]) -> tuple[Path, DatasetSpec]:
    s = spec()
    manual = tmp_path / "manual"
    manual.mkdir(parents=True)
    for name, entries in zip(NAMES, batches, strict=True):
        write_batch(manual / name, entries)
    raw = tmp_path / "raw"
    directory = mf.dataset_dir(raw, s)
    m = mf.Manifest.for_spec(s)
    for f in s.files:
        rec = Fetcher(progress=None).copy_local(f, manual, directory)
        m.files[rec.name] = rec
    mf.save(directory, m)
    return raw, s


JOIN = {"b1c0": "b2c1"}
EXCLUDE = {"b1c1": "does not reach 80% capacity", "b3c0": "noisy channel"}
LIFE = {"b1c0": 2}


def build(tmp_path: Path, batches: list[list[dict[str, Any]]]) -> Path:
    raw, s = install(tmp_path, batches)
    sv.build_bundle(
        raw, tmp_path / "processed", s, continuations=JOIN, excluded=EXCLUDE, continuation_life=LIFE
    )
    return tmp_path / "processed" / s.slug / s.version


def standard() -> list[list[dict[str, Any]]]:
    return [
        [entry([0.0, 1.07, 1.06]), entry([1.09, 1.05], policy="5.4C(40%)-3.6C")],
        [entry([1.08], life=float("nan")), entry([1.04, 1.03])],  # b2c1 continues b1c0
        [entry([1.06, 1.539], policy="4.8C(80%)-4.8C-newstructure")],
    ]


def rows(out: Path, name: str) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = pq.read_table(out / name).to_pylist()
    return data


def test_joined_and_excluded_cells_are_kept_with_provenance(tmp_path: Path):
    out = build(tmp_path, standard())
    bats = {b["external_id"]: b for b in rows(out, "batteries.parquet")}
    assert sorted(bats) == ["b1c0", "b1c1", "b2c0", "b3c0"]  # b2c1 joined into b1c0: 5 entries -> 4
    b0 = json.loads(bats["b1c0"]["test_conditions_json"])
    assert [s["cell"] for s in b0["segments"]] == ["b1c0", "b2c1"]
    assert b0["cycle_life_source"] == 4.0 and b0["cycle_life_source_joined"] == 6.0
    assert "joined_segments" in b0["dataset_flags"]
    assert json.loads(bats["b1c1"]["test_conditions_json"])["dataset_flags"][
        "paper_excluded"
    ].startswith("does not reach 80% capacity")
    assert "paper_excluded" in json.loads(bats["b3c0"]["test_conditions_json"])["dataset_flags"]
    assert (
        json.loads(bats["b2c0"]["test_conditions_json"])["cycle_life_source"] is None
    )  # NaN in source
    assert json.loads(bats["b1c1"]["test_conditions_json"])["charging_policy"] == "5.4C(40%)-3.6C"
    b = bats["b1c0"]
    assert (b["rated_capacity_ah"], b["chemistry_basis"], b["n_discharge_cycles"]) == (
        1.1,
        "stated_by_source",
        5,
    )
    assert (b["first_capacity_ah"], b["first_capacity_cycle_index"]) == (1.07, 1)  # 0 Ah skipped
    assert b["chemistry"] == "LiFePO4/graphite" and len(b["chemistry"]) <= 32  # database limit
    assert b0["cell_model"].startswith("A123 APR18650M1A")
    report = json.loads((out / "quality_report.json").read_text())
    assert report["battery_flags"] == {
        "joined_segments": ["b1c0"],
        "paper_excluded": ["b1c1", "b3c0"],
    }


def test_cycles_use_the_source_summaries_and_discharge_samples(tmp_path: Path):
    out = build(tmp_path, standard())
    cyc = [r for r in rows(out, "cycles.parquet") if r["external_id"] == "b1c0"]
    assert [r["capacity_ah"] for r in cyc] == [0.0, 1.07, 1.06, 1.04, 1.03]
    assert [json.loads(r["source_ref_json"])["cell"] for r in cyc] == ["b1c0"] * 3 + ["b2c1"] * 2
    assert [r["source_cycle_index"] for r in cyc] == [0, 1, 2, 0, 1]
    c = cyc[1]
    assert c["soh_pct"] == 1.07 / 1.1 * 100
    assert (c["temp_mean_c"], c["temp_min_c"], c["temp_max_c"]) == (32.0, 29.0, 35.0)
    assert c["internal_resistance_ohm"] == 0.0161 and c["charge_time_s"] == 13.0 * 60
    v = np.linspace(3.5, 2.0, 6)[3:]
    assert c["voltage_mean_v"] == float(np.mean(v)) and c["current_mean_a"] == -4.4
    assert c["discharge_time_s"] == pytest.approx(3.0 * 60)
    assert c["start_time_local"] is None and c["ambient_temp_c"] is None
    assert json.loads(cyc[0]["quality_flags_json"]) == {"capacity_zero": "0 Ah reported"}
    high = [r for r in rows(out, "cycles.parquet") if r["external_id"] == "b3c0"][1]
    assert "capacity_above_rated" in json.loads(high["quality_flags_json"])
    assert all(r["db_eligible"] for r in cyc)


def test_samples_keep_source_values_and_identify_their_segment(tmp_path: Path):
    out = build(tmp_path, standard())
    s = rows(out, "samples/b1c0_cycle.parquet")
    assert len(s) == 5 * 6
    src = cycle_arrays(1, 1.07)
    seg = [r for r in s if r["canonical_cycle_index"] == 1]
    assert [r["time_min"] for r in seg] == list(src["t"])
    assert [r["time_s"] for r in seg] == list(src["t"] * 60.0)
    assert [r["voltage_v"] for r in seg] == list(src["V"]) and [
        r["discharge_ah"] for r in seg
    ] == list(src["Qd"])
    assert {r["source_cell"] for r in s} == {"b1c0", "b2c1"}
    assert {r["source_member"] for r in s if r["source_cell"] == "b2c1"} == {"batch2.mat"}
    assert pq.read_schema(out / "samples/b1c0_cycle.parquet") == sv.sample_schema()


def test_bundle_is_verifiable_and_deterministic(tmp_path: Path):
    raw, s = install(tmp_path, standard())
    kw: dict[str, Any] = {"continuations": JOIN, "excluded": EXCLUDE, "continuation_life": LIFE}
    a = sv.build_bundle(raw, tmp_path / "p", s, **kw)
    assert (
        bdl.verify_bundle(tmp_path / "p" / s.slug / s.version)["bundle_checksum"]
        == a["bundle_checksum"]
    )
    assert sv.build_bundle(raw, tmp_path / "p", s, **kw)["bundle_checksum"] == a["bundle_checksum"]


def test_empty_cycles_and_structural_problems(tmp_path: Path):
    def empty_first(k: int, c: float) -> dict[str, Any]:
        arrays = cycle_arrays(k, c)
        return {key: (np.zeros((0,)) if k == 0 else val) for key, val in arrays.items()}

    batches = standard()
    batches[0][0]["arrays"] = empty_first
    out = build(tmp_path, batches)
    first = rows(out, "cycles.parquet")[0]
    assert "empty_samples" in json.loads(first["quality_flags_json"]) and first["n_samples"] == 0
    assert first["voltage_mean_v"] is None and first["discharge_time_s"] is None

    raw, s = install(tmp_path / "missing", standard())
    with pytest.raises(LoaderError, match="expected entries not in the batch files: \\['b2c9'\\]"):
        sv.build_bundle(
            raw,
            tmp_path / "p2",
            s,
            continuations={"b1c0": "b2c9"},
            excluded={},
            continuation_life={},
        )


def test_complex_values_stop_the_loader():
    with pytest.raises(LoaderError, match="complex values"):
        sv._real(np.array([1.0 + 1j]), "x")
    assert sv._scalar(np.array([np.nan])) is None and sv._scalar(np.array([1.0, 2.0])) is None


def test_published_tables_match_the_paper_counts():
    assert len(sv.CONTINUATIONS) == 5 and len(sv.PAPER_EXCLUDED) == 11
    assert set(sv.CONTINUATIONS) == set(sv.CONTINUATION_CYCLE_LIFE)
    assert 46 + 48 + 46 - len(sv.CONTINUATIONS) == 135
