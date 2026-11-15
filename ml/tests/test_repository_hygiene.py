"""CI guard: datasets and private material can never be committed.

Runs ``git`` against the repository this package lives in; skipped outside a Git checkout.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(
    GIT is None or not (ROOT / ".git").exists(), reason="not a git checkout"
)

#: Raw or processed dataset formats that must never be tracked.
DATA_SUFFIXES = (
    ".mat", ".zip", ".xlsx", ".xls", ".h5", ".hdf5", ".parquet", ".pkl", ".joblib", ".npz",
)  # fmt: skip


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    assert GIT is not None
    return subprocess.run(
        [GIT, "-C", str(ROOT), *args], capture_output=True, text=True, check=False
    )


def test_no_dataset_files_are_tracked():
    tracked = _git("ls-files").stdout.splitlines()
    assert [p for p in tracked if p.startswith(("data/", "artifacts/"))] == []
    assert [p for p in tracked if p.lower().endswith(DATA_SUFFIXES)] == []
    assert [p for p in tracked if Path(p).name == "MANIFEST.json"] == []


@pytest.mark.parametrize(
    "path",
    [
        "data/raw/nasa-pcoe-battery/2022-09-18/MANIFEST.json",
        "data/raw/severson-2019/2019-03-11/2017-05-12_batchdata_updated_struct_errorcorrect.mat",
        "data/processed/x.parquet",
        "research_paper/draft.tex",
        "backend/.env",
    ],
)
def test_private_and_data_paths_are_ignored(path: str):
    assert _git("check-ignore", "--quiet", "--no-index", path).returncode == 0, path
