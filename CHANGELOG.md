# Changelog

Notable changes to VOLTERRA AI's analytics. Algorithm versions are explicit: **v1** reproduces the
original prototype exactly (including the known defects F1–F8 in `ARCHITECTURE_PLAN.md` §3.6),
is permanent, and stays the API default. **v2** holds the corrected methods. The golden fixtures
in `backend/tests/golden/` describe v1 and are never modified.

## [Unreleased] — Phase 8: simulator evidence and baseline validation

No analytics change: v1 and v2 simulator outputs are unchanged (fixtures re-recorded, zero diff).

- `python -m volterra_ml.calibration` (evidence for the assumed stress coefficients, bootstrap
  CIs) and `python -m app.validation.simulator_baseline` (the simulator baseline against real
  Severson life); results committed in `backend/app/evidence/` (aggregates only).
- `GET /api/v1/simulator/evidence`; Simulator evidence card and out-of-range notes; the Digital
  Twin shows the experimental RUL panel for real batteries.

## [Unreleased] — Phase 7: experimental ML models

No v1 or v2 analytics change; existing API responses are unchanged (fixtures re-recorded with zero
diff). See `docs/models/README.md`.

- `python -m volterra_ml.modeling run`: battery-wise evaluation of RUL, SOH-forecast and SOH
  estimation models (baselines, ridge, LightGBM) with split-conformal intervals; run outputs stay
  outside git.
- Migration `0005` (additive): `ml_models`, `ml_predictions`; `python -m app.db.import_models`.
- API: `GET /models`, `GET /batteries/{id}/rul-predictions` (provenance `predicted`, 90 % interval,
  held-out/in-sample split).
- Frontend: Models page; experimental RUL panel on Battery Data.
- ml dependencies: scikit-learn, lightgbm.

## [Unreleased] — Phase 6 M5 + M6: real-data API and frontend

No v1 or v2 analytics change: synthetic-v1 responses are unchanged (fixtures re-recorded; only the
new optional fields were added). The development database is unchanged (still migration 0002).

- Migration `0004`: `cycles.temp_mean_c` and `voltage_mean_v` become nullable. Its downgrade
  refuses while nulls exist (it never deletes). The importer now imports every cycle with a
  measured capacity and SOH, except sample-less placeholders (`empty_samples`); missing
  temperature or voltage stays null and is never filled in.
- API: batteries report `analysis {available, reason, message, min_cycles}`, `flags` and
  incomplete/flagged cycle counts; cycles expose nullable temperature/voltage, internal
  resistance, charge time and quality flags; analytical contexts carry a `note` for real cells
  (not validated on real cells). Analytics on a battery without the inputs they need return 422
  `missing_measurement` or `insufficient_data` instead of guessing.
- New `GET /batteries/{id}/cycles/{cycle}/samples?max_points=` (deterministic downsampling, first
  and last samples kept; 422 `no_samples`, 404 `cycle_not_found`, 503 `samples_unavailable`)
  reading the bundle files under the new `VOLTERRA_DATA_DIR` setting.
- Frontend: battery selection by URL (`?battery=<dataset>:<external_id>`, synthetic default),
  header battery selector, limitation states that show the API's reason, and a new
  **Battery Data** page (per-cycle measured channels with flagged cycles, per-cycle samples).
- CI E2E imports two generated real-style bundles (never real data) through
  `tests.support.fixture_bundles ci-import`, which refuses unless it runs in GitHub Actions
  against the local `volterra_ci` service database, and checks that a re-import is a no-op.

## [Unreleased] — Phase 6 M4: CALCE and Severson loaders, canonical schema v2

No analytics, API or frontend change; the development database is unchanged.

- Canonical schema v2: nullable cycle columns `internal_resistance_ohm`, `charge_time_s`,
  `source_ref_json`; migration `0003` adds `cycles.source_ref` (JSONB) and the importer persists it.
- `python -m volterra_ml.loaders build calce-cs2-cx2` (12 cells, 15,971 cycles) and
  `build severson-2019` (135 cells: 5 continuations joined, 11 paper-excluded flagged; 114,738
  cycles). The NASA bundle is rebuilt under v2.
- The importer refuses over-long text fields before writing (database column limits).

## [Unreleased] — Phase 6 M2 + M3: canonical schema, NASA loader, database and importer

No analytics, API or frontend change; the development database is unchanged.

- Canonical battery-data schema v1 (`docs/datasets/canonical-schema.md`) with deterministic
  validation flags; missing measurements stay null.
- `python -m volterra_ml.loaders build nasa-pcoe-battery`: verified NASA archive → deterministic
  Parquet bundle (34 cells, 2,794 discharge cycles, all samples and impedance records).
- Migration `0002` (additive): `dataset_files` table; provenance columns on `datasets`
  (`publisher`, `landing_url`, `doi`), `batteries` (`chemistry_basis`, `soh_reference`,
  `soh_reference_capacity_ah`, `first_capacity_ah`, `first_capacity_cycle_index`) and `cycles`
  (`source_cycle_index`).
- `python -m app.db.import_dataset`: verified, transactional, idempotent bundle import.

