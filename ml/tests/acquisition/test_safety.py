from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from volterra_ml.acquisition.safety import (
    UnsafeDestinationError,
    _existing_ancestor,
    ensure_git_ignored,
)

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / ".gitignore").write_text("data/\n")
    return repo


@needs_git
def test_ignored_folder_inside_a_repo_is_allowed(tmp_path: Path):
    repo = _repo(tmp_path)
    ensure_git_ignored(repo / "data" / "raw" / "x" / "v1")  # does not exist yet: still checked


@needs_git
def test_tracked_folder_inside_a_repo_is_refused(tmp_path: Path):
    repo = _repo(tmp_path)
    with pytest.raises(UnsafeDestinationError, match="not ignored"):
        ensure_git_ignored(repo / "datasets" / "raw")


def test_outside_any_repo_is_allowed(tmp_path: Path):
    ensure_git_ignored(tmp_path / "anywhere")


def test_without_git_the_check_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)  # the module safety imports
    ensure_git_ignored(tmp_path / "x")


def test_existing_ancestor_falls_back_to_cwd(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Path, "is_dir", lambda _self: False)
    assert _existing_ancestor(Path("/no/such/dir")) == Path.cwd()
