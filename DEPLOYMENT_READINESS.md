# Deployment readiness: VOLTERRA AI public demonstration

Target: frontend on Vercel (Hobby), API and PostgreSQL on Render (free), separate production
database, **synthetic-v1 data only**. Audit and hardening on branch `fix/deploy-security-hardening`
(from `main` = `c782115`), 2026-11-17. **No hosting service has been created.**

Status legend: **Ready** · **Requires configuration** · **Requires code correction** (fixed
items say how) · **Blocked**.

## 1. Summary

| Area                           | Status                                                                                                                                 |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| Scenario write security        | Was **Requires code correction**, now fixed (signed anonymous sessions, CSRF, ownership)                                               |
| Scenario limits                | Was **Requires code correction**, now fixed (atomic, database-enforced)                                                                |
| Health checks                  | Was **Requires code correction**, now fixed (`/health/live`, `/health/ready` → 503)                                                    |
| Request protection             | Was **Requires code correction**, now fixed (rate limits, 413, headers, 503 on DB outage)                                              |
| Models page on empty database  | Was **Requires code correction** (13 E2E regressions), now fixed                                                                       |
| Secrets in error messages      | Was **Requires code correction** (found during testing), now fixed                                                                     |
| Simulator vs write budget (R1) | Was **Requires code correction** (pre-merge review), now fixed: separate calculation budget                                            |
| Per-client identity (R2)       | Was **Requires code correction** (pre-merge review), now fixed: signed session, then right-most address; deployment-time checks in §4a |
| Hosting accounts               | **Blocked on the owner**: Render and Vercel accounts are needed (no CLI or credentials here)                                           |
| CORS origin, Vercel rewrite    | **Requires configuration** after the services exist (URLs not known yet)                                                               |
| Model run in production        | **Owner decision** (see §6)                                                                                                            |

Final evidence is in §5. Remaining risks are in §7.

## 2. Phase 1 audit: original findings

| #   | Finding                                                                                                                                                                                 | Class                      |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| A1  | Git: deploy source is `main` = `c782115` (PR #19 merge); local checkout content identical; untracked `presentation/`, `project_report/`, template DOCX (not ignored)                    | Ready (ignore rules added) |
| A2  | Backend build `uv sync --locked --no-dev` (uv 0.12.24, Python 3.12.8 on Render); lockfile present; Phase 10 rehearsal on 3.12 passed                                                    | Ready                      |
| A3  | Frontend build `npm ci && npm run build` (Node 24, `.nvmrc` 24.22.3, `engines ^24.15.0`); output `dist`                                                                                 | Ready                      |
| A4  | Startup runs `alembic upgrade head` + idempotent synthetic seed + uvicorn; migrations 0001–0005 additive                                                                                | Ready                      |
| A5  | **Scenario endpoints accepted unauthenticated create/rename/delete from anyone, for everyone's scenarios**                                                                              | Requires code correction   |
| A6  | **No server-side scenario limit** (the 4-scenario limit was UI-only; a test asserted 6 were allowed)                                                                                    | Requires code correction   |
| A7  | `/health` always 200 even with the database down; Render health check pointed at it                                                                                                     | Requires code correction   |
| A8  | No rate limiting or request-size limit; CORS `allow_headers=["*"]`                                                                                                                      | Requires code correction   |
| A9  | Error envelope already safe (no exception messages; validation errors without input)                                                                                                    | Ready                      |
| A10 | Frontend calls the API on its own origin; Vercel rewrites `/api/*` to Render; no `localhost` API URL in the bundle (two `http://localhost` strings are React Router's URL-parsing base) | Ready                      |
| A11 | `vercel.json` rewrite target hard-codes `volterra-api.onrender.com`; Render appends a suffix if the name is taken                                                                       | Requires configuration     |
| A12 | `VOLTERRA_CORS_ORIGINS` must be the real Vercel URL                                                                                                                                     | Requires configuration     |
| A13 | No file uploads; samples endpoint answers 503 without `VOLTERRA_DATA_DIR` (not set in production); no persistent disk needed                                                            | Ready                      |
| A14 | Secrets: `DATABASE_URL` is a `SecretStr`, `.env` ignored, Render injects the URL from the database                                                                                      | Ready                      |
| A15 | API docs (`/api/v1/docs`, `/api/v1/openapi.json`) public; they describe a contract already public in the repository                                                                     | Ready (kept, see §7)       |
| A16 | Production source maps are emitted; the repository is public, so they reveal nothing new                                                                                                | Ready (noted)              |
| A17 | **Production rehearsal: 13 E2E failures on the Models page** with no model run (see §3)                                                                                                 | Requires code correction   |
| A18 | Free Render PostgreSQL expires 30 days after creation (14-day grace), 1 GB, no backups; free web service sleeps after 15 min idle (~1 min cold start)                                   | Ready (limitation, §7)     |
| A19 | **Found during testing:** a configuration validation error echoed the raw settings input, which could include the database URL, into logs                                               | Requires code correction   |
| A20 | **Found during testing:** with the database down, data endpoints answered a generic 500 (no leak, but not retryable)                                                                    | Requires code correction   |

## 3. The 17 failures of the first rehearsal (2026-11-17, before any fix)

Full Playwright suite against the production build + production-mode API on a throwaway database
(synthetic-v1 only): **88 passed, 17 failed**.

| Failures | Tests                                                                                     | Cause                                                                                                                                                                                                                | Kind                                                      |
| -------- | ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| 4        | `models.spec.ts` (3), `real-data.spec.ts` (1)                                             | Expect CI-only generated fixtures (`generated0001` run, `calce-test:CS2_T` battery). A synthetic-only database cannot have them; real data must not be imported. Same 4 as the local run on the dev DB.              | **Baseline**                                              |
| 13       | `a11y` Models dark/light (2), `responsive` all widths × themes (10), `shell` → Models (1) | The Models page correctly showed "No model run imported", but that empty state lacked the `page-content` marker, so the shared `settled()` helper waited 30 s and failed. CI never saw it (CI always imports a run). | **New regression**: genuine missing empty-state behaviour |

Fix (A17): the empty state is now wrapped as the page's content (`ModelsPage.tsx`, text and design
unchanged) and a unit test pins it. No data was imported.

