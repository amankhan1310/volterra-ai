# Project status

Progress against the phases in [`ARCHITECTURE_PLAN.md`](ARCHITECTURE_PLAN.md) §10.

| Phase                           | Status      |
| ------------------------------- | ----------- |
| 0. Foundations                  | ✅ Complete |
| 1. Golden fixtures              | ✅ Complete |
| 2. Analytics parity in Python   | ✅ Complete |
| 3. DB + API (parity)            | ✅ Complete |
| 4. React parity                 | ✅ Complete |
| 5. Correctness fixes (F1–F8)    | ✅ Complete |
| 6. Real data                    | In progress |
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

Branch: `feat/backend-db-api` (PR into `main`). Phase 2 was merged as PR #3 (`f6bd10c`). Phase 3
was merged as PR #4 (`00427a6`).

Delivered:

- **Database:** PostgreSQL 16 schema with four tables (`datasets`, `batteries`, `cycles`,
  `scenarios`). Numeric values are `DOUBLE PRECISION`, and SOH is stored as produced by the data
  source.
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

## Phase 4 — React parity frontend (complete)

Plan approved 2026-11-13 (decisions D1–D10 and U1–U8; see the Phase 4 plan review). Six
milestones, each on its own branch and PR, each reviewed live before the next starts:
M1 shell · M2 Overview · M3 Digital Twin · M4 Simulator · M5 Anomalies + Advisor · M6 About,
light theme, responsive and accessibility pass.

Environment: Node 24.22.3 (nvm-windows), uv 0.12.24; `uv lock --check` and
`uv sync --locked --dry-run` were clean.

### Milestone 1 — foundation and application shell (2026-11-13)

Branch: `feat/frontend-shell` (PR into `main`). Docs sync was merged as PR #5 (`f847b80`).

Delivered:

- **Foundation:** Vite 8, React 19, TypeScript 5.9 (strict, `noUncheckedIndexedAccess`,
  `exactOptionalPropertyTypes`), React Router 7, TanStack Query 5, openapi-fetch. Versions are
  pinned exactly and `package-lock.json` is committed; peer dependencies were checked before
  installing and `npm install` reported no conflicts.
- **Design system:** the legacy redesign tokens (dark), global styles and self-hosted Manrope
  (D5). Base components: Card, Button, Segmented, ProvenanceTag, Note, Stat, InfoTip, Dialog,
  Toast, loading/error/empty states.
- **Shell:** sidebar with the legacy groups and icons, collapse to icons, off-canvas drawer below
  860px (closes on navigation, Escape or backdrop; inert while closed), header with breadcrumb,
  quick navigation, data-source pill, notification bell, status card with the API/database status
  dot (U8), page header with Run analysis (D6), data-context bar, skip link, 404 page and error
  boundary. Legacy hash URLs (`/#sim`) redirect to the new routes.
- **API:** types generated from `backend/openapi.json` (drift check), typed client with the API's
  error envelope, query hooks. The shell shows live API data: battery, dataset, algorithm
  version, anomaly count and health. The six pages are labelled placeholders with no data.
- **Shared simulator state (D1):** EOL and initial SOH, starting from the API defaults, with the
  "changed from default" flags for the U1 chips.
- **CI:** `frontend` workflow: type drift, ESLint, `tsc`, Vitest with the 85% line and branch
  gate, build; an E2E job runs Playwright and axe against the real API on PostgreSQL 16 and the
  production build (Chromium downloaded in CI only).

Verification (local; Windows; Node 24.22.3; API on the seeded development database):

- **Unit and component tests:** 88 passed. Coverage: 99.62% lines, 96.19% branches.
- **E2E (Playwright, installed Edge, no browser download):** 34 passed: navigation, live API
  values, toasts, collapse, drawer, failure states, no horizontal scroll at 1440/1180/980/860/
  390 px, and axe (WCAG 2.1 A/AA) with no serious or critical violations on every page. The
  shell suite also passes against the production build (`vite preview`).
