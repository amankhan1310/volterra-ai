# frontend

React 19 + TypeScript single-page app (Vite 8, React Router 7, TanStack Query 5) that replaces
the prototype in [`../legacy/`](../legacy/) while keeping its design system. It reads everything
from the FastAPI backend; it never re-implements analytics and has no runtime mock data.

**Status:** Phase 4, Milestone 1: application shell, navigation, dark theme, API client and
API/database status. The six pages are labelled placeholders until their milestones
(Overview M2, Digital Twin M3, Simulator M4, Anomalies + Advisor M5, About M6). See
[`../ARCHITECTURE_PLAN.md`](../ARCHITECTURE_PLAN.md) §10 and
[`../PROJECT_STATUS.md`](../PROJECT_STATUS.md).

## Requirements

- Node **24** (`.nvmrc`: 24.22.3). With nvm-windows: `nvm install 24.22.3` then `nvm use 24.22.3`.
- The backend on `http://127.0.0.1:8000` with a migrated and seeded database (see
  [`../backend/README.md`](../backend/README.md)). Vite proxies `/api` to it, so the browser makes
  same-origin requests. Override the target with `VOLTERRA_API_URL`.

## Commands

```sh
npm ci                    # exact versions from package-lock.json
npm run dev               # http://localhost:5173
npm run lint              # ESLint (type-aware, strict)
npm run typecheck         # tsc -b (strict, noUncheckedIndexedAccess, exactOptionalPropertyTypes)
npm run test              # Vitest + Testing Library + MSW
npm run test:coverage     # with the 85% line and branch gate
npm run build             # type check + production build into dist/
npm run preview           # serve dist/ on http://localhost:4173 (also proxies /api)
```

### API contract

`src/api/schema.d.ts` is **generated** from `../backend/openapi.json`; never edit it.

```sh
npm run api:types         # regenerate after the backend contract changes
npm run api:types:check   # fails if the committed types are out of date (CI runs this)
```

### End-to-end and accessibility tests

Playwright runs against the real API and database. CI downloads Playwright's Chromium. Locally,
use an installed browser instead of downloading one:

```sh
PW_CHANNEL=msedge npm run e2e            # reuses `npm run dev` if it is running
```

`e2e/parity.spec.ts` compares every Overview number with the legacy prototype, so it also needs
`legacy/` served on port 8080 (`LEGACY_URL` overrides the address); CI serves it.

### Test fixtures and review screenshots

```sh
npm run record:fixtures                  # re-record src/test/fixtures from the running API
PW_CHANNEL=msedge npm run review:screens -- <outDir>   # React vs legacy, 5 widths + interactions
```

The screenshot script also needs the legacy prototype served on port 8080
(`python -m http.server 8080 --directory legacy` from the repository root).

## Structure

```
src/
  main.tsx            entry: fonts, tokens, providers, router
  app/                router, layout, page metadata, query client, 404, error boundary
  api/                generated types, typed client (openapi-fetch), error mapping, query hooks
  state/              shared simulator parameters (decision D1)
  styles/             design tokens (legacy redesign values) and global styles
  components/layout/  sidebar, header, status card, page header, context bar, data gate
  components/ui/      Card, Button, Segmented, ProvenanceTag, Note, Stat, InfoTip, Dialog, Toast, states
  components/charts/  ECharts registry and wrapper (own lazy chunk), theme from CSS tokens, sparkline
  features/           pages: overview (M2); the rest are labelled placeholders until their milestone
  test/               Vitest setup, MSW server, recorded fixtures, render helpers
e2e/                  Playwright: shell, overview, legacy parity, responsive, accessibility
scripts/              type drift check, fixture recorder, review screenshots
```

## Rules

- Every analytic value shown carries its provenance (`measured | simulated | fitted | predicted |
assumed`); every page shows the dataset and algorithm version.
- No `innerHTML`, `dangerouslySetInnerHTML`, `prompt()`, `alert()` or `confirm()` (lint-enforced).
- No hard-coded colours in components or charts: use the CSS variables in `styles/tokens.css`.
- MSW fixtures are real API responses and are used by tests only.
