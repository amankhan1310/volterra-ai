# VOLTERRA AI

Intelligent battery health and predictive analytics: state-of-health (SOH) estimation,
degradation analysis, remaining-useful-life (RUL) prediction, anomaly detection and
scenario simulation.

> **Status:** Phase 4 in progress: the React frontend is being rebuilt against the FastAPI +
> PostgreSQL backend (Phase 3), one milestone at a time. Milestone 1 (application shell) is done;
> the six pages follow. See [`ARCHITECTURE_PLAN.md`](ARCHITECTURE_PLAN.md) for the plan and
> [`PROJECT_STATUS.md`](PROJECT_STATUS.md) for progress.

## Repository layout

| Path        | Contents                                                                  |
| ----------- | ------------------------------------------------------------------------- |
| `legacy/`   | The original static browser prototype (reference implementation).         |
| `frontend/` | React + TypeScript single-page app (see its README; Phase 4 in progress). |
| `backend/`  | FastAPI API, PostgreSQL models/migrations, v1 analytics (see its README). |
| `ml/`       | `volterra_ml` package: data loaders, features, models _(scaffold only)_.  |
| `infra/`    | `docker-compose.yml` for an optional local PostgreSQL 16.                 |
| `.github/`  | CI workflows.                                                             |

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
Pydantic v2 · SQLAlchemy 2 · Alembic · PostgreSQL 16 · planned: scikit-learn · LightGBM · pandas.

## Disclaimer

Academic software project. It does not replace a manufacturer's Battery Management System,
professional diagnostics or warranty assessment.