## 4. Fixes (code)

### Scenario access control (A5): signed anonymous sessions

- **Modes** (`VOLTERRA_SCENARIO_ACCESS`): `session` (production default), `shared` (local
  development default: unchanged single-user behaviour; **refused in production**), `disabled`
  (read-only: writes 403).
- **Identifier:** 128 bits from `secrets.token_bytes` (OS CSPRNG), as a UUIDv4.
- **Tamper resistance:** cookie value `<id>.<HMAC-SHA256(secret, context ‖ id)>`, verified in
  constant time (`hmac.compare_digest`); a forged, altered or foreign-key cookie is simply no
  session. Secret `VOLTERRA_SESSION_SECRET` (≥ 32 chars) is **required in production** (startup
  fails without it); Render generates it (`generateValue: true`: random base64 256-bit, created
  once, never in the repository).
- **Cookie:** `HttpOnly; SameSite=Lax; Secure` (production); `Path=/api/v1`; 30 days.
- **Ownership on every operation:** list, read, update and delete are filtered by owner in the
  SQL `WHERE` clause; another session's scenario answers **404**, exactly like a missing one.
  Requests without a valid session see an empty list.
- **CSRF:** cookie-authenticated writes require `X-Volterra-Client: web` (the frontend client
  sends it on every request); a cross-site page cannot add it without a CORS preflight, which is
  refused. `SameSite=Lax` already withholds the cookie from cross-site POST/PATCH/DELETE. A
  present `Origin` must be the API's own, the forwarded host's, or an allow-listed origin.
- **CORS:** allow-listed origins only, `allow_credentials=False` (the browser app is same-origin
  through the Vercel rewrite, so credentialed cross-origin access is not needed), headers limited
  to `Content-Type` and `X-Volterra-Client`.
- Storage: the existing nullable `scenarios.user_id` column; **no migration**. Existing rows
  (owner `NULL`) remain the shared list in development.

### Scenario limits (A6): atomic, database-enforced, durable

- 4 per battery per owner (`VOLTERRA_SCENARIO_LIMIT`) and 1,000 in total
  (`VOLTERRA_SCENARIO_TOTAL_LIMIT`); 409 `scenario_limit_reached`.
- Count-and-insert run inside one transaction **after** `pg_advisory_xact_lock`, so concurrent
  creators queue and re-count; the lock is released at commit/rollback. These limits live in the
  database: **shared by all API instances and durable across restarts.**

### Health (A7)

| Endpoint               | Checks                      | Status                                |
| ---------------------- | --------------------------- | ------------------------------------- |
| `/api/v1/health/live`  | the process answers         | 200 always                            |
| `/api/v1/health/ready` | `SELECT 1` within 5 s       | 200 `ready`, else **503** `not_ready` |
| `/api/v1/health`       | as before (frontend status) | 200, database status in the body      |

No probe returns connection details or exception messages (`/health` reports only the exception
type, as before). `render.yaml` uses **`/api/v1/health/ready`**.

