"""Robust z-score anomaly detection, version 1 (ported from ``legacy/core.js:74-103``).

JavaScript source (per channel)::

    const m = med(vals), mad = med(vals.map((v) => Math.abs(v - m))) || 1e-9,
          sp = (3.5 * mad) / 0.6745;
    vals.forEach((v, i) => {
      const z = (0.6745 * (v - m)) / mad;
      if (Math.abs(z) > 3.5) out.push({ c: i, ..., lo: m - sp, hi: m + sp, z,
                                        sev: Math.abs(z) > 6 ? "h" : "m" });
    });
    // channels: temp (raw), volt (raw), soh residual vs centred 15-cycle rolling median
    return out.sort((a, b) => a.c - b.c);   // stable

Known defects reproduced on purpose (fixed only in v2): **F1**, temperature spikes are missed
because the global median/MAD ignores the sinusoidal baseline; **F2**, capacity-step false
positives; **F7**, the capacity residual uses a centred window, i.e. future cycles.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal

from app.analytics.jsmath import js_truthy
from app.analytics.stats import median
from app.analytics.synthetic import CycleRecord
from app.analytics.types import Provenance

ChannelKey = Literal["temp", "volt", "soh"]
Severity = Literal["high", "medium"]

Z_SCALE = 0.6745
FLAG_ABS_Z = 3.5
HIGH_ABS_Z = 6.0
MAD_FLOOR = 1e-9
RESIDUAL_HALF_WINDOW = 7

DETECTOR = "robust_z"
DETECTOR_VERSION = "v1"


@dataclass(frozen=True)
class ChannelSpec:
    key: ChannelKey
    label: str
    unit: str


CHANNELS: tuple[ChannelSpec, ...] = (
    ChannelSpec("temp", "Temperature excursion", "°C"),
    ChannelSpec("volt", "Voltage dip/spike", "V"),
    ChannelSpec("soh", "Irregular capacity step", "% resid."),
)


@dataclass(frozen=True)
class ChannelStats:
    spec: ChannelSpec
    values: tuple[float, ...]
    median: float
    mad: float
    expected_low: float
    expected_high: float
    z: tuple[float, ...]


@dataclass(frozen=True)
class AnomalyEvent:
    cycle: int
    channel: ChannelKey
    type: str
    value: float
    unit: str
    expected_low: float
    expected_high: float
    z: float
    severity: Severity


@dataclass(frozen=True)
class AnomalyReport:
    channels: tuple[ChannelStats, ...]
    events: tuple[AnomalyEvent, ...]
    detector: str = DETECTOR
    version: str = DETECTOR_VERSION
    mode: str = "retrospective"

    provenance: ClassVar[Provenance] = "fitted"

    def detected_cycles(self, channel: ChannelKey) -> list[int]:
        return [e.cycle for e in self.events if e.channel == channel]

    def count(self, severity: Severity | None = None) -> int:
        return len([e for e in self.events if severity is None or e.severity == severity])


def severity_for(z: float) -> Severity | None:
    """``None`` when not flagged; ``"high"`` above |z| 6, otherwise ``"medium"`` above 3.5."""
    if not abs(z) > FLAG_ABS_Z:
        return None
    return "high" if abs(z) > HIGH_ABS_Z else "medium"


def capacity_residuals_v1(soh: Sequence[float]) -> list[float]:
    """SOH minus the median of the centred window ``[i-7, i+7]``, truncated at the edges (F7)."""
    h = RESIDUAL_HALF_WINDOW
    return [v - median(soh[max(0, i - h) : i + h + 1]) for i, v in enumerate(soh)]


def robust_z_channel(
    spec: ChannelSpec, values: Sequence[float], cycles: Sequence[int]
) -> tuple[ChannelStats, list[AnomalyEvent]]:
    """Median/MAD z-scores for one channel and the events it flags (in cycle order)."""
    m = median(values)
    mad = median([abs(v - m) for v in values])
    if not js_truthy(mad):  # `|| 1e-9`: also replaces NaN, as in JavaScript
        mad = MAD_FLOOR
    spread = (FLAG_ABS_Z * mad) / Z_SCALE
    low, high = m - spread, m + spread
    zs = tuple((Z_SCALE * (v - m)) / mad for v in values)
    events = []
    for cycle, v, z in zip(cycles, values, zs, strict=True):
        severity = severity_for(z)
        if severity is not None:
            events.append(
                AnomalyEvent(cycle, spec.key, spec.label, v, spec.unit, low, high, z, severity)
            )
    stats = ChannelStats(spec, tuple(values), m, mad, low, high, zs)
    return stats, events


def detect_anomalies_v1(records: Sequence[CycleRecord]) -> AnomalyReport:
    """Run the prototype's detector over temperature, voltage and capacity residuals."""
    cycles = [r.cycle for r in records]
    inputs: dict[ChannelKey, list[float]] = {
        "temp": [r.temp_c for r in records],
        "volt": [r.voltage_v for r in records],
        "soh": capacity_residuals_v1([r.soh_pct for r in records]),
    }
    channels: list[ChannelStats] = []
    events: list[AnomalyEvent] = []
    for spec in CHANNELS:
        stats, found = robust_z_channel(spec, inputs[spec.key], cycles)
        channels.append(stats)
        events.extend(found)
    events.sort(key=lambda e: e.cycle)  # stable, like V8's Array.prototype.sort
    return AnomalyReport(channels=tuple(channels), events=tuple(events))
