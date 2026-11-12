"""Parity: lin and median match ``regression.json``."""

from __future__ import annotations

from app.analytics.stats import lin, median
from app.analytics.synthetic import generate_synthetic_v1
from tests.support.golden import assert_matches

FIELD = {"cycle": "cycle", "soh_pct": "soh_pct", "temp_c": "temp_c"}


def fit_dict(fit) -> dict[str, float]:
    return {
        "slope": fit.slope,
        "intercept": fit.intercept,
        "residual_sd": fit.residual_sd,
        "slope_se": fit.slope_se,
    }


def test_prototype_fits_match_golden(golden) -> None:
    records = generate_synthetic_v1()
    fits = golden("regression")["fits"]
    expected = [{k: v for k, v in f.items() if k != "purpose"} for f in fits]
    actual = []
    for spec in expected:
        rows = records[spec["cycles"]["from"] : spec["cycles"]["to_inclusive"] + 1]
        xs = [getattr(r, FIELD[spec["x"]]) for r in rows]
        ys = [getattr(r, FIELD[spec["y"]]) for r in rows]
        actual.append(
            {
                "name": spec["name"],
                "x": spec["x"],
                "y": spec["y"],
                "cycles": spec["cycles"],
                "n": len(rows),
                **fit_dict(lin(xs, ys)),
            }
        )
    # temp_vs_soh (index 3) regresses on temperature, which is derived from Math.sin.
    temp_vs_soh = next(i for i, f in enumerate(expected) if f["name"] == "temp_vs_soh")
    assert_matches(actual, expected, label="regression:fits", tolerant=[(temp_vs_soh, "**")])


def test_lin_test_vectors_match_golden(golden) -> None:
    vectors = golden("regression")["lin_test_vectors"]
    actual = [fit_dict(lin(v["x"], v["y"])) for v in vectors]
    assert_matches(actual, [v["expected"] for v in vectors], label="regression:lin_vectors")


def test_median_test_vectors_match_golden(golden) -> None:
    vectors = golden("regression")["med_test_vectors"]
    actual = [median(v["values"]) for v in vectors]
    assert_matches(actual, [v["expected"] for v in vectors], label="regression:med_vectors")
