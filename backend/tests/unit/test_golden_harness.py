"""Tests for the golden fixture loader and the JS-aware comparator itself."""

from __future__ import annotations

import math

import pytest

from tests.support.golden import (
    FIXTURE_NAMES,
    GOLDEN_DIR,
    GoldenMismatchError,
    assert_matches,
    format_path,
    load_golden,
    path_matches,
    ulp_distance,
)

ONE_ULP_ABOVE_ONE = math.nextafter(1.0, 2.0)
SELFTEST = "_selftest"  # labels starting with "_" are excluded from the session report


def test_all_eleven_fixtures_load_with_matching_meta() -> None:
    on_disk = sorted(p.stem for p in GOLDEN_DIR.glob("*.json"))
    assert on_disk == sorted(FIXTURE_NAMES)
    assert len(on_disk) == 11
    for name in FIXTURE_NAMES:
        data = load_golden(name)
        assert data["meta"]["fixture"] == name
        assert data["meta"]["schema_version"] == 1


def test_exact_match_passes_and_is_counted() -> None:
    stats = assert_matches(
        {"a": [1, 2.5, None, True, "x"]}, {"a": [1, 2.5, None, True, "x"]}, label=SELFTEST
    )
    assert (stats.numeric, stats.exact, stats.tolerance_needed) == (2, 2, 0)


def test_one_ulp_difference_fails_without_tolerance() -> None:
    with pytest.raises(GoldenMismatchError, match=r"v: .*1 ULP; exact match required"):
        assert_matches({"v": ONE_ULP_ABOVE_ONE}, {"v": 1.0}, label=SELFTEST)


def test_one_ulp_difference_passes_on_allowed_path_and_is_reported() -> None:
    stats = assert_matches(
        {"rows": [[0, ONE_ULP_ABOVE_ONE]]},
        {"rows": [[0, 1.0]]},
        label=SELFTEST,
        tolerant=[("rows", "*", 1)],
    )
    assert (stats.tolerance_allowed, stats.tolerance_needed, stats.max_ulp) == (1, 1, 1)


def test_tolerance_is_bounded_at_1e_minus_12() -> None:
    with pytest.raises(GoldenMismatchError, match="outside 1e-12 tolerance"):
        assert_matches({"v": 1.0 + 1e-9}, {"v": 1.0}, label=SELFTEST, tolerant=[("v",)])


def test_integers_are_exact_even_on_tolerant_paths() -> None:
    with pytest.raises(GoldenMismatchError, match="discrete: exact only"):
        assert_matches({"n": 107}, {"n": 106}, label=SELFTEST, tolerant=[("**",)])


@pytest.mark.parametrize(
    ("encoded", "value"), [("NaN", math.nan), ("Infinity", math.inf), ("-Infinity", -math.inf)]
)
def test_non_finite_strings_match_python_floats(encoded: str, value: float) -> None:
    assert assert_matches({"v": value}, {"v": encoded}, label=SELFTEST).exact == 1


def test_non_finite_mismatches_are_reported() -> None:
    with pytest.raises(GoldenMismatchError):
        assert_matches({"v": math.inf}, {"v": "NaN"}, label=SELFTEST)
    with pytest.raises(GoldenMismatchError):
        assert_matches({"v": 1.0}, {"v": "Infinity"}, label=SELFTEST)
    with pytest.raises(GoldenMismatchError):
        assert_matches({"v": math.nan}, {"v": 1.0}, label=SELFTEST, tolerant=[("v",)])


def test_text_equal_to_a_non_finite_marker_still_compares_as_text() -> None:
    assert_matches({"v": "NaN"}, {"v": "NaN"}, label=SELFTEST)


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        (0, None),
        (None, 0),
        (1, True),
        (True, 1),
        ("1", 1),
        (1.0, "1"),
        ([1], {"a": 1}),
        ({"a": 1}, [1]),
    ],
)
def test_type_mismatches_fail(actual: object, expected: object) -> None:
    with pytest.raises(GoldenMismatchError):
        assert_matches({"v": actual}, {"v": expected}, label=SELFTEST)


def test_key_and_length_mismatches_are_reported_with_paths() -> None:
    with pytest.raises(
        GoldenMismatchError, match=r"key mismatch \(missing=\['b'\], unexpected=\['c'\]\)"
    ):
        assert_matches({"a": 1, "c": 2}, {"a": 1, "b": 2}, label=SELFTEST)
    with pytest.raises(GoldenMismatchError, match=r"xs: length 2 != expected 3"):
        assert_matches({"xs": [1, 2]}, {"xs": [1, 2, 3]}, label=SELFTEST)


def test_mismatch_report_is_truncated() -> None:
    with pytest.raises(GoldenMismatchError, match=r"30 mismatch\(es\)[\s\S]*and 5 more"):
        assert_matches(list(range(30)), [x + 1 for x in range(30)], label=SELFTEST, max_report=25)


def test_unsupported_fixture_types_raise() -> None:
    with pytest.raises(TypeError):
        assert_matches(1, object(), label=SELFTEST)


def test_path_patterns() -> None:
    assert path_matches(("rows", 3, 1), ("rows", "*", 1))
    assert not path_matches(("rows", 3, 0), ("rows", "*", 1))
    assert not path_matches(("rows", 3), ("rows", "*", 1))
    assert not path_matches(("rows", 3, 1, 0), ("rows", "*", 1))
    assert path_matches(("channels", 0, "z", 7), ("channels", 0, "**"))
    assert format_path(("channels", 0, "z", 7)) == "channels[0].z[7]"
    assert format_path(()) == "<root>"


def test_ulp_distance() -> None:
    assert ulp_distance(1.0, 1.0) == 0
    assert ulp_distance(1.0, ONE_ULP_ABOVE_ONE) == 1
    assert ulp_distance(-0.0, 0.0) == 0
    assert ulp_distance(math.nextafter(0.0, -1.0), math.nextafter(0.0, 1.0)) == 2
