"""The golden fixtures and the legacy sources they came from are unmodified.

``manifest.json`` (written by legacy/tools/export_golden.js) pins the SHA-256 of every fixture
and of the four legacy prototype files. Python re-verifies it so that pytest alone detects a
hand-edited fixture or a changed prototype.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from tests.support.golden import FIXTURE_NAMES, GOLDEN_DIR, load_golden

REPO_ROOT = GOLDEN_DIR.parents[2]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fixture_files_match_manifest_hashes() -> None:
    pinned = load_golden("manifest")["fixtures_sha256"]
    assert sorted(pinned) == sorted(f"{n}.json" for n in FIXTURE_NAMES if n != "manifest")
    for name, digest in pinned.items():
        assert sha256(GOLDEN_DIR / name) == digest, f"{name} was modified"


def test_legacy_sources_match_manifest_hashes() -> None:
    pinned = load_golden("manifest")["legacy_sources_sha256"]
    assert sorted(pinned) == [
        "legacy/core.js",
        "legacy/index.html",
        "legacy/style.css",
        "legacy/ui.js",
    ]
    for rel, digest in pinned.items():
        assert sha256(REPO_ROOT / rel) == digest, f"{rel} was modified"


def test_known_issue_catalogue_lists_f1_to_f8() -> None:
    assert sorted(load_golden("manifest")["known_issues"]) == [f"F{i}" for i in range(1, 9)]
