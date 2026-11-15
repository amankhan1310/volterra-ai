# Canonical battery-data schema (version 1)

The contract between the dataset loaders (`ml/volterra_ml`) and the database importer
(`backend/app/db/import_dataset.py`). The single source of truth is
[`ml/volterra_ml/canonical/columns.py`](../../ml/volterra_ml/canonical/columns.py); the backend
test `tests/db/test_import_contract.py` fails if the importer's expectations drift from it.

## Principles

- **Nothing is invented.** Every measurement column is nullable. A value the source does not
  provide stays null: it is never replaced by zero, interpolated or estimated. Non-finite source
  values (NaN, ±Inf) become null and are flagged.
- **Source identity is kept.** Each battery keeps the source's cell id; each cycle keeps its
  position in the source file (`source_cycle_index`) next to its canonical ordinal
  (`cycle_index`); each battery lists the archive members it came from, with SHA-256.
- **Flags, not deletions.** Validation adds stable flag codes; no row is dropped or corrected.
- **SOH is relative to the rated capacity** (decision D1): `soh_pct = capacity_ah /
soh_reference_capacity_ah × 100`, with `soh_reference = "rated_capacity"`. Each battery also
  records its first measured capacity (`first_capacity_ah`) and the cycle it comes from.
- **One canonical cycle per discharge** (decision D2). Charge and impedance data are kept in
  full in Parquet.

## Bundle layout

`<VOLTERRA_DATA_DIR>/processed/<slug>/<version>/`, written by `python -m volterra_ml.loaders build`:

| File                                       | Content                                                                                                                                                                                         |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `bundle_manifest.json`                     | schema version, dataset provenance (publisher, licence, citation, DOI), loader and library versions, raw inputs (file, size, SHA-256), every output (rows, size, SHA-256) and `bundle_checksum` |
| `batteries.parquet`                        | one row per cell                                                                                                                                                                                |
| `cycles.parquet`                           | one row per discharge cycle                                                                                                                                                                     |
| `samples/<id>_<charge\|discharge>.parquet` | every sample of every charge and discharge, all source channels                                                                                                                                 |
| `impedance/<id>.parquet`                   | impedance records (when the source has them)                                                                                                                                                    |
| `quality_report.json`                      | flag counts per cell and in total                                                                                                                                                               |

Bundles are deterministic (the same input and library versions give byte-identical files), built
in a temporary folder and moved into place only when complete, and written only to locations Git
ignores. `python -m volterra_ml.loaders verify <slug>` re-hashes a bundle.

## Columns

### batteries.parquet

| Column                                            | Type            | Null | Meaning                                                                        |
| ------------------------------------------------- | --------------- | ---- | ------------------------------------------------------------------------------ |
| `external_id`, `source_battery_id`                | string          | no   | cell id as the source names it (e.g. `B0005`)                                  |
| `chemistry`                                       | string          | yes  | only when the publisher states it                                              |
| `chemistry_basis`                                 | string          | no   | `stated_by_source` or `not_stated`                                             |
| `form_factor`                                     | string          | yes  | as stated (NASA: `18650`)                                                      |
| `rated_capacity_ah`                               | float64         | no   | publisher's rated capacity                                                     |
| `nominal_voltage_v`                               | float64         | yes  | only when stated                                                               |
| `soh_reference`, `soh_reference_capacity_ah`      | string, float64 | no   | `rated_capacity`, the reference value                                          |
| `first_capacity_ah`, `first_capacity_cycle_index` | float64, int32  | yes  | first measured discharge capacity                                              |
| `n_discharge_cycles`, `n_cycles_with_capacity`    | int32           | no   | counts in the source                                                           |
| `test_conditions_json`                            | string (JSON)   | no   | the publisher's test description, verbatim, plus observed ambient temperatures |
| `source_files_json`                               | string (JSON)   | no   | archive members (path, SHA-256, which copy is used)                            |

### cycles.parquet