### Request protection (A8, A20)

- **Rate limits, process-local and in memory** (`backend/app/core/guard.py`), on by default in
  production only; 429 `rate_limited` with `Retry-After`; health endpoints exempt. Three request
  classes (corrected after the pre-merge review, see §4a):

  | Class                                          | Per client | All clients together |
  | ---------------------------------------------- | ---------- | -------------------- |
  | read (GET, HEAD, OPTIONS)                      | 1,200/min  | –                    |
  | calculation (`POST /batteries/{id}/simulate`)  | 600/min    | 3,000/min            |
  | stored write (scenario create, rename, delete) | 30/min     | 120/min              |

  They reset on restart and **are not shared between instances or workers** (N instances allow N
  times the requests). They protect one small instance against bursts and loops, not against a
  distributed attack. The durable protection for stored data is the database-enforced scenario
  limits.

- **Body size:** 16 KB maximum on writes and calculations, enforced while streaming (also for
  chunked bodies), 413.
- **Headers:** `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`;
  `Cache-Control: no-store` on scenario responses.
- **Database outage:** connection errors answer **503** `database_unavailable` with
  `Retry-After: 10`, never the driver's message.

### 4a. Pre-merge review corrections (R1, R2)

**R1: the simulator consumed the write budget.** The What-If Simulator re-runs `POST /simulate`
150 ms after the last input change (`frontend/src/features/simulator/SimulatorPage.tsx`,
`SIMULATE_DEBOUNCE_MS`). The guard counted every POST as a write (30/min per client, 120/min for
everyone), so about 10 s of slider use would block a visitor's simulator, and saving, for the rest
of the minute. Fix: `POST /batteries/{id}/simulate` (stores nothing) is its own **calculation**
class with its own per-client (600/min, above the ~400/min a continuously dragged slider can send)
and all-clients (3,000/min, bounds CPU) limits. It never touches the write budgets, which keep
their stricter values for scenario create, rename and delete. A test pins the defaults against
the debounce interval.

**R2: per-client identity behind Vercel and Render.** Verified chain (documentation and community
evidence, 2026-11-17; to be confirmed after deployment, see below):

1. Vercel's rewrite to an external origin sends the visitor's IP in `X-Forwarded-For` (Vercel
   documentation, request headers on rewrites).
2. Render's proxy **appends** to an incoming `X-Forwarded-For` and does not clear client-supplied
   values (Render community reports; a 2021 staff reply says the first entry is the client). There
   is no official Render documentation of the exact format.

So the right-most entry is the address Render's proxy saw (for proxied traffic a **shared Vercel
edge address**), and every entry to its left may be client-supplied when a client calls Render
directly. Trusting a left entry (`VOLTERRA_TRUSTED_PROXY_HOPS=1`) would let direct callers choose
their own key; Vercel does not publish fixed egress addresses that could prove a request came
through Vercel. Therefore:

- **Browsers are identified by their signed session**, not by address. The guard issues the
  anonymous session cookie with a browser's first API response (HttpOnly, SameSite=Lax, Secure
  in production; HMAC-signed, so it cannot be forged), and the scenario routes use the same
  session for ownership. Each browser has its own allowance, even behind one shared edge.
- **Requests without a valid session** (scripts, forged or expired cookies, a browser's very
  first request) are keyed by the **right-most** `X-Forwarded-For` entry (`TRUSTED_PROXY_HOPS=0`,
  unchanged), which a client cannot forge. Discarding cookies does not create allowance: minting a
  new session needs a cookie-less request, which counts against the network address.
- **All-clients limits ignore identity** (calculations and stored writes), so neither new
  sessions nor addresses bypass them.

Production configuration: `VOLTERRA_TRUSTED_PROXY_HOPS` **unset (0)**; `VOLTERRA_ENV=production`
(turns rate limits and session issuance on); `VOLTERRA_SESSION_SECRET` generated by Render.

**Deployment-time checks (not verifiable before the services exist):**

1. Spoofing, direct to Render: send 1,201 cookie-less `GET /api/v1/datasets` to the Render URL
   within a minute, each with a different `X-Forwarded-For: 10.0.0.<n>`; the requests beyond 1,200
   must answer 429 (proves the right-most entry is Render's and not client-controlled).
2. Independence through Vercel: two browsers (separate profiles) on the Vercel URL each get their
   own `volterra_session` cookie; exhausting one's calculation budget does not affect the other.
3. The cookie arrives through the Vercel rewrite with `Secure; HttpOnly; SameSite=Lax;
Path=/api/v1`.
4. If Render's format turns out to differ (e.g. the client is the left-most entry and Render does
   not append), keep `TRUSTED_PROXY_HOPS=0`: browsers are still separated by session; only
   cookie-less traffic would share or mis-key its network bucket.

