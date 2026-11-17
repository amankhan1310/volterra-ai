# Capacity degradation and SOH from measured capacity

`GET /api/v1/batteries/{id}/capacity` (`backend/app/analytics/capacity.py`, shown on the Battery
Data page) summarises what a battery's **measured discharge capacity** shows. It needs neither
temperature nor the 221 cycles of the full analytics, so it works for the CALCE cells (no
temperature channel) and the NASA cells (at most 197 cycles), whose full analytics stay refused
(`missing_measurement`, `insufficient_data`). Nothing is filled in, smoothed or extrapolated.

## SOH reference

`SOH = capacity / reference × 100`. The reference is the one the importer stored from the source
documentation (`soh_reference = rated_capacity`); the first measured capacity is **never** used in
its place.

| Dataset         | Reference         | Source                                                          | Why not the first measurement                                                                                  |
| --------------- | ----------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| NASA PCoE       | 2.0 Ah            | NASA README: "30% fade in rated capacity (from 2 Ah to 1.4 Ah)" | first discharges range from 0.06 Ah (B0033, B0041: aborted or cold discharges) to 2.04 Ah                      |
| CALCE CS2 / CX2 | 1.10 Ah / 1.35 Ah | CALCE cell specifications (1100 / 1350 mAh)                     | fresh CS2 cells deliver ~1.14–1.16 Ah (`capacity_above_rated`); CX2_34 starts with a partial 1.13 Ah discharge |
| Severson et al. | 1.1 Ah            | paper: A123 APR18650M1A, 1.1 Ah nominal                         | n/a                                                                                                            |
| Synthetic       | 2.0 Ah (nominal)  | the generator defines SOH against it                            | n/a                                                                                                            |

A measured battery without a stated reference gets no SOH (the response says so in
`limitations`); its capacity figures are still reported.

## Figures

- **Usable cycles**: every stored cycle except incomplete discharges flagged by the importer
  (`capacity_zero`, `file_ends_during_discharge`). Other flags (`capacity_jump_up`: recovery after
  rest; `capacity_above_rated`) are real behaviour and stay in. Excluded cycles remain visible in
  the per-cycle data.
- **Initial / final capacity**: median of the first / last 5 usable cycles, so one abnormal cycle
  at either end does not decide the result. **Loss** = initial − final; **retention** = final /
  initial.
- **SOH** at start, now (last 5 cycles) and of the last cycle, against the reference.
- **Trend** (`fitted`): least-squares line of capacity against cycle over all usable cycles, only
  with at least 10 of them; slope in Ah/cycle and SOH points per 100 cycles, with R². It describes
  the recorded cycles and is never extrapolated to an end of life.
- **End of life** (observed only): first usable cycle at or below the threshold (80 %) whose
  forward 5-cycle median is also at or below it (the Phase 7 rule). None when the recording
  already starts below the threshold.

## Data quality: when figures are withheld

The measurements themselves are never changed, removed or smoothed; only the summary figures are
withheld when they would misdescribe the recording.

- **Level shift** (sustained jump): the medians of the 5 usable cycles before and after a cycle
  differ by more than 25 % of the rated capacity (NASA 0.5 Ah, CALCE 0.275 / 0.3375 Ah). Single
  abnormal cycles and recovery after rest (about 0.07 Ah in NASA B0005) stay far below it. The
  jump is placed at the largest single-cycle step. The recording is then not one continuous fade
  (different test conditions or abnormal discharges), so **initial capacity, SOH at start, loss,
  retention, the trend and the end of life are withheld**; final capacity and current SOH (the
  measured last cycles) stay. Found in 9 NASA cells, none in CALCE:

  | Cell                  | Jump (cycle: before → after, Ah)                          |
  | --------------------- | --------------------------------------------------------- |
  | B0033                 | 139: 1.37 → 0.24; 147: 0.40 → 1.38                        |
  | B0038 / B0039         | 12: 1.03 → 1.78 / 0.44 → 1.77                             |
  | B0040                 | 12: 0.74 → 1.73                                           |
  | B0041                 | 42: 0.05 → 1.12 (42 discharges at ~0.05 Ah, 4 °C ambient) |
  | B0042 / B0043 / B0044 | 41: ~1.5 → ~0.07; 87: ~0.06 → ~1.5                        |
  | B0050                 | 13: 1.36 → 0.30                                           |

  An upward jump is stated not to be evidence of battery recovery; a drop is stated not to be, on
  its own, evidence of degradation.

- **Final above initial** without a level shift: loss and retention are withheld (not presented
  as recovery). A **rising fitted line** withholds the trend (NASA B0026).
- **Fitted line vs measurement**: when the line's end differs from the measured final capacity by
  more than 5 % of the rated capacity, the fade is not linear and the response says so, with both
  values (10 of 12 CALCE cells, e.g. CS2_33: line 0.378 Ah, measured 0.071 Ah; NASA B0047,
  B0049). The UI labels the line "a model, not a measurement" and shows its end next to the
  measured final capacity.

## Other stated limitations

Fewer than 10 usable cycles (no trend; initial and final windows overlap), a recording that starts
below the threshold, an R² below 0.5, excluded cycles, and — when the full analytics are refused —
that remaining-life forecasts, anomalies, simulator and advisor are not supported for the battery.

## Verification

- `backend/tests/unit/analytics/test_capacity.py`: reference, exclusions, limitations, EOL rule,
  level shifts (B0041- and B0050-shaped), curved fade (CS2_33-shaped), linear fade (B0005-shaped).
- `backend/tests/db/test_real_data_api.py`: the endpoint on generated CALCE-style (no temperature)
  and NASA-style (2 cycles) batteries; SOH equals the stored per-cycle SOH.
- `backend/tests/unit/analytics/test_capacity_realdata.py` (local, `realdata`): all 12 CALCE and
  34 NASA cells recomputed independently from the bundles, whose capacities equal the original
  workbooks and `.mat` files (`ml/tests/loaders/test_calce_realdata.py`, `test_nasa_realdata.py`);
  exact regression values for B0041, CS2_33 and B0005, and the list of cells with level shifts.
