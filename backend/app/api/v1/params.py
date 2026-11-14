"""Shared query parameters: the opt-in algorithm version and the anomaly detection mode."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Query

from app.analytics.anomalies_v2 import DetectionMode

Algorithm = Literal["v1", "v2"]

AlgorithmQuery = Annotated[
    Algorithm,
    Query(
        description=(
            "Analytics version. 'v1' (default) reproduces the original prototype exactly, "
            "including its documented defects F1-F8. 'v2' (opt-in) uses the corrected methods "
            "(see CHANGELOG.md); its forecast is an interim quadratic, not a production-validated "
            "model."
        ),
    ),
]

ModeQuery = Annotated[
    DetectionMode,
    Query(
        description=(
            "Anomaly detection mode (v2 only). 'retrospective' (default) looks back over the "
            "history using windows centred on each cycle; 'causal' is the live mode and uses only "
            "cycles up to each judged cycle."
        ),
    ),
]
