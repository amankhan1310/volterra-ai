"""Command line: ``python -m volterra_ml.acquisition {list,download,verify}``.

Run from ``ml/`` with ``uv run python -m volterra_ml.acquisition ...``. Raw data goes to
``<data-dir>/raw/<slug>/<version>/``; ``--data-dir`` defaults to ``$VOLTERRA_DATA_DIR`` or the
repository's git-ignored ``data/`` folder.

Exit codes: 0 success, 1 verification or acquisition failure, 2 usage error or unsafe target.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO

from volterra_ml.acquisition import manifest as mf
from volterra_ml.acquisition.fetch import AcquisitionError, Fetcher
from volterra_ml.acquisition.safety import UnsafeDestinationError, ensure_git_ignored
from volterra_ml.acquisition.sources import REGISTRY, DatasetSpec

REPO_ROOT = Path(__file__).resolve().parents[3]


def default_data_dir() -> Path:
    env = os.environ.get("VOLTERRA_DATA_DIR")
    if env:
        path = Path(env)
        return path if path.is_absolute() else REPO_ROOT / path
    return REPO_ROOT / "data"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m volterra_ml.acquisition",
        description="Acquire and verify the real battery datasets (raw files, never modified).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show the registered datasets and their provenance")

    def targets(p: argparse.ArgumentParser) -> None:
        p.add_argument("datasets", nargs="*", metavar="SLUG", help="dataset slugs")
        p.add_argument("--all", action="store_true", help="every registered dataset")
        p.add_argument("--data-dir", type=Path, default=None, help="data root (raw/ inside)")

    dl = sub.add_parser("download", help="download, verify and record raw files")
    targets(dl)
    dl.add_argument("--file", action="append", dest="files", metavar="NAME", help="only NAME")
    dl.add_argument(
        "--from-dir",
        type=Path,
        default=None,
        help="copy files downloaded by hand from this folder instead of using the network",
    )
    dl.add_argument("--retries", type=int, default=5)

    vf = sub.add_parser("verify", help="re-hash raw files against MANIFEST.json and the pins")
    targets(vf)
    vf.add_argument(
        "--allow-incomplete", action="store_true", help="do not fail on files not acquired yet"
    )
    return parser


def _select(
    args: argparse.Namespace, registry: Mapping[str, DatasetSpec], err: IO[str]
) -> list[DatasetSpec] | None:
    if args.all == bool(args.datasets):
        print("name dataset slugs or pass --all (not both)", file=err)
        return None
    if args.all:
        return list(registry.values())
    unknown = [s for s in args.datasets if s not in registry]
    if unknown:
        print(f"unknown dataset(s): {', '.join(unknown)}; known: {', '.join(registry)}", file=err)
        return None
    return [registry[s] for s in args.datasets]


def cmd_list(registry: Mapping[str, DatasetSpec], out: IO[str]) -> int:
    for spec in registry.values():
        sized = [f.bytes for f in spec.files if f.bytes is not None]
        size = f"{sum(sized) / 1e9:.2f} GB" if len(sized) == len(spec.files) else "size unpinned"
        print(f"{spec.slug}  [{spec.source}]  version {spec.version}", file=out)
        print(f"  {spec.name}", file=out)
        print(f"  files: {len(spec.files)} ({size})", file=out)
        print(f"  chemistry (as stated): {spec.chemistry_stated or 'not stated'}", file=out)
        print(
            f"  licence: {spec.licence.status}; licence permits redistribution: "
            f"{'yes' if spec.licence.redistribution_permitted else 'no'} "
            "(this project never redistributes data)",
            file=out,
        )
        print(f"  cite: {spec.citation}", file=out)
    return 0


def cmd_download(
    args: argparse.Namespace,
    specs: Sequence[DatasetSpec],
    raw_root: Path,
    fetcher: Fetcher,
    out: IO[str],
    err: IO[str],
) -> int:
    failures = 0
    for spec in specs:
        directory = mf.dataset_dir(raw_root, spec)
        try:
            ensure_git_ignored(directory)
        except UnsafeDestinationError as exc:
            print(f"refusing to write: {exc}", file=err)
            return 2
        manifest = mf.load(directory) or mf.Manifest.for_spec(spec)
        manifest.dataset = mf.dataset_block(spec)
        wanted = [f for f in spec.files if not args.files or f.name in args.files]
        if args.files and not wanted:
            print(f"{spec.slug}: none of {args.files} belong to this dataset", file=err)
            return 2
        for remote in wanted:
            target = directory / remote.name
            if remote.name in manifest.files and target.is_file():
                print(
                    f"{spec.slug}/{remote.name}: already acquired (run verify to re-hash)", file=out
                )
                continue
            if target.exists():
                print(
                    f"{spec.slug}/{remote.name}: exists but is not in MANIFEST.json; refusing to "
                    "overwrite or adopt it. Move it away, then use --from-dir.",
                    file=err,
                )
                failures += 1
                continue
            try:
                if args.from_dir is not None:
                    record = fetcher.copy_local(remote, args.from_dir, directory)
                else:
                    record = fetcher.download(remote, directory)
            except AcquisitionError as exc:
                print(f"{spec.slug}: {exc}", file=err)
                failures += 1
                continue
            manifest.files[record.name] = record
            mf.save(directory, manifest)
            print(f"{spec.slug}/{record.name}: acquired, {record.bytes:,} bytes", file=out)
        if not manifest.files:
            continue
        mf.save(directory, manifest)
    return 1 if failures else 0


def cmd_verify(
    args: argparse.Namespace, specs: Sequence[DatasetSpec], raw_root: Path, out: IO[str]
) -> int:
    failed = False
    for spec in specs:
        report = mf.verify(raw_root, spec, require_complete=not args.allow_incomplete)
        status = "OK" if report.ok else "FAILED"
        print(f"{spec.slug}: {status} ({len(report.checked)} file(s) re-hashed)", file=out)
        for p in report.problems:
            print(f"  problem: {p.file}: {p.message}", file=out)
        for w in report.warnings:
            print(f"  warning: {w.file}: {w.message}", file=out)
        failed |= not report.ok
    return 1 if failed else 0


def main(
    argv: Sequence[str] | None = None,
    *,
    registry: Mapping[str, DatasetSpec] = REGISTRY,
    fetcher: Fetcher | None = None,
    out: IO[str] | None = None,
    err: IO[str] | None = None,
) -> int:
    out = out or sys.stdout  # resolved per call, so redirected streams are honoured
    err = err or sys.stderr
    args = _parser().parse_args(argv)
    if args.command == "list":
        return cmd_list(registry, out)
    specs = _select(args, registry, err)
    if specs is None:
        return 2
    raw_root = (args.data_dir or default_data_dir()) / "raw"
    if args.command == "download":
        fetcher = fetcher or Fetcher(retries=args.retries)
        return cmd_download(args, specs, raw_root, fetcher, out, err)
    return cmd_verify(args, specs, raw_root, out)
