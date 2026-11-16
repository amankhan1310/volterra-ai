"""``python -m volterra_ml.modeling run --data-dir <dir> --out <run-dir>``.

Trains and evaluates the Phase 7 models on the processed bundles under ``<data-dir>/processed``
(or the ``--bundle`` directories given) and writes ``run.json``, ``metrics.json``,
``predictions.json`` and ``models/*.joblib`` to ``<run-dir>``. Reads the bundles only; writes only
inside ``<run-dir>``, which must not exist yet (runs are never overwritten).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from volterra_ml.modeling.experiment import run


def bundles_under(data_dir: Path) -> list[Path]:
    processed = data_dir / "processed"
    return sorted(p for p in processed.glob("*/*") if (p / "bundle_manifest.json").is_file())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m volterra_ml.modeling")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="train and evaluate on the processed bundles")
    r.add_argument("--data-dir", type=Path, help="data directory with processed/<slug>/<version>")
    r.add_argument("--bundle", type=Path, action="append", default=[], help="bundle directory")
    r.add_argument("--out", type=Path, required=True, help="new run directory")
    args = parser.parse_args(argv)
    bundles = list(args.bundle) or (bundles_under(args.data_dir) if args.data_dir else [])
    if not bundles:
        print("no bundles: pass --data-dir or --bundle", file=sys.stderr)
        return 2
    if args.out.exists():
        print(f"{args.out} exists; runs are never overwritten", file=sys.stderr)
        return 2
    result = run(bundles, args.out)
    metrics = result["metrics"]
    for task, summary in metrics.items():
        best = summary["selected"]
        test = summary["models"][best]["test"]
        print(
            f"{task:<24} selected {best:<14} test MAE {test.get('mae', float('nan')):.3f}  "
            f"PICP {test.get('picp', float('nan')):.2f}  "
            f"({summary['batteries']['test']} test batteries)"
        )
    print(f"run {result['run']['run_id']} written to {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
