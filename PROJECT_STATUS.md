# Project status

Progress against the phases in [`ARCHITECTURE_PLAN.md`](ARCHITECTURE_PLAN.md) §10.

| Phase                           | Status      |
| ------------------------------- | ----------- |
| 0. Foundations                  | ✅ Complete |
| 1. Golden fixtures              | ✅ Complete |
| 2. Analytics parity in Python   | ✅ Complete |
| 3. DB + API (parity)            | ✅ Complete |
| 4. React parity                 | ⏳ Next     |
| 5. Correctness fixes (F1–F8)    | Not started |
| 6. Real data                    | Not started |
| 7. ML models                    | Not started |
| 8. Calibrated simulator         | Not started |
| 9. Reports, notifications, auth | Not started |
| 10. Hardening                   | Not started |

## Milestone: Phase 0 — Foundations (2026-11-12)

Branch: `chore/repo-foundation` (PR into `main`).

Delivered:

- `ARCHITECTURE_PLAN.md`: technical assessment and migration plan.
- Repo hygiene: `.gitignore`, `.gitattributes` (LF), `.editorconfig`, `.env.example`
  (placeholders only), `.prettierignore`, `README.md`.
- Prototype moved to `legacy/` with `git mv`. All four files are 100% renames with identical
  blobs, and history follows the rename. Verified: relative asset paths resolve when serving
  `legacy/`, and `core.js` produces identical outputs (SOH 86.09%, RUL 112.7 cycles).
- Empty scaffolds: `backend/` (`app`, `tests`), `ml/` (`volterra_ml`, `tests`), `frontend/`
  (README only), shared `ruff.toml`.
- CI: `.github/workflows/lint.yml` runs ruff check, ruff format, prettier, and a legacy JS
  syntax check.
- `CLAUDE.md`: assistant guidance.

Checks (local): `ruff check .` passed · `ruff format --check .` passed ·
`prettier --check .` passed · `node --check` legacy scripts passed.

Decisions taken (plan Appendix A): legacy moved to `legacy/`; Postgres-backed job queue;
Python 3.11+/Node 20+ recommended (3.10/18 minimum); auth deferred to Phase 9; NASA PCoE as the
first dataset; deep learning optional; deployment target to be decided before Phase 10.

## Milestone: Phase 1 — Golden reference fixtures (2026-11-12)

Branch: `test/legacy-golden` (PR into `main`). Phase 0 was merged as PR #1 (`69ae442`).

Delivered:

- `legacy/tools/export_golden.js`: runs the **unmodified** `core.js` and `ui.js` in a Node `vm`
  sandbox with a DOM stub, then exports the prototype's own values and functions. It has
  built-in sanity checks (recent fit equals `F`, backtest MAE equals `BT.mae`, detector flags
  equal `AN`) and a `--check` mode.
- `backend/tests/golden/`: 11 deterministic JSON fixtures for dataset `synthetic-v1`:

  - `manifest`, `dataset`, `prng`, `regression`, `soh_rul`, `backtest`, `anomalies`
  - `simulator`, `advisor`, `insights`, `display_rules`

  Each records inputs, expected outputs, units, provenance and legacy source line references.
  A README covers regenerating, validating and the numerical tolerances for the Python port.

- `legacy/tools/export_golden.test.js`: 9 tests using Node's built-in test runner.
- CI: `.github/workflows/golden.yml` runs the tests and `--check` on Node 18, 20 and 22.
- `.prettierignore` now excludes only the four frozen prototype files (so `legacy/tools/` is
  format-checked) and the generated fixture JSON.

Verification (local):

- Exporter tests 9/9 passed. `--check` passed: two independent runs were byte-identical and
  matched the committed files.
- Fixtures were byte-identical under Node 18.20.8, 20.20.2 and 22.23.5.
- Negative checks: a one-ULP change to a fixture value and an unexpected extra fixture file
  were both detected.
- The legacy sources are unchanged (same SHA-256 before and after).
- ruff, prettier and `node --check` all passed.

Known defects F1–F8 are captured as-is (see `backend/tests/golden/README.md`). F5 is dormant in
this dataset: fade really did accelerate, so the unconditional text happens to be true.

## Milestone: Phase 2 — Python analytics parity (2026-11-12)

Branch: `feat/backend-analytics-parity` (PR into `main`). Phase 1 was merged as PR #2
(`cf2ce00`).

Delivered, in `backend/app/analytics/` (standard library only, strict typing):

- `jsmath`: JavaScript number semantics:
  - left-to-right summation
  - `Math.round` and `toFixed`
  - division by zero
  - NaN propagation in `max`/`min`
  - JavaScript truthiness
  - 32-bit integer operations
- The **v1** algorithms, each reproducing the prototype exactly, including defects F1–F8:
  - `prng` (mulberry32), `synthetic` (synthetic-v1), `stats` (`lin`, `median`)
  - `health` (SOH, fade, RUL, interval, forecast, gauge), `backtest`, `anomalies` (robust z v1)
  - `simulator`, `advisor` (`ui.js` semantics), `insights` (structured), `display`
  - `legacy_v1.analyze()`: one end-to-end, immutable analysis result
