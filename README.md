# VOLTERRA AI

Intelligent battery health and predictive analytics: state-of-health (SOH) estimation,
degradation analysis, remaining-useful-life (RUL) prediction, anomaly detection and
scenario simulation.

> **Status:** Phases 0–8 and the essential Phase 10 work are complete; Phase 9 (reports,
> notifications, authentication) is deferred. The analytics keep the prototype's **v1** methods as
> the default, with corrected **v2** methods opt-in (`?algorithm=v2`). Real datasets (NASA,
> CALCE, Severson) have loaders and an importer; the Phase 7 ML models and the Phase 8 simulator
> evidence are **experimental and not production-validated**: see
> [`docs/models/README.md`](docs/models/README.md) and
> [`docs/models/simulator-evidence.md`](docs/models/simulator-evidence.md). Plan:
> [`ARCHITECTURE_PLAN.md`](ARCHITECTURE_PLAN.md); progress:
> [`PROJECT_STATUS.md`](PROJECT_STATUS.md); changes: [`CHANGELOG.md`](CHANGELOG.md);
> deployment (Vercel + Render): [`docs/deployment.md`](docs/deployment.md).

## Repository layout

| Path        | Contents                                                                            |
| ----------- | ----------------------------------------------------------------------------------- |
| `legacy/`   | The original static browser prototype (reference implementation).                   |
| `frontend/` | React + TypeScript single-page app (see its README).                                |
| `backend/`  | FastAPI API, PostgreSQL models/migrations, v1 analytics (see its README).           |
| `ml/`       | `volterra_ml` package: dataset acquisition (Phase 6 M1); loaders and models follow. |
| `infra/`    | `docker-compose.yml` for an optional local PostgreSQL 16.                           |
| `.github/`  | CI workflows.                                                                       |

## Running the legacy prototype

The prototype is a static page with no build step. Open `legacy/index.html` in a browser, or
serve the folder:

```sh
python -m http.server 8080 --directory legacy
# then open http://localhost:8080
```

All data in the prototype is a seeded synthetic dataset; it is not connected to any vehicle.

## Running the React frontend

Needs Node 24 and the backend running on port 8000 with a seeded database (see
[`backend/README.md`](backend/README.md) and [`frontend/README.md`](frontend/README.md)).

```sh
cd frontend
npm ci
npm run dev
# then open http://localhost:5173
```

## Linting

```sh
# Python (backend/, ml/)
ruff check .
ruff format --check .

# Formatting (the four frozen prototype files and generated fixtures are excluded)
npx prettier@3.3.3 --check .
```

## Golden reference fixtures (Phase 1)

The prototype's exact outputs are exported to `backend/tests/golden/` as the reference for the
Python port. See [`backend/tests/golden/README.md`](backend/tests/golden/README.md).

```sh
node legacy/tools/export_golden.js --check   # deterministic + matches committed fixtures
node --test legacy/tools/export_golden.test.js  # exporter test suite
```

## Stack

React 19 · TypeScript · Vite 8 · TanStack Query · ECharts (from Phase 4 Milestone 2) · FastAPI ·
Pydantic v2 · SQLAlchemy 2 · Alembic · PostgreSQL 16 · numpy · scikit-learn · LightGBM (offline
modelling in `ml/`) · Vercel (frontend) and Render (API) for deployment.

## Disclaimer

Academic software project. It does not replace a manufacturer's Battery Management System,
professional diagnostics or warranty assessment.
