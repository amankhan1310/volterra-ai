"""Command line: ``python -m volterra_ml.loaders {build,verify}``.

``build nasa-pcoe-battery`` verifies the raw archive, converts it and writes the bundle to
``<data-dir>/processed/<slug>/<version>/``; ``verify`` re-hashes an existing bundle. The data
directory defaults to ``$VOLTERRA_DATA_DIR`` (see ``volterra_ml.acquisition``).

Exit codes: 0 success, 1 conversion or verification failure, 2 usage error.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import IO, Any

from volterra_ml.acquisition.cli import default_data_dir
from volterra_ml.acquisition.safety import UnsafeDestinationError
from volterra_ml.acquisition.sources import CALCE, NASA_PCOE, SEVERSON, DatasetSpec
from volterra_ml.canonical import bundle as bdl
from volterra_ml.loaders import calce, nasa, severson
from volterra_ml.loaders.common import LoaderError

Builder = Callable[[Path, Path, DatasetSpec], dict[str, Any]]
LOADERS: dict[str, tuple[DatasetSpec, Builder]] = {
    NASA_PCOE.slug: (NASA_PCOE, nasa.build_bundle),
    CALCE.slug: (CALCE, calce.build_bundle),
    SEVERSON.slug: (SEVERSON, severson.build_bundle),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m volterra_ml.loaders")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("build", "convert verified raw data into a canonical bundle"),
        ("verify", "re-hash a bundle against its bundle_manifest.json"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("dataset", metavar="SLUG")
        p.add_argument("--data-dir", type=Path, default=None)
    return parser


def _summary(body: dict[str, Any], out: IO[str]) -> None:
    rows = {o["path"]: o["rows"] for o in body["outputs"]}
    print(f"  bundle_checksum {body['bundle_checksum']}", file=out)
    print(
        f"  batteries {rows.get('batteries.parquet')}, cycles {rows.get('cycles.parquet')}, "
        f"files {len(body['outputs'])}",
        file=out,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    out: IO[str] | None = None,
    err: IO[str] | None = None,
) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    args = _parser().parse_args(argv)
    if args.dataset not in LOADERS:
        print(f"no loader for {args.dataset!r}; available: {', '.join(LOADERS)}", file=err)
        return 2
    spec, build = LOADERS[args.dataset]
    data = args.data_dir or default_data_dir()
    target = bdl.bundle_dir(data / "processed", spec.slug, spec.version)
    try:
        if args.command == "build":
            body = build(data / "raw", data / "processed", spec)
            print(f"{spec.slug}: bundle written to {target}", file=out)
        else:
            body = bdl.verify_bundle(target)
            print(f"{spec.slug}: bundle OK", file=out)
    except (nasa.LoaderError, LoaderError, bdl.BundleError, UnsafeDestinationError) as exc:
        print(f"{spec.slug}: {exc}", file=err)
        return 1
    _summary(body, out)
    return 0