### Secrets in errors (A19)

`Settings` sets `hide_input_in_errors=True`; a test proves a production misconfiguration error does
not contain the database password or host.

### Configuration and repository

- `render.yaml`: readiness health check, `VOLTERRA_SESSION_SECRET` (`generateValue: true`),
  `VOLTERRA_SCENARIO_ACCESS=session`.
- `.env.example`: the new variables (commented, no values).
- `.gitignore`: `project_report/` and `presentation/`.
- `backend/openapi.json` and `frontend/src/api/schema.d.ts` regenerated: **additive only**
  (133 lines added, 0 removed: the two health paths and new 403/409 responses).

## 5. Evidence (2026-11-17)

Development database fingerprint (read-only transaction), before and after all tests: see the
table at the end of this section.

| Check                                                                                              | Result                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| -------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend full suite, final after R1/R2 (incl. PostgreSQL tests on disposable `volterra_test_*` DBs) | **726 passed, 0 failed, 0 skipped, 8 xfailed** (strict F1–F8); coverage 97.99 % (before R1/R2: 721 passed)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ruff, ruff format, mypy (strict, 154 files)                                                        | clean                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Frontend Vitest with coverage                                                                      | **26 files, 254 passed** (incl. Models empty state and CSRF header); 98.61 % statements                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Frontend ESLint, `tsc -b`, API-types check, Prettier                                               | clean (exit 0)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| OpenAPI and frontend types up to date (`check-api-types`)                                          | match                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Production rehearsal: migrations 0001→0005 + seed + second seed                                    | exit 0; "Already seeded" on the second run                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Second production start on the same database (migrate + seed)                                      | **identical** before/after: 1 dataset (`synthetic-v1`), 1 battery, 320 cycles, 0 duplicate (battery, cycle) rows, 0 dataset files, 0 model runs/predictions, revision 0005                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Synthetic checksum, rehearsal vs development                                                       | identical (`8b21acca…5c136214`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Readiness with PostgreSQL unreachable (live, port 1)                                               | `/health/live` 200; `/health/ready` **503** `not_ready`; `/health` 200 + `unavailable`; fake password absent from logs                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| HTTP smoke test (production mode, through the frontend proxy)                                      | no CSRF header → 403; foreign `Origin` → 403; saves 1–4 → 201, 5th → **409**; cookie `HttpOnly; SameSite=lax; Secure; Path=/api/v1`; browser A sees 4, browser B 1, anonymous 0; B deleting A's scenario → **404**; A deleting it → 204; 20 kB body → **413**; security headers present                                                                                                                                                                                                                                                                                                            |
| Concurrency (PostgreSQL test)                                                                      | 12 simultaneous saves by one session with 1 existing → exactly 3 × 201, 9 × 409; 15 simultaneous new sessions with total limit 10 → exactly 6 × 201, 9 × 409; 10 rows                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Session tests (memory + PostgreSQL)                                                                | ownership isolation; 5 forged/tampered cookie forms rejected; CSRF header/origin; production `Secure`; read-only mode; total limit                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| Rate-limit tests (`backend/tests/api/test_hardening.py`)                                           | request classes; session cookie issued on the first API response (not on health) and used for ownership; two sessions behind one shared address have independent allowances; cookie-less requests with rotating client-supplied `X-Forwarded-For` entries or forged cookies share one network allowance; simulations use only the calculation budget (per client and all clients) while scenario writes keep their limits; create/rename/delete share the write limit; all-clients write limit across sessions; defaults exceed the simulator's 150 ms debounce rate; window reset; bounded memory |
| Live write concurrency (production mode, through the proxy)                                        | 1 save + 12 simultaneous saves on one session → session holds **exactly 4**; 8 × 409 (1 × 429 from the per-client write budget)                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Live R1 (after the fix)                                                                            | one browser session: **150 rapid simulations → 150 × 200**, then a scenario save → 201 (write budget untouched)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Live R2 (after the fix)                                                                            | browser A: 1 save + 29 renames allowed, then 429; browser B **on the same address**: save 201, simulation 200; A still 429. Session cookie `Secure; HttpOnly; SameSite=lax; Path=/api/v1` on the first API response                                                                                                                                                                                                                                                                                                                                                                                |

### 5a. Playwright against the hardened production-mode rehearsal

Production build (`vite build`, served by `vite preview`, whose `/api` proxy stands in for the
Vercel rewrite) + API with `VOLTERRA_ENV=production` (session scenarios, rate limits on, random
session secret, no data directory) on a throwaway `volterra_test_*` database with synthetic-v1
only:

| Run                     | Passed  | Failed | Failures                                                 |
| ----------------------- | ------- | ------ | -------------------------------------------------------- |
| Before fixes            | 88      | 17     | 4 baseline + 13 Models-page regressions (§3)             |
| **After fixes (final)** | **101** | **4**  | the **4 baseline** tests only (CI-only fixture data, §3) |

All 13 regressions are resolved; the scenario lifecycle and four-scenario browser tests pass in
`session` mode. The 4 baseline tests need generated real-style data that only CI imports; they
pass in CI and are not failures of the application. **No real data was imported.**

### 5b. Databases touched

| Database                     | Use                                      | State now             |
| ---------------------------- | ---------------------------------------- | --------------------- |
| `volterra` (development)     | read-only fingerprints only              | **unchanged** (below) |
| `volterra_test_08f4f2f06439` | first rehearsal                          | dropped               |
| `volterra_test_8de3c54187a0` | hardened rehearsal                       | dropped               |
| `volterra_test_*` (pytest)   | created and dropped by the test fixtures | none left             |

| Development DB (read-only)              | Before              | After               |
| --------------------------------------- | ------------------- | ------------------- |
| datasets / batteries                    | 4 / 182             | 4 / 182             |
| cycles                                  | 133,752             | 133,752             |
| scenarios (with owner)                  | 3 (0)               | 3 (0)               |
| ml_models / ml_predictions              | 8 / 11,982          | 8 / 11,982          |
| Alembic revision                        | 0005                | 0005                |
| synthetic checksum                      | `8b21acca…5c136214` | `8b21acca…5c136214` |
| cycles fingerprint (md5 of id:capacity) | `2f84d45c…37596`    | `2f84d45c…37596`    |

## 5c. Readiness verdict

All critical security and reliability findings (A5–A8, A17, A19, A20) are fixed and verified; no
regression remains. **Ready for hosting setup**, subject to the owner's review and the decisions
in §6. Configuration items A11 and A12 are completed once the service URLs exist.

## 6. Owner decisions before deployment

1. **Model run in production.** With synthetic data only, the Models page shows "No model run
   imported" and the ML RUL panels do not appear (the trend-based RUL on the Overview works).
   Importing run `48194befb681` would add only aggregate metrics (already public in
   `docs/models/README.md`); predictions are stored only for batteries present, i.e. none. Not
   done without your decision.
2. **Scenario mode.** `session` (default, recommended) or `disabled` (fully read-only demo).
3. **Hosting accounts.** Render and Vercel accounts are needed to create the services; neither
   CLI is installed and no credentials are available to me.

## 7. Remaining risks and limitations

- Rate limits are **in memory and per process** (see §4); with more instances or workers, or
  after a restart, they do not aggregate. Durable protection of stored data comes from the
  database limits. The free plan runs one instance with one uvicorn worker.
- **Cookie-less traffic shares network allowances.** Requests without a session (scripts, a
  browser's very first requests) are keyed by the right-most `X-Forwarded-For` entry; through the
  Vercel rewrite that is a shared Vercel edge address, so heavy cookie-less traffic through one
  edge could delay other visitors' first page load on that edge (read limit 1,200/min per
  address). Browsers with a session are unaffected.
- **Forwarded-header chain is documented by community reports, not official Render
  documentation.** `VOLTERRA_TRUSTED_PROXY_HOPS` stays 0, the safe value for the reported
  behaviour; the deployment-time checks in §4a confirm it.
- A visitor can still use up the all-clients limits (calculations 3,000/min, stored writes
  120/min) for everyone during that minute; that is their purpose (bounding CPU and storage).
- Anyone can create anonymous sessions; the per-session limit (4) and the total limit (1,000)
  bound storage, and the write rate limits bound speed, but a determined client can fill the total
  limit over time (then saving answers 409 until rows are deleted).
- Single database role on Render's free PostgreSQL: the application role also runs migrations
  (least-privilege separation is not available on that plan without manual role management).
- Free PostgreSQL **expires after 30 days** (then a 14-day grace period); no backups. Upgrade or
  recreate before then. Free web service sleeps after 15 min idle (about 1 min cold start;
  Vercel's proxy waits up to 120 s).
- API documentation is public (contract already public in the repository).
- ECharts 5.6 moderate advisory (tooltip HTML), mitigated by the escaping formatter; upgrade to 6
  remains a follow-up.
- No Content-Security-Policy yet (inline theme script needs a hash).