| Column                                                 | Type                  | Null | Meaning                                                      |
| ------------------------------------------------------ | --------------------- | ---- | ------------------------------------------------------------ |
| `external_id`, `cycle_index`, `cycle_type`             | string, int32, string | no   | battery, ordinal among its discharges (0-based), `discharge` |
| `source_cycle_index`                                   | int32                 | no   | position in the source's cycle array                         |
| `start_time_local`                                     | string                | yes  | ISO 8601 without offset (the source gives no timezone)       |
| `capacity_ah`, `soh_pct`                               | float64               | yes  | as reported; SOH derived per D1                              |
| `temp_mean_c`, `temp_min_c`, `temp_max_c`              | float64               | yes  | cell temperature over the discharge (finite samples)         |
| `voltage_mean_v`, `voltage_min_v`, `voltage_max_v`     | float64               | yes  | terminal voltage over the discharge                          |
| `current_mean_a`, `discharge_time_s`, `ambient_temp_c` | float64               | yes  | mean current, duration, chamber temperature                  |
| `n_samples`                                            | int32                 | no   | samples in the discharge                                     |
| `quality_flags_json`                                   | string (JSON)         | no   | `{flag: detail}`                                             |
| `db_eligible`                                          | bool                  | no   | has every value the database `cycles` table requires         |

### samples and impedance

Samples: `external_id`, `cycle_type`, `source_cycle_index`, `sample_index`, `time_s`,
`voltage_v`, `current_a`, `temp_c`, `aux_current_a`, `aux_voltage_v` (the source's extra
channels: NASA `Current_charge`/`Voltage_charge` on charge, `Current_load`/`Voltage_load` on
discharge). Values are stored bit for bit; arrays of unequal length are padded with null.

Impedance: `re_ohm`, `rct_ohm` with `re_ohm_im`, `rct_ohm_im` (imaginary parts, null unless the
source value is complex), complex spectra as real/imaginary lists (the source has no frequency
vector), `ambient_temp_c`, `start_time_local` and `quality_flags_json`.

## Validation flags

| Flag                                        | Rule                                                                                                 | Effect                                             |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `capacity_missing`                          | capacity field empty or non-finite                                                                   | capacity and SOH null; not imported into `cycles`  |
| `capacity_negative`                         | capacity < 0                                                                                         | capacity null; not imported                        |
| `capacity_zero`                             | capacity = 0                                                                                         | kept and imported, flagged                         |
| `capacity_above_rated`                      | capacity > rated capacity                                                                            | kept and imported, flagged                         |
| `capacity_jump_up`                          | capacity exceeds the previous positive measured capacity by > 2.5% of rated (0.05 Ah for 2 Ah cells) | kept and imported, flagged                         |
| `empty_samples`                             | no samples                                                                                           | statistics null                                    |
| `unequal_array_lengths`                     | channels of different length                                                                         | padded with null                                   |
| `non_finite_values`                         | NaN/Inf in a channel                                                                                 | those samples null; statistics over finite samples |
| `time_not_increasing`                       | time vector not strictly increasing                                                                  | flagged                                            |
| `voltage_below_1_5v` / `voltage_above_4_5v` | minimum < 1.5 V / maximum > 4.5 V                                                                    | flagged                                            |
| `temperature_out_of_range`                  | outside −20 … 80 °C                                                                                  | flagged                                            |
| `re_complex` / `rct_complex` (impedance)    | fitted value is complex                                                                              | both parts kept, flagged                           |

The thresholds follow the real NASA data: discharges end at 2.0–2.7 V cut-offs and 583 of 2,794
dip slightly below 2.0 V, while the 36 below 1.5 V are failed runs; capacity changes between
consecutive cycles are typically about 0.01 Ah, and the 100 rises above 0.05 Ah stand out.

## Database mapping (migration 0002)

The importer writes one transaction per bundle: `datasets` (plus `publisher`, `landing_url`,
`doi`; licence, loader, inputs and quality report in `meta`), `batteries` (plus
`chemistry_basis`, `soh_reference`, `soh_reference_capacity_ah`, `first_capacity_ah`,
`first_capacity_cycle_index`; test conditions and source files in `test_conditions`), `cycles`
(the `db_eligible` rows only, with `source_cycle_index` and `quality_flags`; `start_time` stays
null without a timezone) and `dataset_files` (every raw and bundle file: path relative to the
data directory, size, SHA-256, rows, battery). Details: `backend/README.md`.
