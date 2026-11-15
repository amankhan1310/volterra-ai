"""The importer's column expectations equal the canonical contract written by volterra_ml.

The backend does not depend on the ml package (decision D6), so the contract module (standard
library only) is loaded from its file. Any drift between producer and consumer fails here.
"""

from __future__ import annotations

import runpy
from pathlib import Path

from app.db import import_dataset as imp

CONTRACT = Path(__file__).resolve().parents[3] / "ml" / "volterra_ml" / "canonical" / "columns.py"


def test_importer_matches_the_canonical_contract() -> None:
    contract = runpy.run_path(str(CONTRACT))
    assert contract["SCHEMA_VERSION"] == imp.SCHEMA_VERSION
    assert contract["BATTERY_COLUMNS"] == imp.BATTERY_COLUMNS
    assert contract["CYCLE_COLUMNS"] == imp.CYCLE_COLUMNS
    assert tuple(contract["DB_REQUIRED"]) == imp.DB_REQUIRED
    assert set(imp.OPTIONAL_CYCLE_COLUMNS) <= set(contract["CYCLE_COLUMNS"])


def test_output_kinds() -> None:
    assert imp.output_kind("samples/B0005_discharge.parquet") == ("samples", "B0005")
    assert imp.output_kind("impedance/B0005.parquet") == ("impedance", "B0005")
    assert imp.output_kind("cycles.parquet") == ("cycles", None)
    assert imp.output_kind("quality_report.json") == ("report", None)
