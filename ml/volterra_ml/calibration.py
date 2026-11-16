"""Phase 8: what the real data say about the simulator's stress coefficients (read-only).

``python -m volterra_ml.calibration --data-dir <dir> --out <file.json>``

The simulator scales a battery's fade rate by assumed factors for temperature
(``exp(0.06·(T-25))``), C-rate (``1 + 0.4·(C-1)``) and depth of discharge (``(DoD/80)^0.9``).
None of these can be *calibrated* from the public datasets, and this module does not pretend to.
It reports the evidence that exists, with bootstrap confidence intervals over batteries:

* **NASA matched groups.** B0025-B0028 (24 °C) and B0029-B0032 (43 °C) were charged alike and
  discharged to the same cut-off voltages pairwise (2.0/2.2/2.5/2.7 V), but the 24 °C group used
  a 4 A square wave at 50 % duty (2 A mean) and the 43 °C group a constant 4 A. Their fade ratio
  is therefore a *combined* temperature-and-load effect: it can be compared with the assumed
  temperature factor, but it cannot isolate it.
* **Severson fast charging (LFP).** Cycle life against the mean charging C-rate implied by the
  measured charge time (to ~80 % SOC). This covers 3.6-5.3 C fast charging, not the simulator's
  slider range, and one chemistry.

Depth of discharge is not varied in these datasets, so there is no evidence for it.
Aggregate numbers only; no measurement leaves the data directory.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from volterra_ml.modeling.data import Bundle, Cell, FloatArray, load_bundle

SCHEMA = 1
SEED = 7
BOOTSTRAP = 5000
#: NASA README (BatteryAgingARC_25_26_27_28_P1 and _29_30_31_32): pairs share the cut-off voltage.
NASA_PAIRS = (("B0025", "B0029"), ("B0026", "B0030"), ("B0027", "B0031"), ("B0028", "B0032"))
NASA_TEMPS_C = (24.0, 43.0)
FADE_WINDOW = 25  # cycles every matched cell has
ASSUMED_TEMP_EXP_PER_C = 0.06
ASSUMED_C_RATE_LINEAR = 0.4
SEVERSON_CHARGE_WINDOW = (1, 100)
CHARGED_FRACTION = 0.8  # Severson policies charge to 80 % SOC with the fast step


def fade_per_100(cell: Cell, window: int = FADE_WINDOW) -> float:
    """Least-squares SOH loss per 100 cycles over the first ``window`` measured cycles."""
    x, y = cell.cycle[:window], cell.soh[:window]
    if len(x) < window:
        raise ValueError(f"{cell.key}: fewer than {window} cycles")
    xc = x - x.mean()
    return float(-(xc @ (y - y.mean())) / (xc @ xc) * 100.0)


def _interval(samples: FloatArray, level: float = 0.9) -> list[float]:
    finite = samples[np.isfinite(samples)]
    lo, hi = np.quantile(finite, [(1 - level) / 2, (1 + level) / 2])
    return [float(lo), float(hi)]


def nasa_matched(bundle: Bundle) -> dict[str, Any]:
    cells = {c.external_id: c for c in bundle.cells}
    pairs = [(fade_per_100(cells[a]), fade_per_100(cells[b])) for a, b in NASA_PAIRS]
    low = np.array([p[0] for p in pairs])
    high = np.array([p[1] for p in pairs])
    ratio = float(high.mean() / low.mean())
    rng = np.random.default_rng(SEED)
    boot = np.empty(BOOTSTRAP)
    for i in range(BOOTSTRAP):
        idx = rng.integers(0, len(pairs), len(pairs))  # resample matched pairs
        mean_low = low[idx].mean()
        boot[i] = high[idx].mean() / mean_low if mean_low > 0 else np.nan
    delta_t = NASA_TEMPS_C[1] - NASA_TEMPS_C[0]
    assumed = math.exp(ASSUMED_TEMP_EXP_PER_C * delta_t)
    ci = _interval(boot)
    return {
        "dataset": bundle.slug,
        "bundle_checksum": bundle.checksum,
        "pairs": [
            {"low_temp_cell": a, "high_temp_cell": b, "fade_low": lo, "fade_high": hi}
            for (a, b), (lo, hi) in zip(NASA_PAIRS, pairs, strict=True)
        ],
        "fade_unit": f"SOH points per 100 cycles over the first {FADE_WINDOW} cycles",
        "temperatures_c": list(NASA_TEMPS_C),
        "observed_ratio": ratio,
        "observed_ratio_ci90": ci,
        "implied_exp_per_c_if_all_temperature": math.log(ratio) / delta_t,
        "implied_exp_per_c_ci90": [math.log(ci[0]) / delta_t, math.log(ci[1]) / delta_t],
        "use": "exploratory only, not suitable for calibration: temperature and discharge load "
        "change together between the groups, and 4 pairs leave the interval very wide",
        "assumed_factor_for_this_delta": assumed,
        "assumed_within_ci": ci[0] <= assumed <= ci[1],
        "confounder": (
            "mean discharge load differs (2 A square wave at 24 °C vs 4 A constant at 43 °C)"
        ),
        "bootstrap": {"replicates": BOOTSTRAP, "seed": SEED, "unit": "matched pairs"},
    }


def severson_fast_charge(bundle: Bundle) -> dict[str, Any]:
    lives, rates = [], []
    a, b = SEVERSON_CHARGE_WINDOW
    for c in bundle.cells:
        if c.excluded or c.reported_cycle_life is None:
            continue
        charge_s = float(np.nanmedian(c.channels["charge_time_s"][a:b]))
        lives.append(c.reported_cycle_life)
        rates.append(CHARGED_FRACTION * 3600.0 / charge_s)
    life = np.log(np.array(lives))
    rate = np.array(rates)

    def slope(x: FloatArray, y: FloatArray) -> tuple[float, float]:
        xc = x - x.mean()
        s = float(xc @ (y - y.mean()) / (xc @ xc))
        resid = y - (y.mean() + s * xc)
        r2 = 1.0 - float(resid @ resid) / float(((y - y.mean()) ** 2).sum())
        return s, r2

    s, r2 = slope(rate, life)
    rng = np.random.default_rng(SEED)
    boot = np.empty(BOOTSTRAP)
    for i in range(BOOTSTRAP):
        idx = rng.integers(0, len(rate), len(rate))
        boot[i] = slope(rate[idx], life[idx])[0]
    ci = _interval(boot)
    return {
        "dataset": bundle.slug,
        "bundle_checksum": bundle.checksum,
        "cells": len(rate),
        "charge_c_rate_range": [float(rate.min()), float(rate.max())],
        "model": "ln(cycle life) = a + b * mean charging C-rate (from measured charge time)",
        "b_per_c": s,
        "b_per_c_ci90": ci,
        "r2": r2,
        "life_factor_per_extra_c": math.exp(s),
        "life_factor_per_extra_c_ci90": [math.exp(ci[0]), math.exp(ci[1])],
        "assumed_fade_factor_per_extra_c": 1.0 + ASSUMED_C_RATE_LINEAR,
        "applies_to": "LFP/graphite (A123), fast charging 3.6-5.3 C to 80 % SOC, 4 C discharge",
        "bootstrap": {"replicates": BOOTSTRAP, "seed": SEED, "unit": "cells"},
    }


def evidence(nasa_dir: Path, severson_dir: Path) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "evidence, not calibration",
        "temperature": {
            "assumed_exp_per_c": ASSUMED_TEMP_EXP_PER_C,
            "provenance": "assumed",
            "evidence": nasa_matched(load_bundle(nasa_dir)),
        },
        "c_rate": {
            "assumed_linear": ASSUMED_C_RATE_LINEAR,
            "provenance": "assumed",
            "evidence": severson_fast_charge(load_bundle(severson_dir)),
        },
        "dod": {
            "provenance": "assumed",
            "evidence": None,
            "note": "Depth of discharge is not varied in the NASA, CALCE or Severson tests.",
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m volterra_ml.calibration")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    processed = args.data_dir / "processed"
    result = evidence(
        processed / "nasa-pcoe-battery" / "2022-09-18", processed / "severson-2019" / "2019-03-11"
    )
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    t, c = result["temperature"]["evidence"], result["c_rate"]["evidence"]
    print(
        f"NASA 43/24 C fade ratio {t['observed_ratio']:.2f} "
        f"(90% CI {t['observed_ratio_ci90'][0]:.2f}-{t['observed_ratio_ci90'][1]:.2f}); "
        f"assumed factor {t['assumed_factor_for_this_delta']:.2f}"
    )
    print(
        f"Severson: life x{c['life_factor_per_extra_c']:.2f} per extra C (90% CI "
        f"{c['life_factor_per_extra_c_ci90'][0]:.2f}-{c['life_factor_per_extra_c_ci90'][1]:.2f}), "
        f"R2 {c['r2']:.2f}, n={c['cells']}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
