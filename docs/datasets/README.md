# Real battery datasets (Phase 6)

VOLTERRA AI's real experimental data comes from three public sources. Each has a dataset card
that records where it comes from, what it contains, how it must be cited, what its licence
says, and the exact files this project pins.

| Dataset (slug)                              | Publisher                     | Cells              | Chemistry (as stated by the publisher) | Licence                        | Status                       |
| ------------------------------------------- | ----------------------------- | ------------------ | -------------------------------------- | ------------------------------ | ---------------------------- |
| [`nasa-pcoe-battery`](nasa-pcoe-battery.md) | NASA Ames PCoE                | 34                 | not stated ("Li-ion 18650")            | not specified                  | downloaded, verified, pinned |
| [`calce-cs2-cx2`](calce-cs2-cx2.md)         | CALCE, University of Maryland | 12 (6 CS2 + 6 CX2) | LiCoO2 cathode                         | All Rights Reserved + citation | downloaded, verified, pinned |
| [`severson-2019`](severson-2019.md)         | TRI / Stanford / MIT          | 124                | LiFePO4/graphite (A123 APR18650M1A)    | CC BY 4.0                      | downloaded, verified, pinned |

All licence and source statements were checked against the publishers' own pages on
2026-11-15; each card quotes the evidence.

## Rules

- **Real, never invented.** These sources are recorded as real experimental data
  (`is_synthetic = false`, provenance `measured`). The synthetic demo dataset `synthetic-v1`
  stays separate and is always labelled as simulated. Missing measurements stay missing.
- **Raw data is preserved exactly as published.** Files are stored byte for byte and made
  read-only. Their size and SHA-256 are pinned in
  [`ml/volterra_ml/acquisition/sources.py`](../../ml/volterra_ml/acquisition/sources.py) once a
  download has been verified, so a later change at the source is detected instead of accepted.
- **Nothing is redistributed.** Raw and processed data never enter Git or a release, whatever
  the licence would allow (decision D8). `ml/tests/test_repository_hygiene.py` fails CI if a
  dataset file is ever tracked, and the acquisition tool refuses to write anywhere Git could
  track.
- **Cite every source you use** as its card describes.

## Storage layout

Data lives outside the repository, in the folder named by the environment variable
`VOLTERRA_DATA_DIR` (on the development machine `D:\volterra\data`; without the variable, the
repository's git-ignored `data/` folder):

```
<VOLTERRA_DATA_DIR>/raw/<slug>/<version>/
    MANIFEST.json      provenance record (see below)
    <raw files>        exactly as published, read-only
<VOLTERRA_DATA_DIR>/processed/<slug>/<version>/
    bundle_manifest.json, *.parquet, quality_report.json   canonical bundle (Phase 6 M2)
```

Processed bundles follow the [canonical schema](canonical-schema.md); they are derived,
deterministic and re-creatable from the raw files, and are never committed either.

`MANIFEST.json` copies the registry metadata (publisher, citation, licence, chemistry) and adds
one entry per file: source URL, the URL finally served, retrieval time (UTC), retrieval method
(`http` or `local_copy`), size, SHA-256, ETag and Last-Modified. It contains no local paths and
nothing about the person who ran the download.

## Acquisition tool

From `ml/` (standard library only; no dataset is parsed here, that is Phase 6 M2):

```sh
uv run python -m volterra_ml.acquisition list                    # provenance of every dataset
uv run python -m volterra_ml.acquisition download nasa-pcoe-battery calce-cs2-cx2
uv run python -m volterra_ml.acquisition verify --all            # re-hash against manifest + pins
uv run python -m volterra_ml.acquisition download calce-cs2-cx2 --from-dir <folder>  # hand-downloaded files
```

- Downloads resume after an interruption (HTTP `Range`), retry transient failures, and keep
  bytes in `<name>.part` until the size and every pin match; only then is the file renamed and
  made read-only. A file that fails verification is deleted.
- An existing raw file that is not in the manifest is never overwritten or adopted.
- `verify` fails on missing, changed, unexpected or partial files, on a manifest that disagrees
  with the registry, and (unless `--allow-incomplete`) on files not acquired yet. Exit codes:
  0 OK, 1 verification or download failure, 2 usage error or unsafe destination.
