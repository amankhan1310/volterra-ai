# Phase 7 models: methodology, results and limitations

**Status: experimental.** These models were trained and evaluated offline on three public
laboratory datasets. They are **not production-validated**. Results depend on each dataset's test
protocol and batteries, and two of the three datasets have too few batteries for a stable
held-out estimate. The API and UI label every prediction `predicted`, show its 90 % interval and
say whether the battery was held out.

Code: `ml/volterra_ml/modeling/`. Run: `python -m volterra_ml.modeling run --data-dir <data> --out
artifacts/models/<run>`. Import: `cd backend && uv run python -m app.db.import_models <run-dir>`.
Run directories, model files and every real-data value stay outside git (`artifacts/` is ignored).

## Reference run

|                 |                                                                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Run id          | `48194befb681` (2026-11-16), code `23b513b` (clean tree), code SHA-256 `63c0d855d874…`                                               |
| Data            | NASA PCoE 2022-09-18 (`471c8176…`), CALCE CS2/CX2 2015-08-10 (`eb60aefc…`), Severson 2019-03-11 (`dec6473b…`); data hash `0adea61c…` |
| Libraries       | Python 3.10.11, numpy 2.2.6, scikit-learn 1.7.2, LightGBM 4.7.0 (deterministic, single-thread, seed 7)                               |
| Reproducibility | A second run on the same code and data gave byte-identical `metrics.json`                                                            |

## Tasks

| Task              | Target                               | Inputs at prediction point _n_                                                                                                                                                          | Datasets                                                                     |
| ----------------- | ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| RUL               | cycles from _n_ to the battery's EOL | SOH history up to _n_ (current SOH, fade so far, slopes over the last 10/50/100 cycles, curvature) and recent measured signals (temperature, voltage, internal resistance, charge time) | all three, pooled                                                            |
| SOH forecast      | SOH 50, 100 or 200 cycles after _n_  | as RUL                                                                                                                                                                                  | all three, pooled                                                            |
| SOH estimation    | SOH at cycle _n_                     | measured signals at _n_ only: never capacity, SOH, discharge time or current (at constant current those are capacity in disguise)                                                       | each dataset separately (their sensors differ)                               |
| Cross-dataset RUL | as RUL                               | SOH-history features only                                                                                                                                                               | train and calibrate on Severson; test on every usable CALCE and NASA battery |

## End of life and censoring

- **EOL threshold:** 80 % of rated capacity (SOH reference: rated capacity, decision D1).
- **Source labels first.** Severson et al. document each cell's cycle life (the test ran until
  80 % of nominal capacity by the tester's measure). When a source documents a label, EOL is cycle
  `life − 1` (the source counts from 1), capped at the last recorded cycle.
- **Otherwise, a threshold rule:** the first cycle with SOH ≤ 80 % whose forward 5-cycle median is
  also ≤ 80 %. A single dip that recovers (NASA capacity regeneration) does not count.
- **Censored batteries** never reach EOL in their data: their true RUL is unknown, so they are
  never used as exact targets (they still receive predictions, marked censored).
- **Batteries that start below EOL** (16 NASA cells, which start below 80 % of the 2.0 Ah rating)
  have no remaining life to predict and are not RUL targets.

### Severson cycle-life audit (resolved)

The source `cycle_life` was checked against the per-cycle records of every usable cell
(`tests/modeling/test_modeling_realdata.py` pins the result):

- **b1c0 (1,190 vs 1,850 cycles).** The batch-1 file holds 1,189 summary cycles for b1c0, which
  is still at 93.3 % SOH at their end: the source's 1,190 is where that _recording_ stopped, not
  EOL. The cell continued in batch 2 as **b2c7** for 662 cycles (summary 1–662). Joined, as the
  authors do, that is 1,851 records (index 0–1,850) ending at 80.26 % SOH, and the authors' joined
  life is 1,190 + 662 = **1,852**. The same holds for b1c1 + b2c8 (2,160), b1c2 + b2c9 (2,237),
  b1c3 + b2c15 (1,434) and b1c4 + b2c16 (1,709). The loader records the joined life; the model
  code uses it.
- **Other batch-1 and batch-3 cells.** The source life is the last summary cycle + 1 (e.g. b1c5:
  1,073 → 1,074) and the record ends at 80.0–80.3 % SOH by the per-cycle capacity: the tester
  stopped each cell at its own 0.88 Ah trigger. The label is therefore the last recorded cycle.
