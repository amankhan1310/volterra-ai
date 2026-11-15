from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from volterra_ml.acquisition.safety import UnsafeDestinationError
from volterra_ml.canonical import bundle as bdl
from volterra_ml.canonical import columns as cols
from volterra_ml.canonical.validate import check_capacity, check_capacity_jumps, check_samples


def test_capacity_jumps_compare_with_the_previous_positive_measured_capacity():
    # rated 2.0 Ah -> threshold 0.05 Ah
    caps = [1.80, 1.79, 1.85, None, 0.0, 1.70, 1.76, 1.761, math.nan, 1.82]
    assert check_capacity_jumps(caps, 2.0) == {
        2: "+0.06 Ah vs cycle 1",  # 1.85 - 1.79
        6: "+0.06 Ah vs cycle 5",  # zero and missing are skipped: 1.76 - 1.70
        9: "+0.059 Ah vs cycle 7",
    }
    assert check_capacity_jumps([1.8, 1.849], 2.0) == {}  # just below 0.05 Ah: not flagged
    assert check_capacity_jumps([1.8, 1.851], 2.0) == {1: "+0.051 Ah vs cycle 0"}
    assert check_capacity_jumps([], 2.0) == {}


# --- the column contract -----------------------------------------------------------------------


def test_contract_identifiers_are_required_and_measurements_nullable():
    for name in ("external_id", "cycle_index", "cycle_type", "source_cycle_index"):
        assert cols.CYCLE_COLUMNS[name][1] is False, name
    measurements = [
        n for n in cols.CYCLE_COLUMNS if n.endswith(("_ah", "_pct", "_c", "_v", "_a", "_s"))
    ]
    assert measurements and all(cols.CYCLE_COLUMNS[n][1] for n in measurements)
    assert set(cols.DB_REQUIRED) <= set(cols.CYCLE_COLUMNS)
    for table in (
        cols.BATTERY_COLUMNS,
        cols.CYCLE_COLUMNS,
        cols.SAMPLE_COLUMNS,
        cols.IMPEDANCE_COLUMNS,
    ):
        schema = bdl.arrow_schema(table)
        assert schema.names == list(table)


# --- validation rules --------------------------------------------------------------------------


def test_clean_samples_have_no_flags():
    assert check_samples([0, 1, 2], [4.2, 3.5, 2.7], [-2, -2, -2], [24, 25, 26]) == {}


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (([0, 1], [4.2], [-2, -2], [24, 25]), {"unequal_array_lengths": "lengths 1,2"}),
        (([], [], [], []), {"empty_samples": "no samples"}),
        (
            ([0, 1], [4.2, math.nan], [-2, -2], [24, 25]),
            {"non_finite_values": "1 non-finite sample values"},
        ),
        (
            ([0, 0], [4.2, 4.1], [-2, -2], [24, 25]),
            {"time_not_increasing": "time vector is not strictly increasing"},
        ),
        (([0, 1], [4.2, 1.49], [-2, -2], [24, 25]), {"voltage_below_1_5v": "min 1.49 V"}),
        (([0, 1], [4.51, 4.2], [-2, -2], [24, 25]), {"voltage_above_4_5v": "max 4.51 V"}),
        (
            ([0, 1], [4.2, 4.1], [-2, -2], [-21, 25]),
            {"temperature_out_of_range": "range -21..25 C"},
        ),
        (
            ([0, 1], [4.2, 4.1], [-2, -2], [24, 80.5]),
            {"temperature_out_of_range": "range 24..80.5 C"},
        ),
    ],
)
def test_sample_rules(args, expected):
    assert check_samples(*args) == expected


def test_thresholds_are_inclusive_at_the_limits():
    assert check_samples([0, 1], [1.5, 4.5], [-2, -2], [-20, 80]) == {}


@pytest.mark.parametrize(
    ("capacity", "expected"),
    [
        (1.8, {}),
        (2.0, {}),
        (None, {"capacity_missing": "source capacity field is empty"}),
        (math.nan, {"capacity_missing": "source capacity is not finite"}),
        (-0.1, {"capacity_negative": "-0.1 Ah"}),
        (0.0, {"capacity_zero": "0 Ah reported"}),
        (2.0353, {"capacity_above_rated": "2.0353 Ah > rated 2"}),
    ],
)
def test_capacity_rules(capacity, expected):
    assert check_capacity(capacity, 2.0) == expected


# --- bundles -----------------------------------------------------------------------------------

SIMPLE = {"a": ("string", False), "b": ("float64", True)}


def make_bundle(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    bdl.write_parquet(bdl.make_table(SIMPLE, [{"a": "x", "b": None}]), work / "t.parquet")
    (work / "note.json").write_text("{}\n")
    final = tmp_path / "processed" / "slug" / "v1"
    bdl.finalize(
        work,
        final,
        dataset={"slug": "slug"},
        loader={"name": "t"},
        inputs=[],
        row_counts={"t.parquet": 1},
    )
    return final


def test_make_table_rejects_nulls_in_required_columns():
    with pytest.raises(bdl.BundleError, match="column 'a' must not contain nulls"):
        bdl.make_table(SIMPLE, [{"a": None, "b": 1.0}])


def test_finalize_and_verify(tmp_path: Path):
    final = make_bundle(tmp_path)
    body = bdl.verify_bundle(final)
    assert [o["path"] for o in body["outputs"]] == ["note.json", "t.parquet"]
    assert [o["rows"] for o in body["outputs"]] == [None, 1]
    assert not (tmp_path / "work").exists()  # moved, not copied


@pytest.mark.parametrize("damage", ["modify", "remove", "extra", "manifest", "schema"])
def test_verify_detects_damage(tmp_path: Path, damage: str):
    final = make_bundle(tmp_path)
    manifest = final / bdl.MANIFEST_NAME
    if damage == "modify":
        (final / "note.json").write_text('{"x": 1}\n')
        match = "note.json: content differs"
    elif damage == "remove":
        (final / "note.json").unlink()
        match = "missing \\['note.json'\\]"
    elif damage == "extra":
        (final / "other.txt").write_text("x")
        match = "extra \\['other.txt'\\]"
    elif damage == "manifest":
        body = json.loads(manifest.read_text())
        body["loader"]["name"] = "changed"
        manifest.write_text(json.dumps(body))
        match = "bundle_checksum does not match"
    else:
        body = json.loads(manifest.read_text())
        body["schema_version"] = 99
        manifest.write_text(json.dumps(body))
        match = "unsupported bundle schema_version 99"
    with pytest.raises(bdl.BundleError, match=match):
        bdl.verify_bundle(final)


def test_missing_manifest(tmp_path: Path):
    with pytest.raises(bdl.BundleError, match="no bundle_manifest.json"):
        bdl.load_manifest(tmp_path)


def test_finalize_replaces_an_existing_bundle_and_leftovers(tmp_path: Path):
    final = make_bundle(tmp_path)
    old = final.with_name(final.name + ".old")
    old.mkdir()  # leftover from an interrupted run
    work = tmp_path / "work2"
    work.mkdir()
    (work / "only.json").write_text("{}\n")
    bdl.finalize(work, final, dataset={}, loader={}, inputs=[], row_counts={})
    assert [p.name for p in final.iterdir()] == ["bundle_manifest.json", "only.json"]
    assert not old.exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_finalize_refuses_a_destination_git_could_track(tmp_path: Path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(UnsafeDestinationError):
        bdl.finalize(
            work, repo / "processed" / "x" / "v", dataset={}, loader={}, inputs=[], row_counts={}
        )
