# Canonical battery-data schema (version 2)

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
ignores. `python -m volterra_ml.loaders verify <slug>` re-hashes a bundle. The lock file resolves
different numpy/scipy/pyarrow versions for Python 3.10 and 3.12, and the manifest records them, so
the two interpreters build bundles with equal values but different bytes (checked for CALCE: all
14 tables equal). The local bundles are built with the project's Python 3.10 environment.

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
| `internal_resistance_ohm` (v2)                         | float64               | yes  | per-cycle internal resistance (Ω) as reported by the source  |
| `charge_time_s` (v2)                                   | float64               | yes  | charge duration (s): reported (Severson) or measured span    |
| `source_ref_json` (v2)                                 | string (JSON)         | yes  | where the cycle comes from (see below)                       |
| `n_samples`                                            | int32                 | no   | samples in the discharge                                     |
| `quality_flags_json`                                   | string (JSON)         | no   | `{flag: detail}`                                             |
| `db_eligible`                                          | bool                  | no   | has every value the database `cycles` table requires         |

Version 2 (Phase 6 M4) added `internal_resistance_ohm`, `charge_time_s` and `source_ref_json`;
older bundles are rebuilt, never reinterpreted. Per dataset:

| Column                    | NASA                                     | CALCE                                                                                               | Severson                                   |
| ------------------------- | ---------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| `internal_resistance_ohm` | null (not reported per cycle)            | null: the tester's value is a held reading that changes within a cycle (full series in the samples) | summary `IR` (Ω)                           |
| `charge_time_s`           | null (charge is a separate source cycle) | span of the cycle's charge samples (current > 0)                                                    | summary `chargetime` (min) × 60            |
| `temp_*_c`                | over the discharge samples               | null (not measured)                                                                                 | summary `Tavg`/`Tmin`/`Tmax` (whole cycle) |
| `start_time_local`        | MATLAB date vector                       | first sample's `Date_Time`                                                                          | null (no absolute time in the files)       |

`source_ref_json` objects (keys sorted):

- NASA: `{"member": "<group zip>/Bxxxx.mat", "cycle_array_index": n}`
- CALCE: `{"member": "<cell>/<workbook>.xlsx", "sheet": "...", "cycle_index_in_file": n,
"first_row": r0, "last_row": r1}` (worksheet rows; the header is row 1)
- Severson: `{"member": "<batch>.mat", "cell": "bNcM", "array_position": k,
"summary_cycle": c}` (`cell` names the segment for joined cells)

Battery-level conditions in `test_conditions_json` may carry `dataset_flags`
(`paper_excluded`, `joined_segments`, `earlier_history_not_converted`); the quality report
lists them under `battery_flags`. `first_capacity_ah` is the first _positive_ measured
capacity (Severson batch 1 reports 0 Ah for every cell's first cycle).

### samples and impedance

Samples: `external_id`, `cycle_type`, `source_cycle_index`, `sample_index`, `time_s`,
`voltage_v`, `current_a`, `temp_c`, `aux_current_a`, `aux_voltage_v` (the source's extra
channels: NASA `Current_charge`/`Voltage_charge` on charge, `Current_load`/`Voltage_load` on
discharge). Values are stored bit for bit; arrays of unequal length are padded with null.

CALCE and Severson samples (`samples/<id>_cycle.parquet`, `cycle_type` `cycle`: one record
per source cycle including charge, discharge and rest) append source-specific columns:
CALCE keeps all 17 Arbin columns (`data_point`, `step_time_s`, `step_index`,
`charge_capacity_ah`, `discharge_capacity_ah`, `charge_energy_wh`, `discharge_energy_wh`,
`dv_dt_v_per_s`, `internal_resistance_ohm`, `is_fc_data`, `ac_impedance_ohm`,
`aci_phase_angle_deg`, `date_time_local`) plus `source_member`, `source_sheet`, `source_row` and
`canonical_cycle_index` (null for cycles without discharge); Severson keeps `time_min` (source
`t`; `time_s = time_min × 60`), `charge_ah` (`Qc`), `discharge_ah` (`Qd`), `source_member`,
`source_cell` and `canonical_cycle_index`. Severson's interpolated `Qdlin`/`Tdlin`/`dQdV` are
derived by the authors and remain in the raw files.

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
| `file_ends_during_discharge` (CALCE)        | the workbook's last sample is a discharge sample                                                     | kept, flagged: capacity may be partial             |
| `empty_source_cells` (CALCE)                | an empty numeric cell in the cycle's rows                                                            | value null, flagged                                |
| `no_discharge_samples` (Severson)           | a cycle record without negative current                                                              | statistics null, flagged                           |
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

## Database mapping (migrations 0002–0004)

The importer writes one transaction per bundle: `datasets` (plus `publisher`, `landing_url`,
`doi`; licence, loader, inputs and quality report in `meta`), `batteries` (plus
`chemistry_basis`, `soh_reference`, `soh_reference_capacity_ah`, `first_capacity_ah`,
`first_capacity_cycle_index`; test conditions and source files in `test_conditions`), `cycles`
(every cycle with a measured capacity and SOH, except sample-less placeholders flagged
`empty_samples`; temperature and voltage may be null since migration 0004 and are never filled
in, and `db_eligible` still means "every analysis input measured"; with `source_cycle_index`, `quality_flags`, the v2 columns
`internal_resistance_ohm` and `charge_time_s`, and `source_ref_json` as JSONB `source_ref`
(migration 0003); `start_time` stays
null without a timezone) and `dataset_files` (every raw and bundle file: path relative to the
data directory, size, SHA-256, rows, battery). Details: `backend/README.md`.
