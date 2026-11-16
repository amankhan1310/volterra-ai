# Phase 8: the simulator's assumptions and baseline against real data

**Outcome in one line:** none of the What-If Simulator's stress coefficients can be calibrated
from the public datasets, so they stay labelled `assumed`. The evidence that does exist is shown
next to them, and the simulator's trend-based baseline was measured against the life real cells
actually had. It is far off before the knee, and the UI says so.

Files: `ml/volterra_ml/calibration.py` → `backend/app/evidence/stress_evidence.json`;
`backend/app/validation/simulator_baseline.py` → `backend/app/evidence/baseline_validation.json`.
Both were run on the real datasets and hold aggregate numbers only. The API serves them at
`GET /api/v1/simulator/evidence`; the Simulator page shows them under the scenario chart.

## Stress coefficients: evidence, not calibration

The simulator multiplies a battery's fade by `exp(0.06·(T−25))` (temperature),
`1 + 0.4·(C−1)` (C-rate) and `(DoD/80)^0.9` (depth of discharge), all carried over from the
prototype.

| Coefficient        | What the data show                                                                                                                                                                                                        | Why it is not a calibration                                                                                                                                                                                                                              |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Temperature        | NASA B0029–B0032 at 43 °C faded **×3.16** faster than B0025–B0028 at 24 °C over their first 25 cycles (90 % bootstrap CI over the 4 matched pairs: 1.88–31). The assumed factor for +19 °C is ×3.13, inside the interval. | The 24 °C group was discharged with a 4 A square wave at 50 % duty (2 A mean), the 43 °C group at a constant 4 A, so load and temperature change together. Four pairs give a very wide interval. Nothing covers temperatures below 24 °C or above 43 °C. |
| C-rate             | Severson LFP fast charging (124 cells): cycle life ×**0.52** per extra C of mean charging rate (CI 0.44–0.63), R² 0.20.                                                                                                   | Covers 3.6–5.3 C fast charging of one chemistry with a fixed 4 C discharge. The slider spans ordinary cycling rates, which no dataset varies.                                                                                                            |
| Depth of discharge | No evidence.                                                                                                                                                                                                              | No dataset varies it.                                                                                                                                                                                                                                    |

The UI lists, for the current scenario, which of its conditions lie outside anything the data
covered.

### Why an "approximately 0.06/°C" estimate is still not a calibration

A first look at the same NASA groups, before reading their test protocols, attributed the whole
×3.16 fade ratio to temperature: ln(3.16)/19 °C ≈ **0.061/°C**, close to the assumed 0.06. The
same number cannot calibrate the coefficient, for two reasons:

1. **Confounding.** The NASA README shows that the 24 °C group was discharged with a 4 A square
   wave at 50 % duty (2 A mean) and the 43 °C group at a constant 4 A. Doubling the mean load
   alone accelerates fade, so the data cannot say how much of ×3.16 is temperature.
2. **Precision.** With four matched pairs the 90 % bootstrap interval of the ratio is 1.88–31.
   Even read as temperature alone, that is 0.033–0.18 per °C: a factor of more than five.

So 0.061/°C is an **exploratory** reading, recorded in the evidence file with its interval and the
label "exploratory only, not suitable for calibration". The coefficient stays `assumed`. It would
become `fitted` only with independent cells that differ in temperature alone, under the same load
and protocol.

## What the evidence files contain

Aggregates only: per-group and per-pair fade _slopes_ (8 numbers for NASA), ratios, regression
slopes, bootstrap intervals, cell counts and error summaries (MAE, bias, counts) per method and
life fraction. No per-cycle or per-sample measurement, no battery trajectory. A unit test caps
each file at 20 kB.

## Baseline against real life

The simulator's baseline is the battery's own fitted trend (v1: a straight line plus the
prototype's `(1 + n/1500)` term; v2: the quadratic forecast, which equals the v2 Overview RUL).
The validation tool runs the backend's unchanged analytics on each of the 124 usable Severson cells,
truncated at 30/50/70/90 % of its documented life. It compares the method's cycles-to-EOL with the
cycles the cell actually had left.

| Method                                 | 30 % of life               | 50 %     | 70 %    | 90 % |
| -------------------------------------- | -------------------------- | -------- | ------- | ---- |
| v1 linear (Overview v1)                | 3,905                      | 1,876    | 867     | 100  |
| v1 simulator baseline                  | 1,244                      | 804      | 479     | 81   |
| v2 quadratic (= v2 simulator baseline) | 589 (8 cells: no estimate) | 384 (18) | 250 (4) | 18   |

Mean absolute error in cycles of remaining life. Every method overestimates remaining life, with
a positive bias almost equal to its MAE: a trend fitted before the knee of an LFP cell cannot see
the knee coming. Only near the end (90 %) is the v2 baseline close (MAE 18 cycles, 44 % of cells
within ±20 %). For comparison, the Phase 7 LightGBM RUL model had MAE of about 85 cycles on
held-out cells at 20–40 % of life (`docs/models/README.md`).

**Consequence for the app.** The scenario curves are useful to compare conditions _relative to
each other_ under stated assumptions. They are not life predictions for real cells. The
Simulator page says this next to the numbers. For real batteries, the Digital Twin and Battery
Data pages show the experimental Phase 7 RUL model, with its interval and validation status.

## Limitations

- Severson only for the baseline validation (NASA cells are shorter than the 120-cycle trend
  window; CALCE has no temperature, which the cycle records require).
- One prediction point per cell per fraction; LFP cells with a pronounced knee are the hardest
  case for any trend extrapolation.
- The evidence is regenerated by hand (`python -m volterra_ml.calibration`, `python -m
app.validation.simulator_baseline`) and committed; CI checks its schema, not its values.
