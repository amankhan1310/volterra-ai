# Changelog

Notable changes to VOLTERRA AI's analytics. Algorithm versions are explicit: **v1** reproduces the
original prototype exactly (including the known defects F1–F8 in `ARCHITECTURE_PLAN.md` §3.6),
is permanent, and stays the API default. **v2** holds the corrected methods. The golden fixtures
in `backend/tests/golden/` describe v1 and are never modified.

## [Unreleased] — Phase 5: corrected v2 analytics (opt-in)

### F6 — The forecast is no longer biased on accelerating fade

- **v1 (unchanged):** a straight line over the last 120 cycles. Fade on `synthetic-v1` is
  quadratic, so the time-ordered backtest over-predicts SOH by +0.576 points on average.
- **v2:** a quadratic over the same 120-cycle window (`app/analytics/forecast_v2.py`). Backtest
  bias +0.042, MAE 0.098 SOH points; RUL to 80% is 96.5 cycles (v1: 112.7), closer to the
  generator's noise-free 92.7.
- **Interim, not production-validated.** A quadratic matches the synthetic generator's shape by
  construction and can extrapolate badly on real cells. Phase 7 must replace it with a model
  chosen by validated comparison on held-out cells.
- Regression test: `backend/tests/v2/test_f6_forecast.py` (|bias| < 0.1).
