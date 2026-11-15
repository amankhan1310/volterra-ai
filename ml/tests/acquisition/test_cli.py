from __future__ import annotations

import io
import json
import runpy
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.acquisition.conftest import Server, payload, remote, sha, spec
from volterra_ml.acquisition import cli
from volterra_ml.acquisition.fetch import Fetcher
from volterra_ml.acquisition.sources import REGISTRY, DatasetSpec


def run(
    argv: list[str],
    registry: Mapping[str, DatasetSpec] | None = None,
    fetcher: Fetcher | None = None,
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(argv, registry=registry or REGISTRY, fetcher=fetcher, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def two_files(server: Server):
    a, b = payload(1), payload(2)
    server.state.files.update({"a.zip": a, "b.zip": b})
    s = spec(
        (remote("a.zip", server.url("a.zip"), a, pin=True), remote("b.zip", server.url("b.zip")))
    )
    return {s.slug: s}, a, b


def test_list_shows_provenance_of_the_real_registry():
    code, out, _ = run(["list"])
    assert code == 0
    for slug in ("nasa-pcoe-battery", "calce-cs2-cx2", "severson-2019"):
        assert slug in out
    assert out.count("licence permits redistribution: no") == 2  # NASA, CALCE
    assert out.count("licence permits redistribution: yes") == 1  # Severson, CC BY 4.0
    assert out.count("(this project never redistributes data)") == 3
    assert "chemistry (as stated): not stated" in out  # NASA


def test_download_then_verify(two_files, tmp_path: Path, fetcher: Fetcher):
    registry, a, b = two_files
    code, out, err = run(["download", "test-set", "--data-dir", str(tmp_path)], registry, fetcher)
    assert code == 0, err
    assert "test-set/a.zip: acquired, 300,000 bytes" in out
    manifest = json.loads((tmp_path / "raw/test-set/2000-01-01/MANIFEST.json").read_text())
    assert {f["name"]: f["sha256"] for f in manifest["files"]} == {"a.zip": sha(a), "b.zip": sha(b)}

    code, out, _ = run(["verify", "--all", "--data-dir", str(tmp_path)], registry)
    assert code == 0 and "test-set: OK (2 file(s) re-hashed)" in out

    # A second download is a no-op that never touches the raw files.
    code, out, _ = run(["download", "--all", "--data-dir", str(tmp_path)], registry, fetcher)
    assert code == 0 and out.count("already acquired") == 2


def test_verify_fails_after_tampering(two_files, tmp_path: Path, fetcher: Fetcher):
    registry, *_ = two_files
    run(["download", "test-set", "--data-dir", str(tmp_path)], registry, fetcher)
    target = tmp_path / "raw/test-set/2000-01-01/b.zip"
    target.chmod(0o644)
    target.write_bytes(b"changed")
    code, out, _ = run(["verify", "test-set", "--data-dir", str(tmp_path)], registry)
    assert code == 1 and "FAILED" in out and "problem: b.zip: size 7" in out
    assert "warning: b.zip: not read-only" in out


def test_partial_download_and_allow_incomplete(two_files, tmp_path: Path, fetcher: Fetcher):
    registry, *_ = two_files
    args = ["--data-dir", str(tmp_path)]
    code, _, _ = run(["download", "test-set", "--file", "a.zip", *args], registry, fetcher)
    assert code == 0
    assert run(["verify", "test-set", *args], registry)[0] == 1
    assert run(["verify", "test-set", "--allow-incomplete", *args], registry)[0] == 0
    code, _, err = run(["download", "test-set", "--file", "zzz", *args], registry, fetcher)
    assert code == 2 and "none of ['zzz']" in err


def test_failed_file_does_not_stop_the_others(server: Server, tmp_path: Path, fetcher: Fetcher):
    good = payload(5)
    server.state.files["good.zip"] = good
    s = spec(
        (remote("gone.zip", server.url("gone.zip")), remote("good.zip", server.url("good.zip")))
    )
    code, out, err = run(
        ["download", "test-set", "--data-dir", str(tmp_path)], {s.slug: s}, fetcher
    )
    assert code == 1 and "HTTP 404" in err and "good.zip: acquired" in out


def test_unrecorded_existing_file_is_never_overwritten(two_files, tmp_path: Path, fetcher):
    registry, *_ = two_files
    directory = tmp_path / "raw/test-set/2000-01-01"
    directory.mkdir(parents=True)
    (directory / "a.zip").write_bytes(b"someone else's file")
    code, _, err = run(["download", "test-set", "--data-dir", str(tmp_path)], registry, fetcher)
    assert code == 1 and "refusing to overwrite" in err
    assert (directory / "a.zip").read_bytes() == b"someone else's file"


def test_from_dir_copies_hand_downloaded_files(two_files, tmp_path: Path, fetcher: Fetcher):
    registry, a, b = two_files
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "a.zip").write_bytes(a)
    (manual / "b.zip").write_bytes(b)
    code, _, err = run(
        ["download", "test-set", "--from-dir", str(manual), "--data-dir", str(tmp_path / "d")],
        registry,
        fetcher,
    )
    assert code == 0, err
    manifest = json.loads((tmp_path / "d/raw/test-set/2000-01-01/MANIFEST.json").read_text())
    assert {f["retrieval_method"] for f in manifest["files"]} == {"local_copy"}


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_download_refuses_a_destination_git_could_track(two_files, tmp_path: Path, fetcher):
    registry, *_ = two_files
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    code, _, err = run(["download", "test-set", "--data-dir", str(repo / "d")], registry, fetcher)
    assert code == 2 and "refusing to write" in err
    assert not (repo / "d").exists()


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["verify"], "name dataset slugs or pass --all"),
        (["verify", "--all", "nasa-pcoe-battery"], "not both"),
        (["verify", "nope"], "unknown dataset(s): nope"),
    ],
)
def test_usage_errors(argv, message):
    code, _, err = run(argv)
    assert code == 2 and message in err


def test_default_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("VOLTERRA_DATA_DIR", raising=False)
    assert cli.default_data_dir() == cli.REPO_ROOT / "data"
    assert (cli.REPO_ROOT / "ml" / "volterra_ml").is_dir()
    monkeypatch.setenv("VOLTERRA_DATA_DIR", "./elsewhere")
    assert cli.default_data_dir() == cli.REPO_ROOT / "elsewhere"
    monkeypatch.setenv("VOLTERRA_DATA_DIR", str(tmp_path))
    assert cli.default_data_dir() == tmp_path


def test_module_entry_point(monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setattr(sys, "argv", ["volterra_ml.acquisition", "list"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("volterra_ml.acquisition", run_name="__main__")
    assert exit_info.value.code == 0
    assert "severson-2019" in capsys.readouterr().out
