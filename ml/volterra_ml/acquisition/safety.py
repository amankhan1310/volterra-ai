"""Guard: raw data may only be written where Git ignores it.

Before anything is written, the target folder is checked. If it lies inside a Git working tree,
Git must report a probe path in it as ignored; otherwise acquisition refuses to run, so a
mistyped ``--data-dir`` can never put datasets under version control. Outside any Git working
tree (or without Git installed) there is nothing to protect and the check passes.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class UnsafeDestinationError(Exception):
    """The destination could be tracked by Git."""


def _existing_ancestor(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.is_dir():
            return candidate
    return Path.cwd()


def ensure_git_ignored(directory: Path) -> None:
    git = shutil.which("git")
    if git is None:
        return
    directory = directory.resolve()
    anchor = _existing_ancestor(directory)
    inside = subprocess.run(
        [git, "-C", str(anchor), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return
    probe = directory / "MANIFEST.json"
    ignored = subprocess.run(
        [git, "-C", str(anchor), "check-ignore", "--quiet", "--no-index", str(probe)],
        capture_output=True,
        check=False,
    )
    if ignored.returncode != 0:
        raise UnsafeDestinationError(
            f"{directory} is inside a Git working tree and not ignored; raw data must never be "
            "committed. Use the git-ignored data/ folder or a folder outside the repository."
        )