- Tooling:
  - `uv` lockfile, restricted by `exclude-newer` to releases at least two weeks old
  - pytest, pytest-cov, hypothesis, strict mypy, ruff
  - CI workflow `.github/workflows/backend.yml` on Python 3.10 and 3.12

Tests (`backend/tests/`):

- **Harness:** `support/golden.py` compares exactly by default. The 1e-12 tolerance applies only
  on declared paths (fields derived from `sin`, `exp` or `pow`), integers are always exact, and
  NaN/±Infinity markers are handled. A tolerance-usage report prints after every run.
- **Parity:** one test per fixture, plus an end-to-end `analyze()` test.
- **Safety nets:**
  - fixture and legacy checksum verification
  - margin guards (no discrete result can flip from a last-bit difference)
  - a source-hygiene scan (no `sum()`, `round()` or `fsum`; standard-library imports only)
  - F1–F8 correct-behaviour tests marked strict xfail

Results (Windows Python 3.10.11 and 3.12.15):

- 233 passed, 8 xfailed (F1–F8, strict). Branch coverage is 100%; the gate is 85%.
- mypy (strict) reports no issues in 46 files. ruff and prettier are clean.
- Parity: 6,196 numeric comparisons, 6,192 bit-exact. 4 needed the 1e-12 tolerance (of 2,110
  where it was allowed), at most 2 ULP. All four come from the simulator's `exp(-1.2)` at 5 °C.
  Every integer and discrete output is exact. The dataset is fully bit-exact, temperature
  included.
- The Phase 1 golden checks still pass. The 11 fixtures and 4 legacy files are unchanged.

Decisions applied:

- v1 is permanent. Phase 5 fixes will be separate v2 implementations with their own expected
  values, and the golden fixtures are never modified.
- The synthetic generator stays in the backend until Phase 6.
- CSS colours and advisor bar geometry are left for the frontend.

## Milestone: Phase 3 — PostgreSQL, migrations and parity API (2026-11-12)

Branch: `feat/backend-db-api` (PR into `main`). Phase 2 was merged as PR #3 (`f6bd10c`).

Delivered:

- **Database:** PostgreSQL 16 schema with four tables (`datasets`, `batteries`, `cycles`,
  `scenarios`). Numeric values are `DOUBLE PRECISION`, and SOH is stored as generated.
  - Async SQLAlchemy 2 with asyncpg.
  - Alembic migration `0001`, which can be rolled back. `alembic check` reports no differences
    between models and database.
  - Seed for `synthetic-v1` (`python -m app.db.seed`). Running it twice changes nothing, and it
    refuses to overwrite different data. Synthetic ground truth is stored only in internal
    metadata.
- **API (`/api/v1`, 17 paths):**
  - `health`, datasets, batteries, cycles
  - `summary`, `forecast`, `backtest`, `insights`, `anomalies`, `twin`
  - `simulator`, `simulate`, `advisor`
  - saved-scenario create, read, update, delete
  - Every analytical response carries `context` and per-value provenance. NaN and Infinity
    are written as strings. A missing database gives 503; unknown ids, 404; invalid input, 422.
    All errors use one envelope.
- **Behaviour preserved:** the API calls the unchanged `legacy_v1.analyze()` in a worker thread,
  through a bounded LRU cache. The cache key includes a checksum of the loaded data, so any data
  change invalidates it. Mappers only copy values, and a static scan enforces that.
  `display.temperature_band()` was added as a separate module (`analytics/twin.py`).
- **Contract:** `backend/openapi.json` is committed, with a drift test and `--check`.
- **CI:** PostgreSQL 16 service; database tests are required and cannot be skipped. CI also
  checks OpenAPI drift, runs the migration round trip and `alembic check`, and seeds twice to
  prove repeat runs are harmless. Python 3.10 and 3.12.

Verification (local; Windows; PostgreSQL 16.16):

- **Tests:** 405 passed and 8 xfailed (F1–F8, strict). Results are identical on Python 3.10.11
  and 3.12.15. Branch coverage is 99.95% (gate 85%).
- **Lint and types:** mypy (strict) reports no issues in 107 files. ruff and prettier are clean,
  and the Phase 1 golden checks pass.
- **Golden parity through the API:** run against both the in-memory repository and PostgreSQL,
  with identical results.
  - Overall: 17,326 numeric comparisons, 17,318 bit-exact. 8 needed the 1e-12 tolerance (of
    6,216 where it was allowed), at most 2 ULP, all from the 5 °C `exp()` rates.
  - The database round trip is lossless: all 1,280 stored doubles match bit for bit.
- **Protected files:** all 29 are byte-identical (11 golden fixtures, 4 legacy files, 14 Phase 2
  analytics files).
- **Database tests:** they use disposable `volterra_test_*` databases only and leave none
  behind.
- **Live run:** `uvicorn` against the development database (migrated and seeded) served the
  golden SOH (86.0894…) and RUL (112.73, 111.46–114.03) values.

## Next

Phase 4: React + TypeScript frontend rebuilt against this API (types generated from
`backend/openapi.json`). This waits for review and approval.
