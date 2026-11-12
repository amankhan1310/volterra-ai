# VOLTERRA AI

Intelligent battery health and predictive analytics: state-of-health (SOH) estimation,
degradation analysis, remaining-useful-life (RUL) prediction, anomaly detection and
scenario simulation.

> **Status:** Phase 0 (foundations) of the migration from a browser prototype to a full-stack
> application. See [`ARCHITECTURE_PLAN.md`](ARCHITECTURE_PLAN.md) for the plan and
> [`PROJECT_STATUS.md`](PROJECT_STATUS.md) for progress.

## Repository layout

| Path        | Contents                                                                 |
| ----------- | ------------------------------------------------------------------------ |
| `legacy/`   | The original static browser prototype (reference implementation).        |
| `frontend/` | React + TypeScript single-page app _(scaffold only — Phase 4)_.          |
| `backend/`  | FastAPI service, PostgreSQL models and migrations _(scaffold only)_.     |
| `ml/`       | `volterra_ml` package: data loaders, features, models _(scaffold only)_. |
| `.github/`  | CI workflows.                                                            |

## Running the legacy prototype

The prototype is a static page with no build step. Open `legacy/index.html` in a browser, or
serve the folder:

```sh
python -m http.server 8080 --directory legacy
# then open http://localhost:8080
```

All data in the prototype is a seeded synthetic dataset; it is not connected to any vehicle.

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

## Planned stack

React 18 · TypeScript · Vite · ECharts · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic ·
PostgreSQL 16 · scikit-learn · LightGBM · pandas.

## Disclaimer

Academic software project. It does not replace a manufacturer's Battery Management System,
professional diagnostics or warranty assessment.
