"""Margin guards: a last-bit difference in sin/exp/pow cannot flip any discrete result.

Fields derived from ``Math.sin``, ``Math.exp`` and ``Math.pow`` may differ from V8 by a few ULP
(about 1e-14 at these magnitudes). These tests prove every threshold decision built on them has
a margin many orders of magnitude larger, so event lists, severities and cycle counts are safe.
"""

from __future__ import annotations

from app.analytics.anomalies import FLAG_ABS_Z, HIGH_ABS_Z, detect_anomalies_v1
from app.analytics.health import recent_trend
from app.analytics.simulator import ScenarioParams, cycles_to_eol, soh_at
from app.analytics.synthetic import generate_synthetic_v1

RECORDS = generate_synthetic_v1()
FADE = recent_trend(RECORDS).fade_pct_per_cycle
Z_MARGIN = 1e-6
SOH_MARGIN = 1e-9


def test_anomaly_z_scores_are_far_from_thresholds() -> None:
    for channel in detect_anomalies_v1(RECORDS).channels:
        closest = min(min(abs(abs(z) - FLAG_ABS_Z), abs(abs(z) - HIGH_ABS_Z)) for z in channel.z)
        assert closest > Z_MARGIN, f"{channel.spec.key}: |z| within {closest} of a threshold"


def test_simulator_eol_crossings_are_far_from_the_threshold(golden) -> None:
    for spec in golden("simulator")["scenarios"]:
        p = ScenarioParams.from_legacy(spec["params"])
        for params in (p, p.with_baseline_conditions()):
            n = cycles_to_eol(params, FADE)
            if not n:  # None (beyond horizon) or 0 (starts at/below EOL): no crossing
                continue
            before = soh_at(params, n - 1, FADE) - params.eol_pct
            at = soh_at(params, n, FADE) - params.eol_pct
            # Strictly above EOL one cycle before the crossing, at/below it at the crossing,
            # and neither value close enough to EOL for a few-ULP difference to matter.
            assert before > 0 >= at, spec["name"]
            assert min(abs(before), abs(at)) > SOH_MARGIN, spec["name"]
