# Deployment progress: VOLTERRA AI public demonstration

| Phase                                  | Status (2026-11-17)                                                                       |
| -------------------------------------- | ----------------------------------------------------------------------------------------- |
| 1. Pre-deployment audit                | Done: `DEPLOYMENT_READINESS.md` §2                                                        |
| 1b. Security and reliability hardening | Done: PR #20 (`fix/deploy-security-hardening`)                                            |
| 1c. Pre-merge review corrections       | Done: R1 (simulator budget) and R2 (per-client identity), `DEPLOYMENT_READINESS.md` §4a   |
| 2. Production configuration            | `render.yaml` / `vercel.json` ready; CORS origin and rewrite URL after the services exist |
| 3. Production database                 | Not started (needs the owner's Render account)                                            |
| 4. Deployment                          | Not started: **no hosting service created**                                               |
| 5. Production validation               | Not started; includes the deployment-time checks in `DEPLOYMENT_READINESS.md` §4a         |

**PR #20 is not merged** and awaits the owner's final review.

## Waiting for the owner

1. Final review and merge decision for PR #20.
2. Decisions in `DEPLOYMENT_READINESS.md` §6 (model run in production; scenario mode).
3. Access to Render and Vercel (accounts; neither CLI is installed here).

## Log

- Audit of `main` = `c782115`; hosting limits checked on render.com and vercel.com (2026-11-17).
- Production rehearsal on a throwaway database: 88/105 E2E; 4 baseline + 13 regressions found.
- Hardening implemented and verified; rehearsal 101/105 (4 baseline only); development database
  unchanged; rehearsal databases dropped.
- PR #20 opened (head `d365b63`): **12/12 GitHub Actions checks passed**, no merge conflicts.
- Read-only pre-merge review: changes requested for R1 (simulations consumed the write budget)
  and R2 (per-client key collapsed to a shared Vercel edge address); everything else approved.
- R1/R2 fixed with regression tests (owner-approved, same branch); see the readiness report §4a
  and §5 for the evidence and the new CI run.
