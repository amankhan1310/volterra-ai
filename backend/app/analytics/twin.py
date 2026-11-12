"""Digital twin semantics (v1), added in Phase 3 without changing any existing v1 module.

The prototype colours the pack by temperature (``legacy/ui.js:391-398``, ``core.js:368-372``)::

    d.temp < 30 ? "var(--cy)" : d.temp < 40 ? "var(--am)" : "var(--rd)"

This module returns the semantic band only; colours belong to the frontend. As in JavaScript, a
NaN temperature fails both comparisons and falls into the hottest band.
"""

from __future__ import annotations

from typing import Literal

TemperatureBand = Literal["normal", "warm", "hot"]

WARM_FROM_C = 30.0
HOT_FROM_C = 40.0
#: The prototype draws 24 modules, all showing the pack-level value (no per-cell data exists).
TWIN_MODULE_COUNT = 24


def temperature_band(temp_c: float) -> TemperatureBand:
    """``normal`` below 30 °C, ``warm`` from 30 to below 40 °C, otherwise ``hot``."""
    if temp_c < WARM_FROM_C:
        return "normal"
    if temp_c < HOT_FROM_C:
        return "warm"
    return "hot"
