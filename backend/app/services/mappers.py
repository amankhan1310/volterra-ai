"""Map v1 analysis results to API schemas.

Rule (enforced by tests/unit/test_api_purity.py): mappers only **copy** values. No arithmetic,
rounding or aggregation happens here, so API responses carry exactly the numbers produced by
``legacy_v1.analyze()`` and the other v1 analytics functions.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.analytics.synthetic import CycleRecord
from app.db.repositories import BatteryInfo, DatasetInfo
from app.schemas.common import AnalysisContext, data_provenance
from app.schemas.datasets import BatteryOut, CycleOut, CyclesResponse, DatasetOut


def context(battery: BatteryInfo, eol_pct: float | None = None) -> AnalysisContext:
    return AnalysisContext(
        battery_id=battery.id,
        dataset=battery.dataset_slug,
        is_synthetic=battery.is_synthetic,
        data_provenance=data_provenance(battery.is_synthetic),
        eol_pct=eol_pct,
    )


def dataset_out(d: DatasetInfo) -> DatasetOut:
    # `meta` (internal metadata such as synthetic ground truth) is deliberately not mapped.
    return DatasetOut(
        slug=d.slug,
        name=d.name,
        source=d.source,
        version=d.version,
        licence=d.licence,
        citation=d.citation,
        description=d.description,
        status=d.status,
        checksum=d.checksum,
        synthetic=d.source == "synthetic",
        battery_count=d.battery_count,
    )


def battery_out(b: BatteryInfo) -> BatteryOut:
    return BatteryOut(
        id=b.id,
        external_id=b.external_id,
        dataset=b.dataset_slug,
        dataset_name=b.dataset_name,
        chemistry=b.chemistry,
        form_factor=b.form_factor,
        nominal_capacity_ah=b.nominal_capacity_ah,
        nominal_voltage_v=b.nominal_voltage_v,
        eol_threshold_pct=b.eol_threshold_pct,
        is_synthetic=b.is_synthetic,
        data_provenance=data_provenance(b.is_synthetic),
        cycle_count=b.cycle_count,
    )


CYCLE_UNITS = {"capacity_ah": "Ah", "soh_pct": "%", "temp_c": "°C", "voltage_v": "V"}


def cycle_out(r: CycleRecord) -> CycleOut:
    return CycleOut(
        cycle=r.cycle,
        capacity_ah=r.capacity_ah,
        soh_pct=r.soh_pct,
        temp_c=r.temp_c,
        voltage_v=r.voltage_v,
    )


def cycles_response(battery: BatteryInfo, records: Sequence[CycleRecord]) -> CyclesResponse:
    return CyclesResponse(
        context=context(battery),
        provenance=data_provenance(battery.is_synthetic),
        units=CYCLE_UNITS,
        items=[cycle_out(r) for r in records],
    )