## [Unreleased] — Phase 6 M1: dataset acquisition and provenance

No analytics, API, database or frontend change. New tooling only:

- `python -m volterra_ml.acquisition` downloads, verifies and records the real datasets (NASA
  PCoE, CALCE CS2/CX2, Severson 2019) with a `MANIFEST.json` per dataset and pinned SHA-256
  checksums; see `docs/datasets/`.
- New CI workflow `ml`; a repository-hygiene test fails if a dataset file is ever tracked.

## [Unreleased] — Phase 5: corrected v2 analytics (opt-in)

### API: opt-in `?algorithm=v2`

- New optional query parameter `algorithm` (`v1` default, or `v2`) on `summary`, `forecast`,
  `backtest`, `insights`, `anomalies`, `simulator`, `simulate` and `advisor`; `anomalies` also
  takes `mode` (`retrospective` default, or `causal`, v2 only: `mode=causal` with v1 returns 422
  `unsupported_mode`). v2 responses say `context.algorithm_version: "v2"` and `known_issues: []`.
- **Additive and backward compatible.** v1 responses are unchanged byte for byte (all frontend
  fixtures re-recorded from the API are identical). New response fields are optional and appear
  only in v2 responses: `Interval.label` / `max_calibrated_horizon_cycles`,
  `LinearFitOut.curvature` / `origin_cycle`, `BacktestResponse.mean_signed_error`,
  `AnomalyMethodOut.step_window` / `min_step_soh_pct` / `causal_fit_window` /
  `causal_min_history`, `ChannelStatsOut.cycles`, `AdvisorRowOut.change_pct` / `comparison`.
  The one widened type is `AnalysisContext.algorithm_version` (`"v1"` → `"v1" | "v2"`).
- The frontend keeps using v1; only its generated types changed.

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
- **Accepted limitation (reviewed after merge).** Coverage is below 90% because forecast errors
  grow over the cell's life, so quantiles from earlier origins understate later errors (mostly
  at 11–50-cycle horizons). Later split points give 84.5% (origin 210) and 85.4% (230). Phase 7
  replaces this with conformal calibration on held-out cells.
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

### F2 — No false capacity steps, and real steps are still detected

- **v1 (unchanged):** robust z of the SOH residual from a centred rolling median. No steps are
  injected in `synthetic-v1`, yet cycles 125, 127, 254, 315 and 319 are flagged (|residual|
  0.32–0.36 SOH points vs noise of about 0.11; 315 and 319 are truncated-window edge effects).
- **v2:** a capacity-step detector: the median of the next 10 cycles minus the level a robust
  (Theil–Sen) line through the previous 10 cycles predicts. A step must be at least **0.5 SOH
  points** (about 4.6× the noise) and have robust |z| > 3.5; one event per step. Cycles without
  10 cycles on each side are not evaluated. Result: nothing flagged on `synthetic-v1`; an
  injected sustained 1.0-point step is found once, within 4 cycles of its onset, wherever it is
  placed (tested at cycles 60–300); a 0.3-point step is not reported.
- Note: a rolling-median residual (v1) cannot see a sustained step at all, so the v2 channel
  measures level changes ("Capacity step", unit SOH pts).
- Regression test: `backend/tests/v2/test_f2_capacity_steps.py`.

### F7 — A live (causal) detection mode that never reads future cycles

- **v1 (unchanged):** the capacity residual uses a window centred on each cycle, so it reads
  later cycles. That suits reviewing history but not live alerting.
- **v2:** `detect_anomalies_v2(records, mode=...)` has two modes. `retrospective` (the default,
  for looking back over history) uses the centred windows. `causal` (live) judges every cycle
  from cycles up to and including it only: point channels compare each value with a Theil–Sen
  line through the previous 15 cycles; a capacity step is judged once the 10 cycles after its
  onset have arrived and is reported at that detection cycle; the robust scale comes from earlier
  statistics only, and a cycle needs 60 earlier statistics before it is judged.
- Verified: rewriting every channel after cycle _k_ leaves every causal event, input and z-score
  at or before _k_ unchanged (tested at _k_ = 80–318). Causal mode on `synthetic-v1` finds the
  injected temperature and voltage anomalies and no false steps; an injected 1.0-point step is
  reported within 10 cycles after it happens.
- Limitation: causal mode needs about 80 cycles of history before it can judge a cycle.
- Regression test: `backend/tests/v2/test_f7_causal.py`.

### F5 — The fade insight follows the numbers

- **v1 (unchanged):** the second insight always says "Fade is accelerating", whatever the slopes.
  (Dormant on `synthetic-v1`, where fade really did accelerate, but wrong for slowing fade.)
- **v2:** `app/analytics/insights_v2.py` classifies the current fade against the first-half fade
  with one explicit rule: ratio above 1.2 → **accelerating** (kind `watch`), below 1/1.2 →
  **slowing**, otherwise **steady**. The Overview acceleration note uses the same rule, so the two
  cannot disagree. The model insight describes the interim quadratic forecast and its bias.
- Regression test: `backend/tests/v2/test_f5_insights.py` (one test per rule, including the
  boundaries).
