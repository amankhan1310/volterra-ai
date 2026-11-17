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

## Stated limitations

Fewer than 10 usable cycles (no trend), fewer than 10 (initial and final windows overlap), a
recording that starts below the threshold, a rising fitted capacity (the trend is withheld: NASA
B0041 starts with 0.056 Ah discharges), an R² below 0.5, excluded cycles, and — when the full
analytics are refused — that remaining-life forecasts, anomalies, simulator and advisor are not
supported for the battery.

## Verification

- `backend/tests/unit/analytics/test_capacity.py`: reference, exclusions, limitations, EOL rule.
- `backend/tests/db/test_real_data_api.py`: the endpoint on generated CALCE-style (no temperature)
  and NASA-style (2 cycles) batteries; SOH equals the stored per-cycle SOH.
- `backend/tests/unit/analytics/test_capacity_realdata.py` (local, `realdata`): all 12 CALCE and
  34 NASA cells recomputed independently from the bundles, whose capacities equal the original
  workbooks and `.mat` files (`ml/tests/loaders/test_calce_realdata.py`, `test_nasa_realdata.py`).
