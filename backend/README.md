# backend

VOLTERRA AI backend:

- a FastAPI service (`/api/v1`) backed by PostgreSQL 16
- `app/analytics`: the **v1** algorithms, a standard-library-only port of the legacy prototype
  verified against the golden fixtures in [`tests/golden/`](tests/golden/README.md)

The API contract is committed as [`openapi.json`](openapi.json).

## Layout

| Path             | Contents                                                                   |
| ---------------- | -------------------------------------------------------------------------- |
| `app/analytics/` | v1 algorithms (Phase 2, unchanged) + `twin.py` (temperature band, Phase 3) |
| `app/db/`        | SQLAlchemy models, async session, repositories, `synthetic-v1` seed        |
| `app/schemas/`   | Pydantic request/response models (the public contract)                     |
| `app/services/`  | `analysis` (cached `legacy_v1.analyze()`), `simulation`, copy-only mappers |
| `app/api/v1/`    | Routers: health, datasets, analysis, monitoring, simulator, scenarios      |
| `app/core/`      | Settings (secrets as `SecretStr`) and the error envelope                   |
| `alembic/`       | Async migration environment and `versions/0001_initial_schema.py`          |
| `tests/`         | parity, unit, api and db (PostgreSQL) suites                               |

v1 reproduces the prototype exactly, including known defects F1–F8 (strict expected-failure tests
in `tests/parity/test_known_defects.py`). Fixes will be separate v2 implementations.

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

## API overview (`/api/v1`)

| Method and path                      | Purpose                                                      |
| ------------------------------------ | ------------------------------------------------------------ |
| `GET /health`                        | Application status, plus database status reported separately |
| `GET /datasets`, `/datasets/{slug}`  | Dataset metadata (internal metadata is never exposed)        |
| `GET /batteries`, `/batteries/{id}`  | Batteries                                                    |
| `GET /batteries/{id}/cycles`         | Per-cycle data (`from_cycle`, `to_cycle`)                    |
| `GET /batteries/{id}/summary`        | SOH, fade, RUL interval, health, KPIs (`eol_pct` 60–90)      |
| `GET /batteries/{id}/forecast`       | Observed series + v1 linear forecast                         |
| `GET /batteries/{id}/backtest`       | Hold-out backtest                                            |
| `GET /batteries/{id}/insights`       | Structured insights (kind, text, values)                     |
| `GET /batteries/{id}/anomalies`      | v1 detector events (`include_scores` for per-cycle z)        |
| `GET /batteries/{id}/twin`           | Pack state at a cycle (`cycle`), illustrative modules        |
| `GET /batteries/{id}/simulator`      | Defaults, slider ranges, coefficient provenance              |
| `POST /batteries/{id}/simulate`      | Scenario vs baseline, trajectories                           |
| `GET /batteries/{id}/advisor`        | Charging Advisor (`eol_pct`, `start_soh_pct`)                |
| `GET/POST /batteries/{id}/scenarios` | Saved scenarios                                              |
| `GET/PATCH/DELETE /scenarios/{id}`   | Saved scenario                                               |

Contract conventions:

- **Context:** every analytical response includes `context`: battery, dataset,
  `algorithm_version: "v1"`, `eol_pct`, and `data_provenance`, which is `simulated` for synthetic
  data and `measured` for real data.
- **Provenance:** every value carries a `provenance` of `measured`, `simulated`, `fitted`,
  `predicted` or `assumed`.
- **Not-a-number values:** NaN and ±Infinity are written as the strings `"NaN"`, `"Infinity"`
  and `"-Infinity"`. `null` always means "not applicable".
- **Errors:** every error uses `{"error": {"code", "message", "details"}}`. A missing database
  gives 503, an unknown id 404, and invalid input 422.

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
