from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.acquisition.conftest import Server, payload, remote, spec
from volterra_ml.acquisition import manifest as mf


def _acquire(server: Server, raw_root: Path, fetcher, names=("a.zip", "b.zip"), pin=False):
    files = []
    for i, name in enumerate(names):
        data = payload(100 + i)
        server.state.files[name] = data
        files.append(remote(name, server.url(name), data, pin=pin))
    s = spec(tuple(files))
    directory = mf.dataset_dir(raw_root, s)
    m = mf.Manifest.for_spec(s)
    for f in files:
        rec = fetcher.download(f, directory)
        m.files[rec.name] = rec
    mf.save(directory, m)
    return s, directory


def test_manifest_round_trip_and_content(server: Server, raw_root: Path, fetcher):
    s, directory = _acquire(server, raw_root, fetcher)
    text = (directory / "MANIFEST.json").read_text(encoding="utf-8")
    body = json.loads(text)
    assert body["schema_version"] == 1
    ds = body["dataset"]
    assert ds["slug"] == "test-set" and ds["is_synthetic"] is False
    assert ds["data_provenance"] == "measured"
    assert ds["licence"]["redistribution_permitted"] is False
    assert [f["name"] for f in body["files"]] == ["a.zip", "b.zip"]
    for f in body["files"]:
        assert set(f) == {
            "name", "source_url", "final_url", "retrieved_at", "retrieval_method",
            "bytes", "sha256", "etag", "last_modified",
        }  # fmt: skip
        assert f["retrieved_at"].endswith("Z")
    assert str(directory.resolve()) not in text  # no local paths in the record
    assert mf.Manifest.from_json(text).to_json() == text
    assert directory == raw_root / "test-set" / "2000-01-01"


def test_verify_passes_on_untouched_data(server: Server, raw_root: Path, fetcher):
    s, _ = _acquire(server, raw_root, fetcher, pin=True)
    report = mf.verify(raw_root, s)
    assert report.ok and report.checked == ("a.zip", "b.zip") and not report.warnings


def _problems(report: mf.VerifyReport) -> list[str]:
    return [f"{p.file}: {p.message}" for p in report.problems]


def test_verify_detects_a_changed_file(server: Server, raw_root: Path, fetcher):
    s, directory = _acquire(server, raw_root, fetcher)
    target = directory / "a.zip"
    target.chmod(0o644)
    data = bytearray(target.read_bytes())
    data[10] ^= 0xFF  # same size, one flipped byte
    target.write_bytes(bytes(data))
    report = mf.verify(raw_root, s)
    assert _problems(report) == ["a.zip: SHA-256 differs from the manifest (file changed)"]
    assert [w.message for w in report.warnings] == ["not read-only"]


def test_verify_detects_size_change_missing_extra_and_partial(server: Server, raw_root, fetcher):
    s, directory = _acquire(server, raw_root, fetcher)
    (directory / "a.zip").chmod(0o644)
    (directory / "a.zip").write_bytes(b"short")
    (directory / "b.zip").chmod(0o644)
    (directory / "b.zip").unlink()
    (directory / "notes.txt").write_text("x")
    (directory / "c.zip.part").write_bytes(b"x")
    problems = _problems(mf.verify(raw_root, s))
    assert "a.zip: size 5 != manifest 300000" in problems
    assert "b.zip: recorded in the manifest but missing on disk" in problems
    assert "notes.txt: unexpected file in the raw folder" in problems
    assert "c.zip.part: incomplete download left behind" in problems


def test_verify_checks_registry_pins(server: Server, raw_root: Path, fetcher):
    s, directory = _acquire(server, raw_root, fetcher, names=("a.zip",))
    other = payload(999)
    pinned = spec((remote("a.zip", "https://x.invalid/a", other, pin=True),))
    problems = _problems(mf.verify(raw_root, pinned))
    assert "a.zip: manifest size 300000 != pinned 300000" not in problems
    assert "a.zip: manifest SHA-256 differs from the registry pin" in problems
    shorter = spec((remote("a.zip", "https://x.invalid/a", other[:10], pin=True),))
    assert "a.zip: manifest size 300000 != pinned 10" in _problems(mf.verify(raw_root, shorter))


def test_verify_reports_files_not_acquired(server: Server, raw_root: Path, fetcher):
    s, _ = _acquire(server, raw_root, fetcher, names=("a.zip",))
    bigger = spec((*s.files, remote("z.zip", "https://x.invalid/z")))
    assert _problems(mf.verify(raw_root, bigger)) == ["z.zip: not acquired yet"]
    assert mf.verify(raw_root, bigger, require_complete=False).ok


def test_verify_rejects_foreign_or_unknown_records(server: Server, raw_root: Path, fetcher):
    s, directory = _acquire(server, raw_root, fetcher, names=("a.zip", "b.zip"))
    only_a = spec((s.files[0],))
    assert _problems(mf.verify(raw_root, only_a)) == [
        "b.zip: recorded in the manifest but not in the registry"
    ]
    m = mf.load(directory)
    assert m is not None
    m.dataset["version"] = "1999-01-01"
    mf.save(directory, m)
    assert "MANIFEST.json: dataset version does not match the registry" in _problems(
        mf.verify(raw_root, s)
    )


def test_verify_without_or_with_broken_manifest(raw_root: Path):
    s = spec((remote("a.zip", "https://x.invalid/a"),))
    assert _problems(mf.verify(raw_root, s)) == ["MANIFEST.json: missing; nothing acquired"]
    directory = mf.dataset_dir(raw_root, s)
    directory.mkdir(parents=True)
    (directory / "MANIFEST.json").write_text("{not json")
    assert _problems(mf.verify(raw_root, s))[0].startswith("MANIFEST.json: unreadable")
    (directory / "MANIFEST.json").write_text(json.dumps({"schema_version": 99}))
    assert "unsupported manifest schema_version 99" in _problems(mf.verify(raw_root, s))[0]


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path: Path):
    s = spec((remote("a.zip", "https://x.invalid/a"),))
    mf.save(tmp_path, mf.Manifest.for_spec(s))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["MANIFEST.json"]
    assert mf.load(tmp_path / "nowhere") is None


@pytest.mark.parametrize("flag", [0o444, 0o644])
def test_read_only_helpers(tmp_path: Path, flag: int):
    f = tmp_path / "x"
    f.write_bytes(b"1")
    f.chmod(flag)
    assert mf.is_read_only(f) == (flag == 0o444)
    mf.make_read_only(f)
    assert mf.is_read_only(f)
