# Project status

Progress against the phases in [`ARCHITECTURE_PLAN.md`](ARCHITECTURE_PLAN.md) §10.

| Phase                           | Status      |
| ------------------------------- | ----------- |
| 0. Foundations                  | ✅ Complete |
| 1. Golden fixtures              | ✅ Complete |
| 2. Analytics parity in Python   | ⏳ Next     |
| 3. DB + API (parity)            | Not started |
| 4. React parity                 | Not started |
| 5. Correctness fixes (F1–F8)    | Not started |
| 6. Real data                    | Not started |
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

## Next

Phase 2: port the analytics to Python (`backend/app/analytics`) and test them against these
fixtures. This waits for review and approval.
