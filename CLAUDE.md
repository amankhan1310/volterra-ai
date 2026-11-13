# CLAUDE.md

Guidance for AI coding assistants working in this repository.

## Project

VOLTERRA AI: battery health analytics (SOH, RUL, anomaly detection, scenario simulation).
The repo is migrating from a static browser prototype (`legacy/`) to React + TypeScript,
FastAPI, PostgreSQL and a Python ML package. **`ARCHITECTURE_PLAN.md` is the source of truth**
for architecture, phases and conventions; **`PROJECT_STATUS.md`** records progress.

## Layout

- `legacy/`: original prototype (`index.html`, `core.js` data + analytics, `ui.js` redesign
  layer that overrides the renderers in `core.js`, `style.css`). **Frozen reference.** Do not
  edit or reformat these four files; they are the source for golden parity fixtures. Helper
  tooling may be added under `legacy/tools/`.
- `backend/`: FastAPI service (`app/`: analytics, db, schemas, services, api), Alembic
  migrations (`alembic/`), API contract (`openapi.json`), tests in `backend/tests/`.
- `ml/`: `volterra_ml` package, tests in `ml/tests/`.
- `frontend/`: React 19 + TypeScript app (Vite 8, React Router 7, TanStack Query 5); unit tests
  in `src/**/*.test.tsx`, Playwright suites in `frontend/e2e/`.
- `data/`, `artifacts/`: git-ignored. Never commit datasets, model binaries or `.env`.

## Working rules

- Work phase by phase as defined in `ARCHITECTURE_PLAN.md` §10; do not start the next phase
  without the user's approval. Update `PROJECT_STATUS.md` when a milestone completes.
- Branch from `main` (`feat/…`, `fix/…`, `chore/…`, `docs/…`, `test/…`); Conventional Commits;
  small commits that each pass lint/tests. Commit and push only when the user asks.
- Every analytic value exposed to the UI carries provenance
  (`measured | simulated | fitted | predicted | assumed`) and, for predictions, an interval.
- ML evaluation splits by battery, never by row; features may only use past cycles.
- Known prototype defects F1–F8 (plan §3.6) are reproduced deliberately in the **v1** algorithms
  (`backend/app/analytics`). v1 is permanent. Fixes are separate **v2** implementations with
  their own expected-value tests, and the golden fixtures are never modified. The strict-xfail
  tests in `backend/tests/parity/test_known_defects.py` must keep failing for v1.
- Analytics code is standard-library only and mirrors JavaScript operation order. Never use
  `sum()`, `round()` or `math.fsum` there; use `app.analytics.jsmath`.
- The API never re-implements analytics: it calls `legacy_v1.analyze()` (cached, keyed by a data
  checksum) and the v1 simulator functions. Mappers, dependencies and routers only copy values
  (`tests/unit/test_api_purity.py`).
- Database tests run only against disposable `volterra_test_<hex>` databases (guarded by
  `tests/support/database.py`). Never run destructive operations against the development
  database or print credentials from `backend/.env`.
- Schema changes go through new Alembic migrations (never edit merged ones). After API changes,
  regenerate `backend/openapi.json` (`uv run python -m app.openapi`), then the frontend types
  (`cd frontend && npm run api:types`); CI fails if either is stale.
- Frontend: read every value from the API, never re-implement analytics, and never ship runtime
  mock data. MSW fixtures are test-only and recorded from the real API
  (`npm run record:fixtures`). No `innerHTML`, `prompt()` or `alert()` (lint-enforced); colours
  come from `src/styles/tokens.css`, not literals. Phase 4 is built milestone by milestone
  (M1–M6), one branch and PR each, with a live review before the next starts.

## Commands

```sh
ruff check . && ruff format --check .      # Python lint (config: ruff.toml)
npx prettier@3.3.3 --check .               # formatting (frozen legacy files excluded)
node --check legacy/core.js legacy/ui.js   # legacy syntax check
python -m http.server 8080 --directory legacy   # run the prototype
node legacy/tools/export_golden.js --check # golden fixtures: deterministic + up to date
node --test legacy/tools/export_golden.test.js  # golden exporter tests
cd backend && uv sync --locked && uv run mypy && uv run pytest   # backend (coverage gate 85%)
cd backend && uv run alembic upgrade head && uv run python -m app.db.seed   # dev database
cd backend && uv run uvicorn --factory app.main:create_app --reload      # API on :8000
cd frontend && npm ci && npm run dev       # React app on :5173 (proxies /api to :8000)
cd frontend && npm run api:types:check && npm run lint && npm run typecheck && npm run test:coverage && npm run build
cd frontend && PW_CHANNEL=msedge npm run e2e   # E2E + axe against the running API (local browser)
```

Golden fixtures in `backend/tests/golden/` are generated, never hand-edited; see the README
there. In Phase 2 they are the specification: fix the Python port, not the fixtures.

## Environment notes (Windows dev machine)

- The `python` on PATH may belong to an unrelated project's virtualenv; create a project venv
  (or use `uv`) rather than installing into it.
- Line endings are normalised to LF via `.gitattributes`.
- Node 24 (`frontend/.nvmrc`) is managed with nvm-windows; uv 0.12.24 (the CI version) is at
  `~/.local/bin/uv.exe`.
- Do not download Playwright browsers locally without the user's approval; run local E2E with an
  installed browser (`PW_CHANNEL=msedge`). CI downloads Chromium itself.
