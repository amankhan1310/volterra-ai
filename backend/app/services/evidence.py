"""Loads the committed Phase 8 evidence files (aggregate numbers, generated offline).

``app/evidence/stress_evidence.json`` comes from ``python -m volterra_ml.calibration`` and
``app/evidence/baseline_validation.json`` from ``python -m app.validation.simulator_baseline``;
both were run on the real datasets, and neither holds a single measurement. They are validated
against the response schema when first read, so a malformed file fails loudly.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.schemas.evidence import BaselineValidation, SimulatorEvidenceResponse, StressEvidence

DATA_DIR = Path(__file__).resolve().parents[1] / "evidence"
EVIDENCE_NOTE = (
    "The simulator's temperature, C-rate and depth-of-discharge coefficients are assumed, not "
    "fitted: the public datasets do not isolate them. The evidence below is what the data can "
    "say, with its confounders. The baseline validation shows how far the trend-based baseline "
    "is from the life real cells actually had."
)


@lru_cache(maxsize=1)
def load_evidence(data_dir: Path = DATA_DIR) -> SimulatorEvidenceResponse:
    stress = json.loads((data_dir / "stress_evidence.json").read_text(encoding="utf-8"))
    baseline = json.loads((data_dir / "baseline_validation.json").read_text(encoding="utf-8"))
    # File key "schema" -> "schema_version"; the DoD entry has no evidence by construction.
    stress["schema_version"] = stress.pop("schema")
    baseline["schema_version"] = baseline.pop("schema")
    if stress["dod"].pop("evidence") is not None:
        raise ValueError("stress_evidence.json: unexpected depth-of-discharge evidence")
    return SimulatorEvidenceResponse(
        stress=StressEvidence.model_validate(stress),
        baseline_validation=BaselineValidation.model_validate(baseline),
        note=EVIDENCE_NOTE,
    )