- **Batch 2** cells ran past EOL; there the threshold rule and the label agree exactly.
- **Totals:** 124 labelled cells (135 minus the paper's 11 exclusions). The threshold rule finds
  EOL in 43 and agrees with the label to 0 cycles; it finds no crossing in 81, all of which end at
  80.0–80.3 % SOH. Without the labels those 81 cells would have been wrongly censored. A first run
  that did so reported a flattering RUL error of 27 cycles on 8 short-lived test cells; the
  numbers below replace it.

## Evaluation protocol

- **Splits by battery, never by row.** A salted SHA-256 of `<dataset>:<battery>` puts each
  battery's whole history in train (60 %), calibration (20 %) or test (20 %). Tests check that no
  battery appears in two splits.
- **Model choice** uses 5-fold cross-validation over the training batteries, grouped by battery.
  The test batteries are scored once, by the model fitted on the training batteries.
- **No future data.** Every feature at cycle _n_ reads cycles ≤ _n_ only. Tests recompute every
  feature on a copy of the battery truncated after _n_, and on one whose future is scrambled, and
  require identical values.
- **No life leakage through the cycle number.** Prediction rows sit on a fixed grid (every 10
  cycles). Rows at "20 % of life" would carry the life in their cycle number; life fractions are
  used only to report test errors.
- **Equal weight per battery** in training, however many rows a battery contributes.
- **Intervals:** split-conformal 90 % intervals, sized on the calibration batteries per dataset
  (Mondrian) when it has ≥ 3 calibration batteries, otherwise pooled (flagged). RUL intervals are
  multiplicative (log scale). Rows of one battery are correlated, so the conformal guarantee holds
  only approximately; the held-out coverage is reported next to the width.
- **Baselines** every learned model must beat: the recent linear trend (the prototype's method),
  the cohort median life minus the current cycle (RUL), persistence (forecast) and the training
  batteries' median SOH at that cycle (SOH estimation).
- **Metrics:** MAE, RMSE, R² and bias; interval coverage (PICP) and mean width (MPIW); for RUL
  also the share within ±20 % of the true RUL (α-λ accuracy) and errors by life fraction.

## Results (run `48194befb681`)

Battery counts are train/calibration/test. "CV" is out-of-fold over the training batteries, with
the batteries in each fold. "Calibration" is the conformal calibration set (b = batteries,
r = rows). Test numbers on 1 battery are anecdotes, not estimates: read the CV column instead.

#### Remaining useful life (cycles; selected: `lightgbm`)

| Dataset (train/cal/test batteries) | Model               | CV MAE (batteries; fold sizes) | Test MAE | Test RMSE | Test R²  | Coverage | Width | Calibration   |
| ---------------------------------- | ------------------- | ------------------------------ | -------- | --------- | -------- | -------- | ----- | ------------- |
| calce-cs2-cx2 (8/3/1)              | linear_trend        | 516 (8; 1/1/2/1/3)             | 371      | 814       | -28.41   | 0.92     | 2008  | 3 b / 197 r   |
| calce-cs2-cx2 (8/3/1)              | cohort_median       | 75 (8; 1/1/2/1/3)              | 134      | 134       | 0.20     | 0.60     | 406   | 3 b / 197 r   |
| calce-cs2-cx2 (8/3/1)              | ridge               | 217 (8; 1/1/2/1/3)             | 492      | 630       | -16.60   | 0.69     | 1625  | 3 b / 197 r   |
| calce-cs2-cx2 (8/3/1)              | lightgbm **(sel.)** | 59 (8; 1/1/2/1/3)              | 59       | 71        | 0.77     | 0.96     | 609   | 3 b / 197 r   |
| nasa-pcoe-battery (3/4/1)          | linear_trend        | 701 (3; 0/0/0/2/1)             | 16       | 24        | -7.50    | 1.00     | 190   | 4 b / 17 r    |
| nasa-pcoe-battery (3/4/1)          | cohort_median       | 566 (3; 0/0/0/2/1)             | 629      | 629       | -5933.61 | 0.67     | 2995  | 4 b / 17 r    |
| nasa-pcoe-battery (3/4/1)          | ridge               | 138 (3; 0/0/0/2/1)             | 37       | 39        | -21.38   | 0.67     | 216   | 4 b / 17 r    |
| nasa-pcoe-battery (3/4/1)          | lightgbm **(sel.)** | 39 (3; 0/0/0/2/1)              | 7        | 7         | 0.16     | 1.00     | 50    | 4 b / 17 r    |
| severson-2019 (72/30/22)           | linear_trend        | 1422 (72; 15/14/11/14/18)      | 1360     | 1640      | -14.29   | 0.90     | 2339  | 30 b / 2483 r |
| severson-2019 (72/30/22)           | cohort_median       | 286 (72; 15/14/11/14/18)       | 317      | 482       | -0.32    | 0.91     | 2291  | 30 b / 2483 r |
| severson-2019 (72/30/22)           | ridge               | 147 (72; 15/14/11/14/18)       | 197      | 360       | 0.26     | 0.84     | 774   | 30 b / 2483 r |
| severson-2019 (72/30/22)           | lightgbm **(sel.)** | 94 (72; 15/14/11/14/18)        | 92       | 195       | 0.78     | 0.89     | 325   | 30 b / 2483 r |

#### SOH forecast, 50 cycles ahead (SOH points; selected: `lightgbm`)

| Dataset (train/cal/test batteries) | Model               | CV MAE (batteries; fold sizes) | Test MAE | Test RMSE | Test R²   | Coverage | Width  | Calibration   |
| ---------------------------------- | ------------------- | ------------------------------ | -------- | --------- | --------- | -------- | ------ | ------------- |
| calce-cs2-cx2 (8/3/1)              | persistence         | 2.98 (8; 1/1/2/1/3)            | 3.58     | 4.60      | 0.89      | 0.74     | 9.34   | 3 b / 382 r   |
| calce-cs2-cx2 (8/3/1)              | linear_trend        | 2.00 (8; 1/1/2/1/3)            | 2.03     | 2.74      | 0.96      | 0.82     | 6.81   | 3 b / 382 r   |
| calce-cs2-cx2 (8/3/1)              | ridge               | 3.23 (8; 1/1/2/1/3)            | 3.62     | 4.27      | 0.90      | 1.00     | 43.13  | 3 b / 382 r   |
| calce-cs2-cx2 (8/3/1)              | lightgbm **(sel.)** | 2.76 (8; 1/1/2/1/3)            | 1.87     | 2.65      | 0.96      | 1.00     | 31.26  | 3 b / 382 r   |
| nasa-pcoe-battery (12/5/1)         | persistence         | 10.91 (12; 2/0/2/6/2)          | 10.80    | 11.03     | -2338.47  | 1.00     | 157.22 | 5 b / 33 r    |
| nasa-pcoe-battery (12/5/1)         | linear_trend        | 20.76 (12; 2/0/2/6/2)          | 30.92    | 32.14     | -19873.62 | 1.00     | 290.89 | 5 b / 33 r    |
| nasa-pcoe-battery (12/5/1)         | ridge               | 14.09 (12; 2/0/2/6/2)          | 3.47     | 3.94      | -297.90   | 1.00     | 157.24 | 5 b / 33 r    |
| nasa-pcoe-battery (12/5/1)         | lightgbm **(sel.)** | 9.89 (12; 2/0/2/6/2)           | 12.88    | 14.07     | -3810.21  | 1.00     | 114.43 | 5 b / 33 r    |
| severson-2019 (72/30/22)           | persistence         | 1.17 (72; 15/14/11/14/18)      | 1.06     | 1.80      | 0.86      | 0.90     | 6.04   | 30 b / 2357 r |
| severson-2019 (72/30/22)           | linear_trend        | 0.61 (72; 15/14/11/14/18)      | 0.50     | 0.93      | 0.96      | 0.90     | 2.85   | 30 b / 2357 r |
| severson-2019 (72/30/22)           | ridge               | 1.77 (72; 15/14/11/14/18)      | 2.13     | 2.66      | 0.69      | 0.95     | 9.82   | 30 b / 2357 r |
| severson-2019 (72/30/22)           | lightgbm **(sel.)** | 0.28 (72; 15/14/11/14/18)      | 0.25     | 0.40      | 0.99      | 0.92     | 1.38   | 30 b / 2357 r |

#### SOH forecast, 100 cycles ahead (SOH points; selected: `lightgbm`)

| Dataset (train/cal/test batteries) | Model               | CV MAE (batteries; fold sizes) | Test MAE | Test RMSE | Test R² | Coverage | Width | Calibration   |
| ---------------------------------- | ------------------- | ------------------------------ | -------- | --------- | ------- | -------- | ----- | ------------- |
| calce-cs2-cx2 (8/3/1)              | persistence         | 5.15 (8; 1/1/2/1/3)            | 6.49     | 7.79      | 0.67    | 0.66     | 16.08 | 3 b / 367 r   |
| calce-cs2-cx2 (8/3/1)              | linear_trend        | 3.50 (8; 1/1/2/1/3)            | 3.26     | 4.53      | 0.89    | 0.84     | 12.24 | 3 b / 367 r   |
| calce-cs2-cx2 (8/3/1)              | ridge               | 4.99 (8; 1/1/2/1/3)            | 4.47     | 4.94      | 0.87    | 0.93     | 14.37 | 3 b / 367 r   |
| calce-cs2-cx2 (8/3/1)              | lightgbm **(sel.)** | 3.82 (8; 1/1/2/1/3)            | 1.94     | 2.83      | 0.96    | 1.00     | 40.75 | 3 b / 367 r   |
| nasa-pcoe-battery (6/4/0)          | persistence         | 13.70 (6; 1/0/0/4/1)           | –        | –         | –       | –        | –     | 4 b / 11 r    |
| nasa-pcoe-battery (6/4/0)          | linear_trend        | 46.87 (6; 1/0/0/4/1)           | –        | –         | –       | –        | –     | 4 b / 11 r    |
| nasa-pcoe-battery (6/4/0)          | ridge               | 20.67 (6; 1/0/0/4/1)           | –        | –         | –       | –        | –     | 4 b / 11 r    |
| nasa-pcoe-battery (6/4/0)          | lightgbm **(sel.)** | 7.82 (6; 1/0/0/4/1)            | –        | –         | –       | –        | –     | 4 b / 11 r    |
| severson-2019 (72/30/22)           | persistence         | 2.05 (72; 15/14/11/14/18)      | 1.89     | 3.05      | 0.60    | 0.90     | 9.98  | 30 b / 2207 r |
| severson-2019 (72/30/22)           | linear_trend        | 1.27 (72; 15/14/11/14/18)      | 1.04     | 1.90      | 0.84    | 0.91     | 6.29  | 30 b / 2207 r |
| severson-2019 (72/30/22)           | ridge               | 1.79 (72; 15/14/11/14/18)      | 2.03     | 2.55      | 0.72    | 0.93     | 7.88  | 30 b / 2207 r |
| severson-2019 (72/30/22)           | lightgbm **(sel.)** | 0.46 (72; 15/14/11/14/18)      | 0.36     | 0.61      | 0.98    | 0.93     | 2.23  | 30 b / 2207 r |

#### SOH forecast, 200 cycles ahead (SOH points; selected: `lightgbm`)

| Dataset (train/cal/test batteries) | Model               | CV MAE (batteries; fold sizes) | Test MAE | Test RMSE | Test R² | Coverage | Width | Calibration   |
| ---------------------------------- | ------------------- | ------------------------------ | -------- | --------- | ------- | -------- | ----- | ------------- |
| calce-cs2-cx2 (8/3/1)              | persistence         | 9.18 (8; 1/1/2/1/3)            | 12.08    | 13.77     | -0.09   | 0.67     | 30.59 | 3 b / 337 r   |
| calce-cs2-cx2 (8/3/1)              | linear_trend        | 6.94 (8; 1/1/2/1/3)            | 6.80     | 9.33      | 0.50    | 0.81     | 22.89 | 3 b / 337 r   |
| calce-cs2-cx2 (8/3/1)              | ridge               | 8.30 (8; 1/1/2/1/3)            | 3.80     | 5.16      | 0.85    | 1.00     | 39.01 | 3 b / 337 r   |
| calce-cs2-cx2 (8/3/1)              | lightgbm **(sel.)** | 5.50 (8; 1/1/2/1/3)            | 3.21     | 5.43      | 0.83    | 0.96     | 29.84 | 3 b / 337 r   |
| severson-2019 (72/29/22)           | persistence         | 3.41 (72; 15/14/11/14/18)      | 3.19     | 4.67      | 0.08    | 0.89     | 15.82 | 29 b / 1911 r |
| severson-2019 (72/29/22)           | linear_trend        | 2.56 (72; 15/14/11/14/18)      | 2.10     | 3.48      | 0.49    | 0.90     | 11.98 | 29 b / 1911 r |
| severson-2019 (72/29/22)           | ridge               | 2.35 (72; 15/14/11/14/18)      | 2.54     | 3.20      | 0.57    | 0.89     | 9.34  | 29 b / 1911 r |
| severson-2019 (72/29/22)           | lightgbm **(sel.)** | 0.93 (72; 15/14/11/14/18)      | 0.74     | 1.15      | 0.94    | 0.93     | 4.50  | 29 b / 1911 r |

#### SOH estimation from signals, Severson (SOH points; selected: `lightgbm`)

| Dataset (train/cal/test batteries) | Model               | CV MAE (batteries; fold sizes) | Test MAE | Test RMSE | Test R² | Coverage | Width | Calibration   |
| ---------------------------------- | ------------------- | ------------------------------ | -------- | --------- | ------- | -------- | ----- | ------------- |
| severson-2019 (72/30/22)           | cycle_lookup        | 2.46 (72; 15/14/11/14/18)      | 2.49     | 3.94      | 0.30    | 0.91     | 13.30 | 30 b / 5011 r |
| severson-2019 (72/30/22)           | ridge               | 1.31 (72; 15/14/11/14/18)      | 1.24     | 1.59      | 0.89    | 0.99     | 8.19  | 30 b / 5011 r |
| severson-2019 (72/30/22)           | lightgbm **(sel.)** | 0.84 (72; 15/14/11/14/18)      | 0.80     | 1.14      | 0.94    | 0.96     | 5.05  | 30 b / 5011 r |

#### SOH estimation from signals, NASA (SOH points; selected: `lightgbm`)

| Dataset (train/cal/test batteries) | Model               | CV MAE (batteries; fold sizes) | Test MAE | Test RMSE | Test R² | Coverage | Width  | Calibration  |
| ---------------------------------- | ------------------- | ------------------------------ | -------- | --------- | ------- | -------- | ------ | ------------ |
| nasa-pcoe-battery (18/10/5)        | cycle_lookup        | 16.08 (18; 2/2/5/7/2)          | 12.80    | 14.86     | -0.04   | 1.00     | 123.14 | 10 b / 136 r |
| nasa-pcoe-battery (18/10/5)        | ridge               | 12.10 (18; 2/2/5/7/2)          | 13.56    | 15.93     | -0.19   | 0.97     | 65.16  | 10 b / 136 r |
| nasa-pcoe-battery (18/10/5)        | lightgbm **(sel.)** | 11.30 (18; 2/2/5/7/2)          | 9.01     | 14.91     | -0.04   | 0.95     | 68.84  | 10 b / 136 r |

#### SOH estimation from signals, CALCE (SOH points; selected: `lightgbm`)

| Dataset (train/cal/test batteries) | Model               | CV MAE (batteries; fold sizes) | Test MAE | Test RMSE | Test R² | Coverage | Width | Calibration |
| ---------------------------------- | ------------------- | ------------------------------ | -------- | --------- | ------- | -------- | ----- | ----------- |
| calce-cs2-cx2 (8/3/1)              | cycle_lookup        | 7.67 (8; 1/1/2/1/3)            | 6.12     | 8.86      | 0.64    | 0.81     | 17.79 | 3 b / 794 r |
| calce-cs2-cx2 (8/3/1)              | ridge               | 4.09 (8; 1/1/2/1/3)            | 5.35     | 6.64      | 0.80    | 0.99     | 46.25 | 3 b / 794 r |
| calce-cs2-cx2 (8/3/1)              | lightgbm **(sel.)** | 3.30 (8; 1/1/2/1/3)            | 2.08     | 3.79      | 0.93    | 0.98     | 24.42 | 3 b / 794 r |

#### Cross-dataset RUL stress test (trained on Severson only) (cycles; selected: `lightgbm`)

| Dataset (train/cal/test batteries) | Model               | CV MAE (batteries; fold sizes) | Test MAE | Test RMSE | Test R² | Coverage | Width | Calibration      |
| ---------------------------------- | ------------------- | ------------------------------ | -------- | --------- | ------- | -------- | ----- | ---------------- |
| calce-cs2-cx2 (0/0/12)             | linear_trend        | – (0; 0/0/0/0/0)               | 509      | 957       | -24.20  | 0.88     | 1739  | 0 b / 0 r pooled |
| calce-cs2-cx2 (0/0/12)             | cohort_median       | – (0; 0/0/0/0/0)               | 115      | 127       | 0.55    | 1.00     | 2965  | 0 b / 0 r pooled |
| calce-cs2-cx2 (0/0/12)             | ridge               | – (0; 0/0/0/0/0)               | 231      | 297       | -1.44   | 0.25     | 213   | 0 b / 0 r pooled |
| calce-cs2-cx2 (0/0/12)             | lightgbm **(sel.)** | – (0; 0/0/0/0/0)               | 182      | 239       | -0.58   | 0.31     | 171   | 0 b / 0 r pooled |
| nasa-pcoe-battery (0/0/8)          | linear_trend        | – (0; 0/0/0/0/0)               | 443      | 1066      | -546.74 | 0.80     | 797   | 0 b / 0 r pooled |
| nasa-pcoe-battery (0/0/8)          | cohort_median       | – (0; 0/0/0/0/0)               | 634      | 637       | -194.63 | 1.00     | 2999  | 0 b / 0 r pooled |
| nasa-pcoe-battery (0/0/8)          | ridge               | – (0; 0/0/0/0/0)               | 302      | 812       | -317.05 | 0.51     | 278   | 0 b / 0 r pooled |
| nasa-pcoe-battery (0/0/8)          | lightgbm **(sel.)** | – (0; 0/0/0/0/0)               | 59       | 81        | -2.14   | 0.25     | 100   | 0 b / 0 r pooled |
| severson-2019 (94/30/0)            | linear_trend        | 1407 (94; 21/21/15/17/20)      | –        | –         | –       | –        | –     | 30 b / 2483 r    |
| severson-2019 (94/30/0)            | cohort_median       | 279 (94; 21/21/15/17/20)       | –        | –         | –       | –        | –     | 30 b / 2483 r    |
| severson-2019 (94/30/0)            | ridge               | 182 (94; 21/21/15/17/20)       | –        | –         | –       | –        | –     | 30 b / 2483 r    |
| severson-2019 (94/30/0)            | lightgbm **(sel.)** | 106 (94; 21/21/15/17/20)       | –        | –         | –       | –        | –     | 30 b / 2483 r    |

RUL, selected model, by life fraction (test batteries, all datasets):

| Life fraction | n   | MAE | Coverage | α-λ (±20 %) |
| ------------- | --- | --- | -------- | ----------- |
| 0.2           | 23  | 87  | 0.96     | 0.78        |
| 0.4           | 24  | 84  | 0.92     | 0.75        |
| 0.6           | 24  | 38  | 1.00     | 0.75        |
| 0.8           | 24  | 20  | 1.00     | 0.75        |

## What the results support

- **Severson (LFP, 124 usable cells, 22 held out):** the strongest evidence. LightGBM predicts RUL
  with MAE 92 cycles (R² 0.78; ridge 197, cohort baseline 317, linear trend 1,360), and its 90 %
  intervals covered 0.89 of held-out points. Over all held-out batteries, errors shrink later in life (MAE 87 cycles at 20 % of
  life, 20 at 80 %). SOH forecasts 50–200 cycles ahead and signal-only SOH estimation (MAE 0.8 SOH
  points) also beat their baselines on held-out cells.
- **CALCE (LCO, 12 cells):** only 1 held-out test battery, so the test numbers are anecdotal. The
  cross-validation over 8 training batteries (folds of 1–3 batteries) is the better guide: RUL MAE
  59 cycles (R² 0.81) with the pooled model. Treat this as indicative only.
- **NASA (34 cells):** not usable for RUL validation (3 trainable batteries; 16 start below 80 %
  of rating and 7 are censored). Signal-only SOH estimation does not work on NASA (R² ≈ 0 on 5 test
  batteries).
- **Across datasets: no generalisation.** A model trained only on Severson LFP cells fails on
  CALCE LCO cells (MAE 182 cycles, R² −0.58, coverage 0.31; the cohort baseline does better at 115)
  and on NASA. Nothing here supports applying the models to a chemistry or protocol they were not
  trained on.

## Limitations

- Laboratory cells under fixed protocols: no vehicle data, no field duty cycles, few
  temperatures. NASA's chemistry is not stated; CALCE has no temperature channel.
- Small held-out sets outside Severson; per-dataset intervals rely on 3–5 calibration batteries.
- One random split (with grouped CV). A different split would move the per-dataset numbers,
  most for CALCE and NASA.
- Fixed hyper-parameters (not tuned) and no deep sequence models; the plan's Gaussian-process
  and LSTM tiers were not added because the baselines and LightGBM already expose the data limits.
- Predictions shown for training batteries are in-sample, and the UI says so.
- The models predict from cycle summaries; they are not wired into the v1/v2 analytics, the Digital
  Twin or the simulator, which keep their own documented methods.
