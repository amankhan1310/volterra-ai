"""Synthetic battery dataset ``synthetic-v1``, ported from ``legacy/core.js:15-32``.

JavaScript source (one shared noise stream ``R = rng(7)``)::

    gn = () => (R() + R() + R() - 1.5) * 1.15
    cap  = NOM * (1 - 0.00028 * i - 0.0000005 * i * i) + gn() * 0.004
    soh  = (cap / NOM) * 100
    temp = 24 + 3 * Math.sin(i / 22) + gn() * 0.6 + ([90, 170, 251].includes(i) ? 9 : 0)
    volt = 3.72 - 0.0002 * i + gn() * 0.01 - ([130, 271].includes(i) ? 0.18 : 0)

Noise draws happen in the order capacity, temperature, voltage for each cycle. Expressions keep
JavaScript's left-to-right grouping so that capacity, SOH and voltage are bit-exact; temperature
uses ``math.sin`` and may differ from V8 in the last bit (see ``backend/tests/golden/README.md``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar

from app.analytics.prng import Mulberry32
from app.analytics.types import Provenance


@dataclass(frozen=True)
class CycleRecord:
    """Pack-level summary of one charge/discharge cycle."""

    cycle: int
    capacity_ah: float
    soh_pct: float
    temp_c: float
    voltage_v: float

    provenance: ClassVar[Provenance] = "simulated"


@dataclass(frozen=True)
class SyntheticConfig:
    dataset_id: str = "synthetic-v1"
    seed: int = 7
    n_cycles: int = 320
    nominal_capacity_ah: float = 2.0
    temp_spike_cycles: tuple[int, ...] = (90, 170, 251)
    temp_spike_c: float = 9.0
    voltage_dip_cycles: tuple[int, ...] = (130, 271)
    voltage_dip_v: float = 0.18


SYNTHETIC_V1 = SyntheticConfig()


def generate_synthetic_v1(config: SyntheticConfig = SYNTHETIC_V1) -> tuple[CycleRecord, ...]:
    """Generate the prototype's seeded synthetic dataset (deterministic)."""
    rand = Mulberry32(config.seed)

    def gn() -> float:
        return (rand() + rand() + rand() - 1.5) * 1.15

    nom = config.nominal_capacity_ah
    records: list[CycleRecord] = []
    for i in range(config.n_cycles):
        cap = nom * (1 - 0.00028 * i - 0.0000005 * i * i) + gn() * 0.004
        soh = (cap / nom) * 100
        spike = config.temp_spike_c if i in config.temp_spike_cycles else 0.0
        temp = 24 + 3 * math.sin(i / 22) + gn() * 0.6 + spike
        dip = config.voltage_dip_v if i in config.voltage_dip_cycles else 0.0
        volt = 3.72 - 0.0002 * i + gn() * 0.01 - dip
        records.append(CycleRecord(i, cap, soh, temp, volt))
    return tuple(records)


def column(records: tuple[CycleRecord, ...], field: str) -> list[float]:
    """Extract one numeric column (the prototype's ``col(k)``)."""
    if field not in {"capacity_ah", "soh_pct", "temp_c", "voltage_v"}:
        raise ValueError(f"unknown column {field!r}")
    return [float(getattr(r, field)) for r in records]