- **Static checks:** ESLint and `tsc -b` clean; prettier clean; API types match the contract.
- **Unchanged:** backend, golden fixtures, legacy files and `openapi.json`.

Found while comparing with the prototype: at phone widths the legacy header overflows and its
menu button shrinks to 0px wide, so the drawer cannot be opened. The React header keeps every
control usable at 390px.

### Milestone 2 — Overview (2026-11-13)

Branch: `feat/frontend-overview`. M1 merged as PR #6 (`499917c`) with CI green.

Delivered: the Overview page rebuilt from the API (`summary`, `forecast`, `backtest`,
`insights`, `cycles`, `anomalies`): SOH gauge, condition panel (RUL, fit interval, backtest MAE,
provenance tags), six KPI cards with sparklines, degradation timeline (zoom, Full/Last 120),
insights, telemetry explorer (four channels, flagged points) and the collapsed "About these
results" section (U3). EOL follows the shared simulator state, with the chip when it differs from
the default (D1, U1). ECharts 5.6.0 is lazy-loaded in its own chunk, coloured from the CSS
tokens; every chart has a screen-reader data table. Each card loads and fails independently.

Verification: unit and component tests (126) with coverage above the gate; Playwright and axe
against the real API, including `e2e/parity.spec.ts`, which compares every Overview number and
both chart series with the legacy prototype (CI now serves `legacy/` for it); production build.

Deviations from the prototype: capacity-step events are marked on the SOH line at their cycle
(the prototype plotted their ≈ ±0.3 residuals on the SOH axis); chart legend swatches match the
line colours; the insights subtitle says they come from the API, not "your browser".

### Milestone 3 — Digital Twin (2026-11-13)

Branch: `feat/frontend-digital-twin`. M2 merged as PR #7 (`0a67fe9`) with all checks green.

Delivered: the Digital Twin page from `GET /twin` and `GET /cycles`: isometric pack (module
count from the API, colours from `health_level` / `temperature_band`), Health/Temperature modes,
cycle slider (label updates at once, requests debounced 120 ms, results cached per cycle, last
good state kept with an inline error if a request fails), module selection by mouse, Enter or
Space, Reset view, pack-state panel with provenance and the SOH mini chart with a cycle cursor.

Verification: 140 unit and component tests; 47 Playwright tests including parity with the
prototype at cycles 0, 160, 170 and 319 in both modes; axe and responsive checks; build.

Found in the prototype: the logo's SVG gradient and the twin legend share the id `lg`, so the
legend is written into the gradient: it never appears and the logo icon disappears on that page.
React shows the legend.

### Milestone 4 — What-If Simulator (2026-11-14)

Branch: `feat/frontend-simulator`. M3 merged as PR #8 (`8813e94`).

Delivered: the What-If Simulator from `GET /simulator`, `POST /simulate` and the scenario
endpoints: six sliders defined by the API, writing the shared draft (D1, so EOL and initial SOH
reach Overview and Advisor with the U1 chip); simulations debounced 150 ms, cached by parameters,
last good result kept with an inline error; chart with baseline, current (EOL line and end
bubble) and up to four saved-scenario overlays drawn over the current horizon, as in the
prototype; results with the prototype's text. Saved scenarios are now persistent (database):
save, rename (accessible dialog, 30 characters, U2), duplicate and delete; Save and Duplicate stop
at four (D3). If the scenario list cannot load, saving is disabled and the simulator still works.

Verification: 161 unit and component tests; Playwright for the full scenario lifecycle (tests
delete only the scenarios they create) and parity with the prototype on the defaults and five
presets (including ">5000" and the already-at-EOL case); axe and responsive checks; build.

Deviations: when both sides start at EOL the prototype printed "(NaN%)"; this shows "(n/a)".
Saved scenarios persist instead of resetting on reload (plan item B10).

### Milestone 5 — Anomaly Detection and Charging Advisor (2026-11-14)

Branch: `feat/frontend-anomalies-advisor`. M4 merged as PR #9 (`88834f6`) with all checks green.

