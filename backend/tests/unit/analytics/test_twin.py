"""temperature_band(): boundaries and JavaScript comparison semantics."""

from __future__ import annotations

import math

import pytest

from app.analytics.synthetic import generate_synthetic_v1
from app.analytics.twin import TWIN_MODULE_COUNT, temperature_band


@pytest.mark.parametrize(
    ("temp", "band"),
    [
        (-math.inf, "normal"),
        (-10.0, "normal"),
        (29.999999, "normal"),
        (math.nextafter(30.0, 0.0), "normal"),
        (30.0, "warm"),
        (39.999999, "warm"),
        (40.0, "hot"),
        (85.0, "hot"),
        (math.inf, "hot"),
        (math.nan, "hot"),  # NaN fails both `<` tests in JavaScript too
    ],
)
def test_temperature_band_boundaries(temp: float, band: str) -> None:
    assert temperature_band(temp) == band


def test_synthetic_v1_never_reaches_the_hot_band() -> None:
    # The prototype notes red never appears for this dataset (max is about 37 °C).
    bands = {temperature_band(r.temp_c) for r in generate_synthetic_v1()}
    assert bands == {"normal", "warm"}
    assert TWIN_MODULE_COUNT == 24
