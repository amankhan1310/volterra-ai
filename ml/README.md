# ml

The `volterra_ml` package: dataset acquisition, the canonical battery-data schema and dataset
loaders; feature engineering, models, anomaly detectors, simulator calibration and evaluation
follow in later phases ([`../ARCHITECTURE_PLAN.md`](../ARCHITECTURE_PLAN.md) §9).

**Status:** Phase 6 M1–M3. `volterra_ml.acquisition` downloads and verifies the raw datasets;
`volterra_ml.canonical` defines the schema, validation rules and Parquet bundles;
`volterra_ml.loaders` converts NASA PCoE (CALCE and Severson follow in M4). Datasets, processed
bundles and trained models are never committed.

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

## Canonical bundles

```sh
uv run python -m volterra_ml.loaders build nasa-pcoe-battery   # raw -> processed/<slug>/<version>
uv run python -m volterra_ml.loaders verify nasa-pcoe-battery  # re-hash the bundle
```

`build` verifies the raw archive against its manifest and pins first, converts it without
inventing or zeroing any value, flags quality issues instead of removing data, and writes a
deterministic bundle with a checksummed `bundle_manifest.json`. The schema, the validation flags
and the database mapping are documented in
[`../docs/datasets/canonical-schema.md`](../docs/datasets/canonical-schema.md); the column
contract (`volterra_ml/canonical/columns.py`) is shared with the backend importer.

## Checks

```sh
uv run ruff check . && uv run ruff format --check .
uv run mypy            # strict
uv run pytest          # coverage gate 85%; warnings are errors; no test downloads data
```

Tests marked `realdata` compare the loader's output with the downloaded files (every capacity
and every sample, bit for bit); they run when the datasets are in `VOLTERRA_DATA_DIR` and are
skipped otherwise (always in CI).
