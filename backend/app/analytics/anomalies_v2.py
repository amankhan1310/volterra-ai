"""Anomaly detection, version 2: detrended robust z and a capacity-step detector (F1, F2).

v1 scores every raw value against the median/MAD of the **whole** series. Temperature follows a
±3 °C sinusoid, which inflates the MAD, so two of the three injected +9 °C spikes (cycles 90 and
251, on the cool part of the wave) stay inside the "normal" band (**F1**, ARCHITECTURE_PLAN.md
§3.6 and §9.4).

v2 removes the slow baseline first: each value's residual from the median of a centred
15-cycle window, then the robust z-score of those residuals (same constants as v1: z scale 0.6745,
flag above |z| 3.5, high above 6). The expected range reported for an event is the local baseline
± the flag threshold, so it follows the wave. Cycles whose centred window would be cut off at the
start or end of the series are **not evaluated** (no verdict from a truncated window).

On ``synthetic-v1`` this finds exactly the injected anomalies: temperature 90, 170, 251 and
voltage 130, 271 (v1: temperature 170 only).

**F2 (capacity steps).** v1 flags SOH residuals from a centred rolling median: the generator
injects no capacity steps, yet cycles 125, 127, 254, 315 and 319 are flagged (|residual|
0.32-0.36 SOH points against noise of about 0.11; 315 and 319 are truncated-window edge effects).
A rolling-median residual also cannot see a real *sustained* step, because the median moves with
it. v2 measures the level change at each cycle directly: the median of the next 10 cycles minus
the level the previous 10 cycles predict (Theil-Sen line, robust to outliers). A step is flagged
only if it is at least ``MIN_STEP_SOH_PCT`` (0.5 SOH points, about 4.6× the noise) **and** its
robust z exceeds 3.5; one event per step (the largest change within ±10 cycles). Cycles without
10 cycles on each side are not evaluated. On ``synthetic-v1`` nothing is flagged; an injected
1.0-point step is.

Standard library only; mirrors the v1 module's structure and result types.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal

from app.analytics.anomalies import (
    CHANNELS,
    FLAG_ABS_Z,
    MAD_FLOOR,
    Z_SCALE,
    AnomalyEvent,
    ChannelKey,
    ChannelSpec,
    Severity,
    severity_for,
)
from app.analytics.stats import median
from app.analytics.synthetic import CycleRecord
from app.analytics.types import Provenance

DetectionMode = Literal["retrospective"]

DETECTOR_V2 = "robust_z_detrended"
DETECTOR_VERSION_V2 = "v2"
#: Centred rolling-median window for point anomalies: i-7 .. i+7 (15 cycles).
POINT_HALF_WINDOW = 7
#: Cycles on each side of a candidate capacity step.
STEP_WINDOW = 10
#: Smallest capacity step reported, in SOH percentage points.
MIN_STEP_SOH_PCT = 0.5

CAPACITY_STEP = ChannelSpec("soh", "Capacity step", "SOH pts")

POINT_CHANNELS: tuple[ChannelSpec, ...] = tuple(c for c in CHANNELS if c.key in ("temp", "volt"))


@dataclass(frozen=True)
class ChannelStatsV2:
    """Detector inputs for the evaluated cycles of one channel, with the scale used."""

    spec: ChannelSpec
    cycles: tuple[int, ...]
    values: tuple[float, ...]
    z: tuple[float, ...]
    median: float
    mad: float
    expected_low: float
    expected_high: float


@dataclass(frozen=True)
class AnomalyReportV2:
    channels: tuple[ChannelStatsV2, ...]
    events: tuple[AnomalyEvent, ...]
    mode: str
    detector: str = DETECTOR_V2
    version: str = DETECTOR_VERSION_V2

    provenance: ClassVar[Provenance] = "fitted"

    def detected_cycles(self, channel: ChannelKey) -> list[int]:
        return [e.cycle for e in self.events if e.channel == channel]

    def count(self, severity: Severity | None = None) -> int:
        return len([e for e in self.events if severity is None or e.severity == severity])


@dataclass(frozen=True)
class Residual:
    """Detector input at one cycle: ``value - baseline``."""

    index: int
    residual: float
    baseline: float


def robust_scale(values: Sequence[float]) -> tuple[float, float]:
    """Median and MAD (floored as in v1, so a flat series cannot divide by zero)."""
    m = median(values)
    mad = median([abs(v - m) for v in values])
    return m, (mad if mad > 0 else MAD_FLOOR)


def residuals_retrospective(
    values: Sequence[float], half: int = POINT_HALF_WINDOW
) -> list[Residual]:
    """Residual from the centred rolling median; edge cycles (truncated window) are skipped."""
    return [
        Residual(i, values[i] - median(values[i - half : i + half + 1]), 0.0)
        for i in range(half, len(values) - half)
    ]


def _with_baseline(values: Sequence[float], residuals: list[Residual]) -> list[Residual]:
    return [Residual(r.index, r.residual, values[r.index] - r.residual) for r in residuals]


def point_channel(
    spec: ChannelSpec,
    values: Sequence[float],
    cycles: Sequence[int],
    residuals: list[Residual],
) -> tuple[ChannelStatsV2, list[AnomalyEvent]]:
    """Robust z of the residuals (one global scale) and the events it flags."""
    m, mad = robust_scale([r.residual for r in residuals])
    spread = FLAG_ABS_Z * mad / Z_SCALE
    zs = [Z_SCALE * (r.residual - m) / mad for r in residuals]
    events = []
    for r, z in zip(residuals, zs, strict=True):
        severity = severity_for(z)
        if severity is not None:
            centre = r.baseline + m
            events.append(
                AnomalyEvent(
                    cycles[r.index],
                    spec.key,
                    spec.label,
                    values[r.index],
                    spec.unit,
                    centre - spread,
                    centre + spread,
                    z,
                    severity,
                )
            )
    stats = ChannelStatsV2(
        spec=spec,
        cycles=tuple(cycles[r.index] for r in residuals),
        values=tuple(r.residual for r in residuals),
        z=tuple(zs),
        median=m,
        mad=mad,
        expected_low=m - spread,
        expected_high=m + spread,
    )
    return stats, events


def theil_sen(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    """Robust line: median of pairwise slopes, then the median intercept."""
    slopes = [
        (ys[j] - ys[i]) / (xs[j] - xs[i])
        for i in range(len(xs))
        for j in range(i + 1, len(xs))
        if xs[j] != xs[i]
    ]
    if not slopes:
        raise ValueError("Theil-Sen needs at least two distinct x values")
    slope = median(slopes)
    return slope, median([y - slope * x for x, y in zip(xs, ys, strict=True)])


def step_size(values: Sequence[float], onset: int, h: int = STEP_WINDOW) -> tuple[float, float]:
    """Level change at ``onset``: median of ``values[onset:onset+h]`` minus the level the previous
    ``h`` values predict for the centre of that window. Returns ``(step, predicted level)``."""
    xs = [float(i) for i in range(onset - h, onset)]
    slope, intercept = theil_sen(xs, values[onset - h : onset])
    predicted = intercept + slope * (onset + (h - 1) / 2)
    return median(values[onset : onset + h]) - predicted, predicted


def steps_retrospective(values: Sequence[float], h: int = STEP_WINDOW) -> list[Residual]:
    """Step size at every onset with ``h`` cycles on both sides (edges are not evaluated)."""
    out = []
    for i in range(h, len(values) - h + 1):
        step, predicted = step_size(values, i, h)
        out.append(Residual(i, step, predicted))
    return out


def suppress_neighbours(candidates: list[tuple[int, float]], radius: int) -> list[int]:
    """Keep each candidate whose |step| is the largest within ``radius`` (one event per step)."""
    return [
        i
        for i, d in candidates
        if all(abs(d) >= abs(e) for j, e in candidates if abs(j - i) <= radius)
    ]


def step_channel(
    cycles: Sequence[int], steps: list[Residual], radius: int = STEP_WINDOW
) -> tuple[ChannelStatsV2, list[AnomalyEvent]]:
    """Capacity steps: |step| >= 0.5 SOH points and robust |z| > 3.5, one event per step."""
    spec = CAPACITY_STEP
    m, mad = robust_scale([s.residual for s in steps])
    spread = FLAG_ABS_Z * mad / Z_SCALE
    zs = [Z_SCALE * (s.residual - m) / mad for s in steps]
    flagged = {
        s.index: (s, z)
        for s, z in zip(steps, zs, strict=True)
        if abs(s.residual) >= MIN_STEP_SOH_PCT and severity_for(z) is not None
    }
    keep = suppress_neighbours([(i, s.residual) for i, (s, _) in flagged.items()], radius)
    events = []
    for i in keep:
        s, z = flagged[i]
        severity = severity_for(z)
        assert severity is not None
        events.append(
            AnomalyEvent(
                cycles[i],
                spec.key,
                spec.label,
                s.residual,
                spec.unit,
                m - spread,
                m + spread,
                z,
                severity,
            )
        )
    stats = ChannelStatsV2(
        spec=spec,
        cycles=tuple(cycles[s.index] for s in steps),
        values=tuple(s.residual for s in steps),
        z=tuple(zs),
        median=m,
        mad=mad,
        expected_low=m - spread,
        expected_high=m + spread,
    )
    return stats, events


def detect_anomalies_v2(
    records: Sequence[CycleRecord], mode: DetectionMode = "retrospective"
) -> AnomalyReportV2:
    """Detrended robust-z detection over temperature and voltage, plus capacity steps."""
    cycles = [r.cycle for r in records]
    inputs: dict[ChannelKey, list[float]] = {
        "temp": [r.temp_c for r in records],
        "volt": [r.voltage_v for r in records],
    }
    channels: list[ChannelStatsV2] = []
    events: list[AnomalyEvent] = []
    for spec in POINT_CHANNELS:
        values = inputs[spec.key]
        residuals = _with_baseline(values, residuals_retrospective(values))
        stats, found = point_channel(spec, values, cycles, residuals)
        channels.append(stats)
        events.extend(found)
    soh = [r.soh_pct for r in records]
    step_stats, steps = step_channel(cycles, steps_retrospective(soh))
    channels.append(step_stats)
    events.extend(steps)
    events.sort(key=lambda e: e.cycle)
    return AnomalyReportV2(channels=tuple(channels), events=tuple(events), mode=mode)
