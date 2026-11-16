# Deployment: Vercel (frontend) and Render (API + PostgreSQL)

The React app is a static build served by Vercel. It calls `/api/...` on its own origin, and
`frontend/vercel.json` rewrites those requests to the FastAPI service on Render, so browsers never
make cross-origin calls. `render.yaml` describes the API and its PostgreSQL database.

What is deployed: the application and the **synthetic-v1** dataset (seeded automatically).
What is not: the real NASA, CALCE and Severson data (licences and size; decision D8) and any
model run, unless the owner decides otherwise (see below).

## 1. Backend on Render

1. Render dashboard → **New → Blueprint** → select this GitHub repository. Render reads
   `render.yaml` and creates `volterra-db` (PostgreSQL 16) and `volterra-api` (Python 3.12).
2. When asked, set `VOLTERRA_CORS_ORIGINS` to the Vercel production URL (for example
   `https://volterra-ai.vercel.app`). Comma-separate several origins.
3. Each start runs `alembic upgrade head`, then the idempotent synthetic seed, then uvicorn. Both
   steps are no-ops once the database is current.
4. Check `https://<service>.onrender.com/api/v1/health`: `status` should be `ok` and the
   database `ok`.

Notes:

- `DATABASE_URL` comes from the database (`postgres://…`); the app converts it for asyncpg
  (`app.core.config.normalise_dsn`, tested).
- Free instances sleep when idle; the first request after a pause takes about a minute. Free
  PostgreSQL databases expire after a limited period: use a paid plan for anything lasting.
- Logs never contain the database URL (it is a `SecretStr`).

## 2. Frontend on Vercel

1. Vercel dashboard → **Add New → Project** → import this repository, **Root Directory:
   `frontend`**. `frontend/vercel.json` sets the build (`npm ci`, `npm run build`, output `dist`).
2. If the Render service is not named `volterra-api`, edit the rewrite destination in
   `frontend/vercel.json` to its URL.
3. Node: the project pins Node 24 (`frontend/.nvmrc`); select Node 24 in the project settings if
   Vercel does not pick it up.
4. Open the deployment and check that the header shows the synthetic battery and the sidebar
   status says "API and database online".

`vercel.json` also sets basic security headers (`nosniff`, `X-Frame-Options: DENY`, a strict
referrer policy and a restrictive permissions policy) and long-term caching for hashed assets.
No Content-Security-Policy is set yet: `index.html` has a small inline script that applies the
theme before first paint, which a strict CSP would need a hash for.

## 3. Optional: model evaluations in production

The Models page shows "No model run imported" until a run is imported. A run made from the real
datasets holds aggregate metrics plus per-battery predictions. Predictions are only stored for
batteries present in the target database, so on a synthetic-only deployment only the metrics
appear. Importing one is the owner's decision:

```sh
cd backend
DATABASE_URL=<render external URL> uv run python -m app.db.import_models ../artifacts/models/<run>
```

## Environment variables

| Variable                       | Where            | Purpose                                                                             |
| ------------------------------ | ---------------- | ----------------------------------------------------------------------------------- |
| `DATABASE_URL`                 | API              | PostgreSQL URL (`postgres://`, `postgresql://` or `postgresql+asyncpg://`)          |
| `VOLTERRA_ENV`                 | API              | `development`, `test` or `production`                                               |
| `VOLTERRA_CORS_ORIGINS`        | API              | Allowed browser origins for direct calls (comma-separated)                          |
| `VOLTERRA_ANALYSIS_CACHE_SIZE` | API              | Cached analyses (default 32)                                                        |
| `VOLTERRA_DATA_DIR`            | API, ml          | Data directory with `processed/` bundles (samples endpoint; not used in production) |
| `TEST_DATABASE_URL`            | tests            | Maintenance database for disposable test databases (never production)               |
| `VOLTERRA_API_URL`             | Vite dev/preview | Backend URL for the local proxy (default `http://127.0.0.1:8000`)                   |

## Local demonstration

```sh
cd backend && uv sync --locked && uv run alembic upgrade head && uv run python -m app.db.seed
uv run uvicorn --factory app.main:create_app --port 8000
cd ../frontend && npm ci && npm run dev        # http://localhost:5173
```
