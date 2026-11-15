"""The canonical battery-data contract (Phase 6 M2), schema version 1. Standard library only.

This module is the single source of truth for the Parquet bundle columns. The backend importer
checks its own expectations against this file (``backend/tests/db/test_import_contract.py``),
so the producer (``volterra_ml``) and the consumer (``app.db.import_dataset``) cannot drift.

Rules:

* Units are in the column names (``_ah``, ``_v``, ``_a``, ``_c``, ``_s``, ``_pct``).
* Every measurement column is nullable. A value the source does not provide stays null; it is
  never replaced by zero or by an estimate.
* Identifier columns preserve the source's own identifiers (cell id, position in the source file,
  archive member), so every canonical row can be traced back to raw bytes.
"""

from __future__ import annotations

SCHEMA_VERSION = 1

#: Column -> Arrow type name (``string``, ``int32``, ``int64``, ``float64``, ``bool``) and
#: whether nulls are allowed. Order is the column order written to Parquet.
BATTERY_COLUMNS: dict[str, tuple[str, bool]] = {
    "external_id": ("string", False),
    "source_battery_id": ("string", False),
    "chemistry": ("string", True),
    "chemistry_basis": ("string", False),  # stated_by_source | not_stated
    "form_factor": ("string", True),
    "rated_capacity_ah": ("float64", False),
    "nominal_voltage_v": ("float64", True),
    "soh_reference": ("string", False),  # rated_capacity (decision D1)
    "soh_reference_capacity_ah": ("float64", False),
    "first_capacity_ah": ("float64", True),  # first measured discharge capacity
    "first_capacity_cycle_index": ("int32", True),
    "n_discharge_cycles": ("int32", False),
    "n_cycles_with_capacity": ("int32", False),
    "test_conditions_json": ("string", False),  # JSON object, publisher's text kept verbatim
    "source_files_json": ("string", False),  # JSON list of archive members with SHA-256
}

CYCLE_COLUMNS: dict[str, tuple[str, bool]] = {
    "external_id": ("string", False),
    "cycle_index": ("int32", False),  # ordinal among this cell's discharge cycles (0-based)
    "cycle_type": ("string", False),  # discharge (decision D2)
    "source_cycle_index": ("int32", False),  # position in the source's cycle array (0-based)
    "start_time_local": ("string", True),  # ISO 8601 without offset; source gives no timezone
    "capacity_ah": ("float64", True),
    "soh_pct": ("float64", True),  # capacity_ah / soh_reference_capacity_ah * 100
    "temp_mean_c": ("float64", True),
    "temp_min_c": ("float64", True),
    "temp_max_c": ("float64", True),
    "voltage_mean_v": ("float64", True),
    "voltage_min_v": ("float64", True),
    "voltage_max_v": ("float64", True),
    "current_mean_a": ("float64", True),
    "discharge_time_s": ("float64", True),
    "ambient_temp_c": ("float64", True),
    "n_samples": ("int32", False),
    "quality_flags_json": ("string", False),  # JSON object {flag: detail}
    "db_eligible": ("bool", False),  # has every value the cycles table requires
}

#: Per-sample traces (one file per cell and operation type; extra source channels are kept).
SAMPLE_COLUMNS: dict[str, tuple[str, bool]] = {
    "external_id": ("string", False),
    "cycle_type": ("string", False),  # charge | discharge
    "source_cycle_index": ("int32", False),
    "sample_index": ("int32", False),
    "time_s": ("float64", True),
    "voltage_v": ("float64", True),
    "current_a": ("float64", True),
    "temp_c": ("float64", True),
    "aux_current_a": ("float64", True),  # NASA: Current_charge (charge) / Current_load (discharge)
    "aux_voltage_v": ("float64", True),  # NASA: Voltage_charge (charge) / Voltage_load (discharge)
}

IMPEDANCE_COLUMNS: dict[str, tuple[str, bool]] = {
    "external_id": ("string", False),
    "source_cycle_index": ("int32", False),
    "start_time_local": ("string", True),
    "ambient_temp_c": ("float64", True),
    "re_ohm": ("float64", True),  # estimated electrolyte resistance (source: Re), real part
    "re_ohm_im": ("float64", True),  # imaginary part when the source value is complex, else null
    "rct_ohm": ("float64", True),  # estimated charge-transfer resistance (source: Rct), real part
    "rct_ohm_im": ("float64", True),  # imaginary part when the source value is complex, else null
    # Complex spectra as parallel real/imaginary lists; the source gives no frequency vector.
    "battery_impedance_re": ("list<float64>", True),
    "battery_impedance_im": ("list<float64>", True),
    "rectified_impedance_re": ("list<float64>", True),
    "rectified_impedance_im": ("list<float64>", True),
    "quality_flags_json": ("string", False),  # e.g. {"re_complex": ...} when a fit is complex
}

#: Values the database ``cycles`` table requires (NOT NULL in migration 0001). A canonical cycle
#: lacking any of them stays in Parquet with ``db_eligible = false`` and is not imported.
DB_REQUIRED = ("capacity_ah", "soh_pct", "temp_mean_c", "voltage_mean_v")

CHEMISTRY_BASES = ("stated_by_source", "not_stated")
SOH_REFERENCES = ("rated_capacity",)
