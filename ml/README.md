# ml

The `volterra_ml` package: dataset acquisition and, in later milestones, loaders (NASA PCoE,
CALCE, Severson), validation, feature engineering, models, anomaly detectors, simulator
calibration and evaluation ([`../ARCHITECTURE_PLAN.md`](../ARCHITECTURE_PLAN.md) §9).

**Status:** Phase 6 M1. `volterra_ml.acquisition` downloads, verifies and records the real
datasets; nothing parses them yet (M2). Datasets and trained models are never committed.

## Dataset acquisition

Provenance, licences, citations and the pinned files of each dataset are documented in
[`../docs/datasets/`](../docs/datasets/README.md). Data is written to
`<VOLTERRA_DATA_DIR>/raw/<slug>/<version>/` (default: the repository's git-ignored `data/`).

```sh
uv sync --locked
uv run python -m volterra_ml.acquisition list
uv run python -m volterra_ml.acquisition download nasa-pcoe-battery calce-cs2-cx2
uv run python -m volterra_ml.acquisition verify --all
```

The tool is standard-library only. It resumes interrupted downloads, keeps a file only after its
size and SHA-256 match the registry pins, makes raw files read-only, writes `MANIFEST.json`
atomically, and refuses any destination Git could track.

## Checks

```sh
uv run ruff check . && uv run ruff format --check .
uv run mypy            # strict
uv run pytest          # coverage gate 85%; no test downloads data
```
