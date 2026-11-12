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
- `backend/`: FastAPI service (`app/`), tests in `backend/tests/`.
- `ml/`: `volterra_ml` package, tests in `ml/tests/`.
- `frontend/`: React + TypeScript app.
- `data/`, `artifacts/`: git-ignored. Never commit datasets, model binaries or `.env`.

## Working rules

- Work phase by phase as defined in `ARCHITECTURE_PLAN.md` §10; do not start the next phase
  without the user's approval. Update `PROJECT_STATUS.md` when a milestone completes.
- Branch from `main` (`feat/…`, `fix/…`, `chore/…`, `docs/…`, `test/…`); Conventional Commits;
  small commits that each pass lint/tests. Commit and push only when the user asks.
- Every analytic value exposed to the UI carries provenance
  (`measured | simulated | fitted | predicted | assumed`) and, for predictions, an interval.
- ML evaluation splits by battery, never by row; features may only use past cycles.
- Known prototype defects F1–F8 (plan §3.6) are reproduced deliberately during the parity port,
  then fixed as separate, tested changes.

## Commands

```sh
ruff check . && ruff format --check .      # Python lint (config: ruff.toml)
npx prettier@3.3.3 --check .               # formatting (legacy/ excluded)
node --check legacy/core.js legacy/ui.js   # legacy syntax check
python -m http.server 8080 --directory legacy   # run the prototype
```

## Environment notes (Windows dev machine)

- The `python` on PATH may belong to an unrelated project's virtualenv; create a project venv
  (or use `uv`) rather than installing into it.
- Line endings are normalised to LF via `.gitattributes`.
