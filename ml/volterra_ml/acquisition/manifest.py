"""``MANIFEST.json``: the provenance record kept next to every raw dataset.

Layout (``<data>/raw/<slug>/<version>/``)::

    MANIFEST.json            this record (rewritten atomically as files arrive)
    <file>                   raw files exactly as published, marked read-only

The manifest snapshots the registry metadata (publisher, citation, licence, chemistry) so the
raw folder describes itself, and adds one entry per file: source URL, the URL finally served
after redirects, retrieval time (UTC), retrieval method, size, SHA-256 and the HTTP validators.
It never records local absolute paths or anything about the person who ran the download.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import stat
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from volterra_ml.acquisition.sources import DatasetSpec

SCHEMA_VERSION = 1
MANIFEST_NAME = "MANIFEST.json"
PART_SUFFIX = ".part"
_CHUNK = 1024 * 1024

RetrievalMethod = Literal["http", "local_copy"]


@dataclass(frozen=True)
class FileRecord:
    name: str
    source_url: str
    final_url: str | None
    retrieved_at: str
    retrieval_method: RetrievalMethod
    bytes: int
    sha256: str
    etag: str | None = None
    last_modified: str | None = None


@dataclass
class Manifest:
    dataset: dict[str, Any]
    files: dict[str, FileRecord] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def for_spec(cls, spec: DatasetSpec) -> Manifest:
        return cls(dataset=dataset_block(spec))

    def to_json(self) -> str:
        body = {
            "schema_version": self.schema_version,
            "dataset": self.dataset,
            "files": [dataclasses.asdict(self.files[k]) for k in sorted(self.files)],
        }
        return json.dumps(body, indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Manifest:
        body = json.loads(text)
        if body.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"unsupported manifest schema_version {body.get('schema_version')!r}")
        files = {f["name"]: FileRecord(**f) for f in body["files"]}
        return cls(dataset=body["dataset"], files=files)


def dataset_block(spec: DatasetSpec) -> dict[str, Any]:
    """The registry metadata copied into each manifest (no file pins; those are per file)."""
    return {
        "slug": spec.slug,
        "source": spec.source,
        "name": spec.name,
        "version": spec.version,
        "publisher": spec.publisher,
        "landing_url": spec.landing_url,
        "citation": spec.citation,
        "doi": spec.doi,
        "licence": dataclasses.asdict(spec.licence),
        "chemistry_stated": spec.chemistry_stated,
        "description": spec.description,
        "is_synthetic": spec.is_synthetic,
        "data_provenance": "measured",
    }


def dataset_dir(raw_root: Path, spec: DatasetSpec) -> Path:
    return raw_root / spec.slug / spec.version


def load(directory: Path) -> Manifest | None:
    path = directory / MANIFEST_NAME
    if not path.exists():
        return None
    return Manifest.from_json(path.read_text(encoding="utf-8"))


def save(directory: Path, manifest: Manifest) -> Path:
    """Write ``MANIFEST.json`` atomically (a crash never leaves a half-written manifest)."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / MANIFEST_NAME
    tmp = directory / (MANIFEST_NAME + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(manifest.to_json())
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_read_only(path: Path) -> None:
    """Clear every write bit (on Windows this sets the read-only attribute)."""
    mode = path.stat().st_mode
    path.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def is_read_only(path: Path) -> bool:
    return not os.access(path, os.W_OK)


@dataclass(frozen=True)
class Problem:
    file: str
    message: str


@dataclass(frozen=True)
class VerifyReport:
    slug: str
    directory: Path
    checked: tuple[str, ...]
    problems: tuple[Problem, ...]
    warnings: tuple[Problem, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def verify(raw_root: Path, spec: DatasetSpec, *, require_complete: bool = True) -> VerifyReport:
    """Re-hash every raw file and compare it with its manifest entry and the registry pins.

    Problems (verification fails): missing manifest, missing or altered files, size or SHA-256
    differing from the manifest or from a registry pin, unexpected files, leftover partial
    downloads, a manifest describing another dataset, and (with ``require_complete``) registry
    files that were never downloaded. Warnings: raw files that are not read-only.
    """
    directory = dataset_dir(raw_root, spec)
    problems: list[Problem] = []
    warnings: list[Problem] = []
    checked: list[str] = []

    try:
        manifest = load(directory)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return VerifyReport(
            spec.slug, directory, (), (Problem(MANIFEST_NAME, f"unreadable: {exc}"),), ()
        )
    if manifest is None:
        return VerifyReport(
            spec.slug, directory, (), (Problem(MANIFEST_NAME, "missing; nothing acquired"),), ()
        )

    for key in ("slug", "source", "version"):
        if manifest.dataset.get(key) != getattr(spec, key):
            problems.append(Problem(MANIFEST_NAME, f"dataset {key} does not match the registry"))

    expected = {f.name for f in spec.files}
    for name, record in sorted(manifest.files.items()):
        path = directory / name
        if name not in expected:
            problems.append(Problem(name, "recorded in the manifest but not in the registry"))
            continue
        if not path.is_file():
            problems.append(Problem(name, "recorded in the manifest but missing on disk"))
            continue
        checked.append(name)
        size = path.stat().st_size
        if size != record.bytes:
            problems.append(Problem(name, f"size {size} != manifest {record.bytes}"))
        digest = sha256_file(path)
        if digest != record.sha256:
            problems.append(Problem(name, "SHA-256 differs from the manifest (file changed)"))
        pin = spec.file(name)
        if pin.bytes is not None and record.bytes != pin.bytes:
            problems.append(Problem(name, f"manifest size {record.bytes} != pinned {pin.bytes}"))
        if pin.sha256 is not None and record.sha256 != pin.sha256:
            problems.append(Problem(name, "manifest SHA-256 differs from the registry pin"))
        if not is_read_only(path):
            warnings.append(Problem(name, "not read-only"))

    if require_complete:
        for name in sorted(expected - set(manifest.files)):
            problems.append(Problem(name, "not acquired yet"))

    allowed = set(manifest.files) | {MANIFEST_NAME}
    for entry in sorted(_entries(directory)):
        if entry.endswith(PART_SUFFIX):
            problems.append(Problem(entry, "incomplete download left behind"))
        elif entry not in allowed:
            problems.append(Problem(entry, "unexpected file in the raw folder"))

    return VerifyReport(spec.slug, directory, tuple(checked), tuple(problems), tuple(warnings))


def _entries(directory: Path) -> Iterable[str]:
    return (p.name for p in directory.iterdir()) if directory.is_dir() else ()
