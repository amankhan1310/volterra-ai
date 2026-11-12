# Project status

Progress against the phases in [`ARCHITECTURE_PLAN.md`](ARCHITECTURE_PLAN.md) §10.

| Phase                           | Status      |
| ------------------------------- | ----------- |
| 0. Foundations                  | ✅ Complete |
| 1. Golden fixtures              | ⏳ Next     |
| 2. Analytics parity in Python   | Not started |
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

## Next

Phase 1: Node exporter (`legacy/tools/export_golden.js`) that writes the prototype's dataset
and analytics outputs to JSON fixtures for the Python parity tests.
