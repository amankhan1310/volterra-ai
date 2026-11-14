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

### F3 — The RUL interval reflects the real forecast error

- **v1 (unchanged):** a "95% fit interval" from slope ± 1.96·SE only: 111.5–114.0 cycles (2.6
  wide), although the backtest error implies about ±11 cycles.
- **v2:** a **90% prediction interval** calibrated from repeated historical backtests
  (`rul_interval_v2`): the v2 forecast is refitted at every past origin, its errors are collected
  per horizon, and the 5% / 95% error quantiles bound the forecast. RUL to 80%: 92–101 cycles
  around 96.5; it contains the generator's noise-free 92.7. Bounds beyond the calibrated horizon
  (171 cycles here, the last horizon with at least 30 backtests) are reported as unknown.
- **Calibration uses this battery's own history only.** Calibrated on earlier origins and scored
  on later ones, coverage is 85.9–88.3% (target 85–95%). This does **not** establish coverage
  across batteries; that needs held-out cells (Phase 6–7).
- Regression test: `backend/tests/v2/test_f3_interval.py`.

### F4 — Overview and Simulator agree on the same conditions

- **v1 (unchanged):** the Overview says 112.7 cycles to 80% and the simulator baseline (same
  25 °C / 1C / 80% DoD) says 106, because the simulator adds its own `(1 + n/1500)` acceleration
  term and starts from a rounded SOH.
- **v2:** one source of truth (`app/analytics/simulator_v2.py`). The baseline curve is the shared
  v2 forecast started at the scenario's initial SOH; a scenario runs that curve at its stress
  factor, so its cycles to EOL = baseline cycles × (baseline fade / scenario fade). No separate
  acceleration term, no rounding of the starting SOH. Baseline: 97 cycles = the rounded Overview
  RUL (96.5). Δ% is `null` instead of `NaN` when it cannot be computed.
- The temperature, C-rate and DoD factors stay **assumed**; fitting them is Phase 8.
- Regression test: `backend/tests/v2/test_f4_simulator.py`.

### F8 — The Charging Advisor says when a change cannot be compared

- **v1 (unchanged):** the live prototype rule `n && b ? ((n − b) / b) · 100 : 0`, so a change
  whose cycle count is unknown (beyond 5000 cycles) or whose baseline is already at end of life
  shows **0%**, which reads as "no effect".
- **v2:** `app/analytics/advisor_v2.py` runs the six one-factor changes on the v2 simulator and
  gives each row a `change_pct` that is `null` unless comparable, plus an explicit `comparison`
  state: `comparable`, `at_or_below_eol` or `beyond_horizon`.
- API (with `?algorithm=v2`): `change_pct` and `comparison` are new fields; the existing
  `delta_pct` keeps its v1 meaning and type (a number, 0 when not comparable) for compatibility.
- Regression test: `backend/tests/v2/test_f8_advisor.py`.

### F1 — Temperature spikes on the cool part of the cycle are detected

- **v1 (unchanged):** robust z of the raw values against the whole series. The ±3 °C temperature
  wave inflates the spread, so only one of the three injected spikes (cycle 170) is flagged.
- **v2:** `app/analytics/anomalies_v2.py` removes the slow baseline first (residual from a centred
  15-cycle rolling median), then applies the same robust z (|z| > 3.5, high above 6). Event ranges
  follow the local baseline. Cycles whose window would be truncated at the series edges are not
  evaluated. Result on `synthetic-v1`: temperature 90, 170, 251 and voltage 130, 271, i.e.
  precision and recall 1.0 on the labelled injections (v1 temperature recall 1/3).
- Regression test: `backend/tests/v2/test_f1_anomalies.py`.
