"""Map v1 analysis results to API schemas.

Rule (enforced by tests/unit/test_api_purity.py): mappers only **copy** values. No arithmetic,
rounding or aggregation happens here, so API responses carry exactly the numbers produced by
``legacy_v1.analyze()`` and the other v1 analytics functions.
"""

from __future__ import annotations

from app.db.repositories import BatteryInfo
from app.schemas.common import AnalysisContext, data_provenance


def context(battery: BatteryInfo, eol_pct: float | None = None) -> AnalysisContext:
    return AnalysisContext(
        battery_id=battery.id,
        dataset=battery.dataset_slug,
        is_synthetic=battery.is_synthetic,
        data_provenance=data_provenance(battery.is_synthetic),
        eol_pct=eol_pct,
    )