Delivered:

- **Anomaly Detection** from `GET /anomalies` and `GET /cycles`: events-flagged summary with the
  severity rule taken from the detector settings and a provenance tag; three-lane timeline whose
  event dots are focusable, with a tooltip on hover or keyboard focus (the prototype had a native
  title only); temperature and voltage charts with flagged points, each with a per-cycle
  screen-reader table; the detected-events table (prototype formatting, scrolls inside its card
  on a phone) and the prototype's empty state.
- **Charging Advisor** from `GET /advisor?eol_pct&start_soh_pct`: baseline card and six diverging
  bars with the prototype's geometry, numbers and colours. EOL and initial SOH follow the shared
  simulator state, with a chip for each when it differs from the default (D1, U1). When cycles
  to end of life cannot be compared, v1 reports 0%; a plain-language chip says so (D4), once on
  the baseline when the initial SOH is already at or below the threshold, otherwise on the row.
- **"About these results"** is now a shared component (`ResultNotes`), used by Overview,
  Anomalies and Advisor: plain-language limits, collapsed, no defect codes (U3, D4).
- Fixtures: the Advisor at the defaults, at EOL 70% from 90% SOH, and at EOL 90% from 85% SOH
  (the real at-end-of-life case), recorded from the API.

Fixed across the app (found during the responsive review):

- Visually hidden chart tables laid out at full height (a table treats `height` as a minimum), so
  the document scrolled thousands of pixels into empty space on the Overview (since M2) and on
  Anomalies. The hiding now sits on a wrapper, and `<main>` is the containing block. The
  responsive suite now checks, on every page at every width, that no hidden element takes up
  space and that the document itself never scrolls vertically.
