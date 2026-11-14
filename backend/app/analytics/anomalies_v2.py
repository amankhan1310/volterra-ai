"""Anomaly detection, version 2: detrending, a capacity-step detector and a live mode (F1, F2,
F7).

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

**F7 (two modes).** v1's capacity residual uses a centred window, so it reads future cycles:
fine for reviewing history, invalid for live alerting. v2 has two modes:

* ``"retrospective"`` (default; look back over history): the centred windows above, one robust
  scale per channel over all evaluated cycles.
* ``"causal"`` (live): every verdict at cycle ``t`` uses only cycles ``<= t``. Point channels
  compare each value with a Theil-Sen line through the previous 15 cycles; a capacity step is
  judged once the 10 cycles after its onset have arrived and is reported at that detection cycle;
  the robust scale comes from **earlier** statistics only, and a cycle needs
  ``CAUSAL_MIN_HISTORY`` (60) earlier statistics before it is judged. Changing future data cannot
  change any earlier result.

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

DetectionMode = Literal["retrospective", "causal"]

DETECTOR_V2 = "robust_z_detrended"
DETECTOR_VERSION_V2 = "v2"
#: Centred rolling-median window for point anomalies: i-7 .. i+7 (15 cycles).
POINT_HALF_WINDOW = 7
#: Cycles on each side of a candidate capacity step.
STEP_WINDOW = 10
#: Smallest capacity step reported, in SOH percentage points.
MIN_STEP_SOH_PCT = 0.5
#: Causal mode: previous cycles used to predict the current value of a point channel.
CAUSAL_FIT_WINDOW = 15
#: Causal mode: earlier detector statistics needed before a cycle is judged.
CAUSAL_MIN_HISTORY = 60

CAPACITY_STEP = ChannelSpec("soh", "Capacity step", "SOH pts")

POINT_CHANNELS: tuple[ChannelSpec, ...] = tuple(c for c in CHANNELS if c.key in ("temp", "volt"))


@dataclass(frozen=True)
class ChannelStatsV2:
    """Detector inputs for the evaluated cycles of one channel, with the (latest) scale used."""

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
    mode: DetectionMode
    detector: str = DETECTOR_V2
    version: str = DETECTOR_VERSION_V2

    provenance: ClassVar[Provenance] = "fitted"

    def detected_cycles(self, channel: ChannelKey) -> list[int]:
        return [e.cycle for e in self.events if e.channel == channel]

    def count(self, severity: Severity | None = None) -> int:
        return len([e for e in self.events if severity is None or e.severity == severity])


@dataclass(frozen=True)
class Residual:
    """Detector input at one cycle (``index`` into the records): ``value - baseline``."""

    index: int
    residual: float
    baseline: float


@dataclass(frozen=True)
class Scored:
    """A residual with the robust scale it was judged against and its z-score."""

    residual: Residual
    median: float
    mad: float
    z: float


def robust_scale(values: Sequence[float]) -> tuple[float, float]:
    """Median and MAD (floored as in v1, so a flat series cannot divide by zero)."""
    m = median(values)
    mad = median([abs(v - m) for v in values])
    return m, (mad if mad > 0 else MAD_FLOOR)


def score(residuals: list[Residual], mode: DetectionMode) -> list[Scored]:
    """Robust z of each residual.

    Retrospective: one scale over all residuals. Causal: each residual is scaled by the earlier
    residuals only; the first ``CAUSAL_MIN_HISTORY`` are not judged.
    """
    if mode == "retrospective":
        m, mad = robust_scale([r.residual for r in residuals])
        return [Scored(r, m, mad, Z_SCALE * (r.residual - m) / mad) for r in residuals]
    out = []
    for k in range(CAUSAL_MIN_HISTORY, len(residuals)):
        m, mad = robust_scale([r.residual for r in residuals[:k]])
        r = residuals[k]
        out.append(Scored(r, m, mad, Z_SCALE * (r.residual - m) / mad))
    return out


def channel_stats(spec: ChannelSpec, cycles: Sequence[int], scored: list[Scored]) -> ChannelStatsV2:
    """Per-cycle detector inputs and z-scores; the scale reported is the latest one used."""
    m, mad = (scored[-1].median, scored[-1].mad) if scored else (0.0, MAD_FLOOR)
    spread = FLAG_ABS_Z * mad / Z_SCALE
    return ChannelStatsV2(
        spec=spec,
        cycles=tuple(cycles[s.residual.index] for s in scored),
        values=tuple(s.residual.residual for s in scored),
        z=tuple(s.z for s in scored),
        median=m,
        mad=mad,
        expected_low=m - spread,
        expected_high=m + spread,
    )


def residuals_retrospective(
    values: Sequence[float], half: int = POINT_HALF_WINDOW
) -> list[Residual]:
    """Residual from the centred rolling median; edge cycles (truncated window) are skipped."""
    out = []
    for i in range(half, len(values) - half):
        baseline = median(values[i - half : i + half + 1])
        out.append(Residual(i, values[i] - baseline, baseline))
    return out


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


def residuals_causal(values: Sequence[float], w: int = CAUSAL_FIT_WINDOW) -> list[Residual]:
    """Residual from a Theil-Sen line through the previous ``w`` values (past only)."""
    out = []
    for i in range(w, len(values)):
        slope, intercept = theil_sen([float(k) for k in range(i - w, i)], values[i - w : i])
        baseline = intercept + slope * i
        out.append(Residual(i, values[i] - baseline, baseline))
    return out


def point_channel(
    spec: ChannelSpec,
    values: Sequence[float],
    cycles: Sequence[int],
    residuals: list[Residual],
    mode: DetectionMode,
) -> tuple[ChannelStatsV2, list[AnomalyEvent]]:
    """Point anomalies: robust |z| > 3.5 of the residuals; ranges follow the local baseline."""
    scored = score(residuals, mode)
    events = []
    for s in scored:
        severity = severity_for(s.z)
        if severity is not None:
            spread = FLAG_ABS_Z * s.mad / Z_SCALE
            centre = s.residual.baseline + s.median
            events.append(
                AnomalyEvent(
                    cycles[s.residual.index],
                    spec.key,
                    spec.label,
                    values[s.residual.index],
                    spec.unit,
                    centre - spread,
                    centre + spread,
                    s.z,
                    severity,
                )
            )
    return channel_stats(spec, cycles, scored), events


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


def steps_causal(values: Sequence[float], h: int = STEP_WINDOW) -> list[Residual]:
    """Step size judged at detection cycle ``t`` for the onset ``t-h+1`` (uses cycles <= t)."""
    out = []
    for t in range(2 * h - 1, len(values)):
        step, predicted = step_size(values, t - h + 1, h)
        out.append(Residual(t, step, predicted))
    return out


def suppress_neighbours(candidates: list[tuple[int, float]], radius: int) -> list[int]:
    """Keep each candidate whose |step| is the largest within ``radius`` (one event per step)."""
    return [
        i
        for i, d in candidates
        if all(abs(d) >= abs(e) for j, e in candidates if abs(j - i) <= radius)
    ]


def first_of_each_run(candidates: list[int], radius: int) -> list[int]:
    """Causal de-duplication: keep the first detection of each run (no look-ahead)."""
    return [c for k, c in enumerate(candidates) if k == 0 or c - candidates[k - 1] > radius]


def step_channel(
    cycles: Sequence[int], steps: list[Residual], mode: DetectionMode, radius: int = STEP_WINDOW
) -> tuple[ChannelStatsV2, list[AnomalyEvent]]:
    """Capacity steps: |step| >= 0.5 SOH points and robust |z| > 3.5, one event per step."""
    spec = CAPACITY_STEP
    scored = score(steps, mode)
    flagged = {
        s.residual.index: s
        for s in scored
        if abs(s.residual.residual) >= MIN_STEP_SOH_PCT and severity_for(s.z) is not None
    }
    keep = (
        suppress_neighbours([(i, s.residual.residual) for i, s in flagged.items()], radius)
        if mode == "retrospective"
        else first_of_each_run(list(flagged), radius)
    )
    events = []
    for i in keep:
        s = flagged[i]
        severity = severity_for(s.z)
        assert severity is not None
        spread = FLAG_ABS_Z * s.mad / Z_SCALE
        events.append(
            AnomalyEvent(
                cycles[i],
                spec.key,
                spec.label,
                s.residual.residual,
                spec.unit,
                s.median - spread,
                s.median + spread,
                s.z,
                severity,
            )
        )
    return channel_stats(spec, cycles, scored), events


def detect_anomalies_v2(
    records: Sequence[CycleRecord], mode: DetectionMode = "retrospective"
) -> AnomalyReportV2:
    """Detrended robust-z detection over temperature and voltage, plus capacity steps."""
    cycles = [r.cycle for r in records]
    inputs: dict[ChannelKey, list[float]] = {
        "temp": [r.temp_c for r in records],
        "volt": [r.voltage_v for r in records],
    }
    residuals_for = residuals_retrospective if mode == "retrospective" else residuals_causal
    steps_for = steps_retrospective if mode == "retrospective" else steps_causal
    channels: list[ChannelStatsV2] = []
    events: list[AnomalyEvent] = []
    for spec in POINT_CHANNELS:
        values = inputs[spec.key]
        stats, found = point_channel(spec, values, cycles, residuals_for(values), mode)
        channels.append(stats)
        events.extend(found)
    step_stats, steps = step_channel(cycles, steps_for([r.soh_pct for r in records]), mode)
    channels.append(step_stats)
    events.extend(steps)
    events.sort(key=lambda e: e.cycle)
    return AnomalyReportV2(channels=tuple(channels), events=tuple(events), mode=mode)
