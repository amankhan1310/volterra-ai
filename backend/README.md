# backend

VOLTERRA AI backend:

- a FastAPI service (`/api/v1`) backed by PostgreSQL 16
- `app/analytics`: the **v1** algorithms, a standard-library-only port of the legacy prototype
  verified against the golden fixtures in [`tests/golden/`](tests/golden/README.md), and the
  corrected **v2** methods for the known defects F1–F8 (opt-in, see
  [`../CHANGELOG.md`](../CHANGELOG.md))

The API contract is committed as [`openapi.json`](openapi.json).

## Layout

| Path             | Contents                                                                                                                                                             |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/analytics/` | v1 algorithms (Phase 2, unchanged), `twin.py` (Phase 3), `*_v2.py` (Phase 5)                                                                                         |
| `app/db/`        | SQLAlchemy models, async session, repositories, `synthetic-v1` seed, real-dataset importer (`import_dataset.py`, Phase 6)                                            |
| `app/schemas/`   | Pydantic request/response models (the public contract)                                                                                                               |
| `app/services/`  | `analysis` (cached `analyze()` / `analyze_v2()`), `simulation`, mappers                                                                                              |
| `app/api/v1/`    | Routers: health, datasets, analysis, monitoring, simulator, scenarios                                                                                                |
| `app/core/`      | Settings (secrets as `SecretStr`) and the error envelope                                                                                                             |
| `alembic/`       | Async migration environment; `versions/0001_initial_schema.py`, `0002_real_dataset_provenance.py`, `0003_cycle_source_ref.py`, `0004_nullable_cycle_measurements.py` |
| `tests/`         | parity, unit, api, db (PostgreSQL) and `v2` (Phase 5 fixes) suites                                                                                                   |

v1 reproduces the prototype exactly, including known defects F1–F8 (strict expected-failure tests
in `tests/parity/test_known_defects.py`, which keep failing for v1). Phase 5 added the fixes as
separate **v2** implementations (`forecast_v2`, `anomalies_v2`, `simulator_v2`, `advisor_v2`,
`insights_v2`, composed by `analysis_v2.analyze_v2()`), with their own expected-value tests in
`tests/v2/`. v1 stays the API default; v2 is opt-in with `?algorithm=v2`. The v2 forecast is an
interim quadratic, not a production-validated model (Phase 7 replaces it).

## Setup

Requires [uv](https://docs.astral.sh/uv/) (CI uses 0.12.24), Python 3.10 or newer, and
PostgreSQL 16 (native install, or `docker compose -f ../infra/docker-compose.yml up -d`).

```sh
cd backend
cp .env.example .env                 # then set DATABASE_URL / TEST_DATABASE_URL credentials
uv sync --locked                     # create .venv from uv.lock
uv run alembic upgrade head          # create the schema in DATABASE_URL
uv run python -m app.db.seed         # load synthetic-v1 (idempotent)
uv run uvicorn --factory app.main:create_app --reload
# API docs: http://127.0.0.1:8000/api/v1/docs
```

`backend/.env` is git-ignored. Settings hold the database URL as a secret, so it never appears
in logs or error messages.

## Importing real datasets (Phase 6)

Real datasets arrive as canonical Parquet bundles built by `volterra_ml`
(see [`../docs/datasets/canonical-schema.md`](../docs/datasets/canonical-schema.md)):

```sh
uv run alembic upgrade head    # 0002 provenance, 0003 source_ref, 0004 nullable temperature/voltage
uv run python -m app.db.import_dataset "$VOLTERRA_DATA_DIR/processed/nasa-pcoe-battery/2022-09-18"
```

The importer re-hashes the bundle, checks every column against the contract and every row
against the database rules, then imports in **one transaction**: the dataset with its
publisher, licence, citation and DOI; batteries with their source identifiers, SOH reference and
first measured capacity; every cycle with a measured capacity and SOH (temperature or voltage
may be null and are never filled in; sample-less placeholders stay in the bundle), with source
position and quality flags; and every raw and processed file (path relative to the data directory, size,
SHA-256). Re-importing the same bundle is a no-op; a changed bundle updates batteries in place
(scenarios stay attached). Invalid bundles, a dataset with another source under the same slug,
or batteries that would disappear are refused before anything is written. The synthetic dataset
can never be overwritten. Dataset paths are stored relative to `VOLTERRA_DATA_DIR`.

The synthetic battery is always listed first, so it stays the frontend's default; real batteries
are chosen with `?battery=<dataset>:<external_id>`. Each battery reports whether the analytics
can run (`analysis.available`; `reason` `missing_measurement` or `insufficient_data`;
`min_cycles`). The analytics are **not validated on real cells**, which every real-cell context
states in `note`. Set `VOLTERRA_DATA_DIR` for the API to serve per-cycle samples from the bundle
files. Importing real data into the development database needs the owner's approval; imports are
exercised on disposable `volterra_test_*` databases and, in CI, on generated bundles only
(`python -m tests.support.fixture_bundles ci-import`, which refuses any database other than the
local `volterra_ci` service database in GitHub Actions).

## Importing model runs (Phase 7)

```sh
uv run alembic upgrade head                        # 0005 adds ml_models and ml_predictions
uv run python -m app.db.import_models ../artifacts/models/<run>
```

The importer checks the run before writing (status `experimental`, artifact SHA-256s, selected
models, finite and ordered predictions), imports in one transaction and treats a re-import of the
same `run_id` as a no-op. Predictions are stored only for batteries already in the database.
The API serves the most recently imported run. Model runs derived from real data are imported only
into disposable databases unless the owner approves otherwise; CI imports a generated run
(`tests/support/model_runs.py`, made-up values).

## API overview (`/api/v1`)

| Method and path                          | Purpose                                                      |
| ---------------------------------------- | ------------------------------------------------------------ |
| `GET /health`                            | Application status, plus database status reported separately |
| `GET /datasets`, `/datasets/{slug}`      | Dataset metadata (internal metadata is never exposed)        |
| `GET /batteries`, `/batteries/{id}`      | Batteries                                                    |
| `GET /batteries/{id}/cycles`             | Per-cycle data (`from_cycle`, `to_cycle`)                    |
| `GET /batteries/{id}/cycles/{n}/samples` | Measured samples of one cycle (`max_points` 2–20000)         |
| `GET /batteries/{id}/summary`            | SOH, fade, RUL interval, health, KPIs (`eol_pct` 60–90)      |
| `GET /batteries/{id}/forecast`           | Observed series + forecast (v1 linear, v2 quadratic)         |
| `GET /batteries/{id}/backtest`           | Hold-out backtest                                            |
| `GET /batteries/{id}/insights`           | Structured insights (kind, text, values)                     |
| `GET /batteries/{id}/anomalies`          | Events (`include_scores`; v2 adds `mode=causal`)             |
| `GET /batteries/{id}/twin`               | Pack state at a cycle (`cycle`), illustrative modules        |
| `GET /batteries/{id}/simulator`          | Defaults, slider ranges, coefficient provenance              |
| `POST /batteries/{id}/simulate`          | Scenario vs baseline, trajectories                           |
| `GET /batteries/{id}/advisor`            | Charging Advisor (`eol_pct`, `start_soh_pct`)                |
| `GET/POST /batteries/{id}/scenarios`     | Saved scenarios                                              |
| `GET/PATCH/DELETE /scenarios/{id}`       | Saved scenario                                               |
| `GET /models`                            | Latest model run: per-dataset CV and held-out test metrics   |
| `GET /batteries/{id}/rul-predictions`    | Stored RUL predictions with 90 % intervals (experimental)    |

Contract conventions:

- **Algorithm version:** `summary`, `forecast`, `backtest`, `insights`, `anomalies`, `simulator`,
  `simulate` and `advisor` take an optional `algorithm` query parameter: `v1` (default, the
  prototype's methods including F1–F8) or `v2` (the corrected methods). v2-only response fields
  are optional and omitted from v1 responses, so v1 clients see no change.
- **Context:** every analytical response includes `context`: battery, dataset,
  `algorithm_version` (`"v1"` or `"v2"`), `eol_pct`, and `data_provenance`, which is `simulated`
  for synthetic data and `measured` for real data.
- **Provenance:** every value carries a `provenance` of `measured`, `simulated`, `fitted`,
  `predicted` or `assumed`.
- **Not-a-number values:** NaN and ±Infinity are written as the strings `"NaN"`, `"Infinity"`
  and `"-Infinity"`. `null` always means "not applicable".
- **Errors:** every error uses `{"error": {"code", "message", "details"}}`. A missing database
  gives 503, an unknown id 404, and invalid input 422. Analytics that lack measured inputs
  return 422 `missing_measurement` or `insufficient_data`; samples return 422 `no_samples`
  (synthetic data), 404 `cycle_not_found` or 503 `samples_unavailable`.

After changing endpoints or schemas, regenerate the contract with `uv run python -m app.openapi`.
`--check` verifies it is current, and so does a test.

## Tests

```sh
uv run ruff check . && uv run ruff format --check .
uv run mypy                          # strict
uv run pytest                        # everything; coverage gate 85%
```

PostgreSQL tests (marker `db`) need `TEST_DATABASE_URL`, a maintenance database such as
`postgres`:

- Each test session creates databases named `volterra_test_<random>`, migrates and seeds them,
  and drops them afterwards.
- A guard refuses to create, drop or downgrade any other database.
- Without `TEST_DATABASE_URL` these tests are skipped with a visible reason. With
  `VOLTERRA_REQUIRE_DB=1`, as CI sets, they fail instead.

The pytest summary includes a golden-parity table showing how many comparisons were bit-exact.

## Rules

- **Analytics code:** standard library only, mirroring JavaScript's operation order. Never use
  `sum()`, `round()` or `math.fsum` there. `tests/unit/test_source_hygiene.py` enforces this.
- **API layer:** mappers, dependencies and routers only copy values.
  `tests/unit/test_api_purity.py` fails on any arithmetic there.
- **Migrations:** never edit a merged migration; add a new one per change. Every migration must
  be able to roll back.
- **Golden fixtures:** never edit `tests/golden/*.json`. They are generated from `legacy/`.