- The timeline is drawn at its measured width, so its labels stay readable on a phone (the
  prototype's fixed drawing shrank them to about 5 px).
- Unit tests: under the full parallel run with coverage, the first test of a file can wait for a
  cold page import beyond the 3 s wait; `asyncUtilTimeout` is now 10 s and `testTimeout` 15 s.
  Only the waiting changed, not what the tests check.

Verification (local; Windows; Node 24.22.3; API on the seeded development database):

- **Unit and component tests:** 193 passed. Coverage: 99.14% statements, 93.14% branches.
- **E2E (Playwright, installed Edge):** 71 passed against the dev server and 71 against the
  production build (`vite preview`), including parity with the prototype for every Anomaly
  Detection value (counts, rule, timeline lanes and severities, events table, both chart series)
  and for the Advisor on five parameter sets (defaults; EOL 70% from 90% with moved T/C/D to show
  they are ignored; 60% from 100%; 60% from 70%; 90% from 85%), comparing every row's text,
  colour and bar geometry; axe (WCAG 2.1 A/AA) and the responsive checks at 1440/1180/980/860/390.
- **Static checks:** ESLint and `tsc -b` clean; prettier clean; API types match the contract.
- **Unchanged:** backend (405 passed, 8 strict xfail; mypy clean), golden fixtures, legacy files
  and `openapi.json`.

Deviations from the prototype: full lane names on the timeline (the prototype cut them to five
letters); chart legends name the channel with its unit, in the line's colour; event tooltips add
the severity.

### Milestone 6 — About, light theme, responsive and accessibility pass (2026-11-15)

Branch: `feat/frontend-about-polish`. M5 merged as PR #10 (`3f6c5ca`) with all 10 checks green.
The light-theme design was previewed on the running app and approved before it was built.

Delivered:

- **About** from the API (battery record and fit range): the prototype's Data, Method,
  "Simulation vs a real EV" and Definitions cards, word for word, plus the known limitations
  F1–F8 in plain language with links to the pages that show them. This is the only page with the
  codes (D4); a unit test keeps the list consistent with the API's `known_issues`. The
  prototype's "Not included" list named a Python backend, which now exists; it lists the later
  phases instead. No page is a placeholder any more, so the placeholder component is removed.
- **Light theme (D2):** dark on a first visit; a sun/moon toggle in the header switches theme and
  the choice is remembered (localStorage), applied before the first paint by a script in
  `index.html`. Text accents meet WCAG AA (4.5:1) on every surface; graphics (chart series, gauge,
  twin, bars, dots, slider thumbs) use the prototype's brighter light accents (3:1, WCAG 1.4.11)
  through `-fill` tokens and a `.graphic` scope. The twin's modules have lighter faces, each
  outlined in the darker shade of its own colour, and keep the strong selection outline. Charts,
  gauge and twin recolour live when the theme changes.
- **Dark theme unchanged,** with one approved exception: the sidebar group labels go from 3.6:1
  to 4.6:1 (`#5d6c82` → `#6e7d93`). A test pins the dark palette to the prototype's values and
  checks that its graphic accents equal its text accents.
- **Gauge caption:** "inner ring: life used to …" crossed both rings in the prototype (and in
  M2); it is now a caption under the dial, readable at every width, in both themes.
- **Contrast checks:** `styles/contrast.test.ts` parses `tokens.css` and checks, in both themes,
  text and accents on every surface (4.5:1), graphic accents (3:1), text on buttons, the badge
  and the chart marker (4.5:1) and the twin module outlines against the plate (3:1).

Verification (local; Windows; Node 24.22.3; API on the seeded development database):

- **Unit and component tests:** 225 passed. Coverage: 99.17% statements, 93.3% branches.
- **E2E (Playwright, installed Edge):** 92 passed against the dev server and 92 against the
  production build: axe (WCAG 2.1 A/AA) on all six pages in both themes, no horizontal or
  document scroll at 1440/1180/980/860/390 px in both themes, the theme suite (first visit,
  toggle, navigation and reload, no flash, rendered text/graphic colours, twin outlines, gauge
  caption position), About parity with the prototype, and every M1–M5 suite.
- **Static checks:** ESLint and `tsc -b` clean; prettier clean; API types match the contract;
  production build clean.
- **Unchanged:** backend (405 passed, 8 strict xfail; mypy clean), golden fixtures, legacy files
  and `openapi.json`.

### Phase 4 Definition of Done

Exit criteria (ARCHITECTURE_PLAN.md §10): the §1.2 checklist passes, Playwright E2E for each page,
the light theme works, no `innerHTML`.

| §1.2 feature                                                                                                           | React                      | Verified by                                         |
| ---------------------------------------------------------------------------------------------------------------------- | -------------------------- | --------------------------------------------------- |
| Overview: SOH gauge with ticks and life-used ring, condition, RUL with interval, fade, backtest MAE                    | ✅                         | parity (every number, both chart series), unit, E2E |
| Overview: six KPI cards with sparklines, degradation timeline (zoom, Full/Last 120), four insights, telemetry explorer | ✅                         | parity, unit, E2E                                   |
| Digital Twin: 24-module isometric pack, cycle slider, Health/Temperature, module lift, pack panel, mini chart          | ✅                         | parity (cycles 0/160/170/319, both modes), E2E      |
| What-If Simulator: six sliders, trajectory vs baseline, cycles to EOL, Δ, fade, four saved scenarios                   | ✅ (scenarios now persist) | parity (6 parameter sets), scenario lifecycle E2E   |
| Anomaly Detection: counts by severity, three-lane timeline, temperature and voltage charts, event table                | ✅                         | parity (every value), E2E                           |
| Charging Advisor: baseline and six sensitivity rows with diverging bars                                                | ✅                         | parity (5 parameter sets), E2E                      |
| About: data, method, limits, definitions, "not included"                                                               | ✅ (list corrected)        | parity, unit, E2E                                   |
| Run analysis with toast                                                                                                | ✅ (a real reload, D6)     | unit, E2E                                           |
| Notification bell with anomaly count                                                                                   | ✅                         | unit, E2E                                           |
| Collapsible sidebar and mobile drawer                                                                                  | ✅                         | E2E at all widths                                   |
| Tooltips reachable by keyboard and touch (prototype: `title` only)                                                     | ✅                         | unit, E2E                                           |
| `prefers-reduced-motion`                                                                                               | ✅                         | global styles                                       |
| Light theme works                                                                                                      | ✅                         | theme E2E, axe in light, contrast test              |
| No `innerHTML`                                                                                                         | ✅                         | lint-enforced                                       |

## Phase 5 — Correctness fixes F1–F8 (2026-11-15)

Branch: `feat/phase-5-analytics-fixes` (one PR). M6 merged as PR #11 (`638aa87`).

Decisions (approved before implementation): v2 is opt-in through the API (`?algorithm=v2`, v1
default, additive contract); F6 uses an interim quadratic over the same 120-cycle window; F3 is a
90% prediction interval calibrated from repeated historical backtests; F2 needs a 0.5 SOH-point
step; F7 defaults to look-back with `mode=causal` for live use; F4 anchors the simulator to the
shared v2 forecast (no acceleration term); F5 uses ratio thresholds 1.2 and 1/1.2; F8 keeps
`delta_pct` (a number) and adds `change_pct` and `comparison`; `algorithm_version` widens to
`"v1" | "v2"`.

Delivered (one commit per defect, details in `CHANGELOG.md`):

| Defect | v1 (unchanged)                            | v2                                                                         |
| ------ | ----------------------------------------- | -------------------------------------------------------------------------- |
| F1     | temperature flags `[170]` only            | detrended robust z: temperature `[90, 170, 251]`, voltage `[130, 271]`     |
| F2     | five false capacity steps                 | step detector (≥ 0.5 SOH pts): none; an injected 1.0-point step is found   |
| F3     | "95% fit interval" 111.5–114.0 (2.6 wide) | 90% prediction interval 92–101; held-out coverage 85.9–88.3%               |
| F4     | Overview 112.7 vs simulator 106           | baseline 97 = round(Overview RUL 96.5)                                     |
| F5     | always "Fade is accelerating"             | accelerating / slowing / steady by explicit ratio rule                     |
| F6     | backtest bias +0.576                      | interim quadratic: bias +0.042                                             |
| F7     | centred window reads future cycles        | `causal` mode: no result can change when later data changes                |
| F8     | 0% when not comparable                    | `change_pct: null` with `comparison` (`at_or_below_eol`, `beyond_horizon`) |

- The API exposes v2 with `?algorithm=v2` on the eight analytics endpoints; `context`
  says which algorithm produced a response. v2-only fields are omitted from v1 responses.
- `CHANGELOG.md` records each fix; the golden README no longer says the fixtures change.

Limitations (documented in the code, the changelog and the API descriptions):

- The v2 forecast is an **interim quadratic**, not a production-validated model: it matches the
  synthetic generator's shape by construction and can extrapolate badly on real cells. Phase 7
  must replace it after validated model comparison on held-out cells.
- The F3 interval is calibrated from this battery's own history; it does not establish coverage
  across batteries (needs held-out cells, Phase 6–7). Bounds beyond the calibrated horizon (171
  cycles here) are reported as unknown. **Accepted limitation (reviewed 2026-11-15):** coverage
  falls short of 90% because forecast errors grow over a cell's life (calibration on earlier
  origins understates later errors), mostly at 11–50-cycle horizons (81–85%); short horizons are
  92–95%. Later split points, not covered by the test, give 84.5% (origin 210) and 85.4% (230),
  just under the 85% target. The calibrated horizon is the cycle count − 149 (120-cycle window,
  at least 30 backtests per horizon). Phase 7 replaces this with conformal calibration across
  held-out cells.
- Causal anomaly detection needs about 80 cycles of history before it judges a cycle.
- The simulator's stress coefficients stay assumed (fitting them is Phase 8).
- The frontend still shows v1; switching the UI to v2 is a separate, later decision.

Verification (local; Windows; Python 3.10.11; PostgreSQL 16):

- **Backend:** 542 passed, 8 xfailed. The 8 are the strict F1–F8 tests for v1, which must keep
  failing. Coverage 99.77% (all new modules 100%). ruff, ruff format and strict mypy clean.
- **Parity:** the golden fixtures and the legacy prototype are unchanged; the parity suites,
  `export_golden.js --check` and the exporter tests pass.
- **Contract:** `openapi.json` regenerated; an OpenAPI diff found no removed or newly required
  fields. Every frontend fixture re-recorded from the API on PostgreSQL is byte-identical, so v1
  responses are unchanged.
- **Frontend:** types regenerated with no code change; 225 unit tests and 93 Playwright tests
  (including prototype parity, axe in both themes and responsive checks) pass against the
  Phase 5 API; production build clean.

Merged as PR #12 (`4499411`, 2026-11-15). Post-merge verification on `main` passed: backend 542
passed + 8 strict xfail (99.96% coverage), 225 frontend unit and 93 Playwright tests, build,
golden fixtures; all GitHub Actions workflows green for the PR and the merge commit.

## Phase 6 — Real battery datasets (in progress)

Decisions (approved 2026-11-15; `ARCHITECTURE_PLAN.md` §9–10 still apply):

| #   | Decision                                                                                                                                          |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | SOH = measured capacity / **rated** capacity (NASA 2.0 Ah, CALCE CS2 1.1 Ah and CX2 1.35 Ah, Severson 1.1 Ah); the basis is stored per battery.   |
| D2  | `cycles` holds one row per capacity-bearing cycle (discharge for NASA/CALCE, full cycle for Severson); charge and impedance data stay in Parquet. |
| D3  | Missing measurements stay null (migration `0002` relaxes NOT NULL); analytics return 422 `missing_measurement` instead of imputing.               |
| D4  | v1/v2 run unchanged on real cells where the data suffices (≥ 221 cycles), labelled "not validated on real cells"; otherwise 422 and data views.   |
| D5  | User upload, column mapping and the job runner are deferred to a later "6b"; curated datasets are imported by CLI.                                |
| D6  | `volterra_ml` parses into Parquet bundles; the backend only adds `pyarrow`; no uv workspace yet.                                                  |
| D7  | Own validation rules plus pyarrow schemas instead of pandera.                                                                                     |
| D8  | Raw and processed data are never committed or redistributed; CI uses generated fixtures only.                                                     |
| D9  | Datasets are downloaded to the developer machine (Severson only after explicit approval).                                                         |
| D10 | Severson: import all 124 cells and flag the paper's exclusions.                                                                                   |
| D11 | Battery selection by URL parameter, synthetic battery as the default.                                                                             |
| D12 | F3 stays an acknowledged limitation (see Phase 5) until Phase 7.                                                                                  |

Milestones: **M1** acquisition and provenance · M2 canonical schema and NASA loader · M3 database
and importer · M4 CALCE and Severson loaders · M5 API · M6 React.

### Milestone 1 — Dataset acquisition and provenance (2026-11-15)

Branch: `feat/phase-6-m1-dataset-acquisition`.

- **Sources verified** against the publishers' own pages, with cards in
  [`docs/datasets/`](docs/datasets/README.md): NASA PCoE (licence "not specified"), CALCE CS2/CX2
  ("All Rights Reserved" plus a citation requirement), Severson et al. 2019 (CC BY 4.0, declared
  by data.matr.io). Chemistry is recorded only where the publisher states it (not for NASA).
- **Acquisition tool** `python -m volterra_ml.acquisition` (`ml/volterra_ml/acquisition/`,
  standard library only): `list`, `download` (resume, retries, verification before a file is
  kept, read-only raw files, `--from-dir` for hand-downloaded files) and `verify` (re-hashes
  every file against `MANIFEST.json` and the registry pins). It refuses to write anywhere Git
  could track.
- **Downloaded and pinned** (16 files, 9.17 GB, in `D:\volterra\data` = `VOLTERRA_DATA_DIR`, each
  dataset with a `MANIFEST.json`): NASA (1 archive, 209.7 MB, 34 cells) and CALCE (12 archives,
  695.1 MB), every zip passing its CRC check; Severson (3 MATLAB 7.3/HDF5 files, 8.27 GB,
  downloaded with approval under CC BY 4.0, sizes equal to the host's metadata). `verify --all`
  re-hashes all 16 files against the manifests and the pinned SHA-256 values.
- **CI:** new `ml` workflow (Python 3.10 and 3.12: ruff, strict mypy, pytest with an 85% coverage
  gate); `test_repository_hygiene.py` fails if any dataset file is tracked. No test downloads
  data.
- Nothing in `backend/`, `frontend/` or the database changed.

Merged as PR #13 (`b88c2c2`).

Development environment: since 2026-11-15 the project lives in `D:\volterra\project` and the data
in `D:\volterra\data` (copy-first migration, verified file by file; the earlier copy is kept as a
backup).

### Milestones 2 + 3 — Canonical schema, NASA loader, database and importer (2026-11-15)

Branch: `feat/phase-6-m2-m3-schema-nasa-import` (M2 and M3 combined, as approved).

- **Canonical schema v1** ([`docs/datasets/canonical-schema.md`](docs/datasets/canonical-schema.md)),
  defined once in `ml/volterra_ml/canonical/columns.py` and checked against the backend importer
  by a contract test. Every measurement is nullable and never zero-filled; source identifiers
  (cell id, position in the source file, archive members with SHA-256) are kept; SOH references
  the rated capacity (D1) and each battery records its first measured capacity; one canonical
  cycle per discharge (D2). Deterministic validation flags (capacity missing/zero/above rated,
  capacity jumps, voltage or temperature out of range, non-finite or unordered samples, unequal
  arrays, complex impedance fits) mark data without changing or removing it.
- **NASA loader** (`python -m volterra_ml.loaders build nasa-pcoe-battery`), written after
  inspecting the real files: MATLAB 5.0, B0025–B0028 duplicated byte for byte (one copy
  converted, both recorded), field names that differ from the published description, per-cycle
  ambient temperature, 25 empty capacities, 19 zero capacities and 9 complex `Re`/`Rct` fits.
  It verifies the raw archive first and writes a deterministic Parquet bundle (34 batteries,
  2,794 discharge cycles, every charge/discharge sample and impedance record) in about 20 s;
  a rebuild is byte-identical. Every capacity and every sample of all six channels matches the
  source bit for bit (local real-data tests).
- **Database (migration `0002`, additive):** `dataset_files` plus provenance columns on
  `datasets`, `batteries` and `cycles`; all nullable, so the synthetic data is untouched and a
  downgrade restores the Phase 3 schema exactly. The NOT NULL relaxation of the analysis inputs
  waits for CALCE (M4), which needs it; NASA discharges always have them.
- **Importer** (`python -m app.db.import_dataset`): verifies the bundle, checks columns and rows,
  imports in one transaction, is idempotent, updates batteries in place (scenarios kept), refuses
  to delete batteries or overwrite another source, and records every raw and processed file with
  a relative path and SHA-256. Only cycles with every analysis input are inserted (2,769 of
  2,794); the rest stay in Parquet with their flags.
- **End to end on real data:** raw NASA archive → loader → bundle → disposable PostgreSQL
  database: 34 batteries and 2,769 cycles imported, every value equal to the bundle, flags
  preserved, re-import a no-op. The development database was not changed: real batteries would
  reorder the API's battery list (the frontend opens the first one), so importing into it waits
  until the API and UI are real-data aware (M5/M6).
- No NASA cell reaches the 221 cycles the v1/v2 analytics need (maximum 197), so all NASA cells
  will get data views only (D4).
- Dependencies: `numpy`, `scipy`, `pyarrow` in `ml/`; `pyarrow` in `backend/` (D6).

## Next

Phase 6 M4 (CALCE and Severson loaders), only after the M2+M3 review and with approval.
