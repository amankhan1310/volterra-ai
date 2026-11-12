"""Golden fixture loading and JavaScript-aware comparison for the Phase 2 parity tests.

The fixtures in ``backend/tests/golden/`` are the exact outputs of the legacy JavaScript
prototype. Comparison rules (approved for Phase 2):

* Numbers are compared **exactly** (``==``) by default.
* A relative/absolute tolerance of ``1e-12`` is allowed **only** on paths explicitly declared
  by the caller. Those are fields derived from ``Math.sin``, ``Math.exp`` or ``Math.pow``, whose
  last bit can differ between V8 and the platform C library used by Python.
* Integer (discrete) results are always exact, even on tolerance-allowed paths.
* ``null`` must be ``None``; booleans must be booleans; strings must match exactly.
* Non-finite numbers are stored in fixtures as ``"NaN"``, ``"Infinity"`` and ``"-Infinity"``
  and match the corresponding Python floats.

Every comparison is counted, so the test session can report how many comparisons actually
needed the tolerance (see ``tests/conftest.py``).
"""

from __future__ import annotations

import json
import math
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden"
FIXTURE_NAMES = (
    "advisor",
    "anomalies",
    "backtest",
    "dataset",
    "display_rules",
    "insights",
    "manifest",
    "prng",
    "regression",
    "simulator",
    "soh_rul",
)
TOLERANCE = 1e-12
NON_FINITE: dict[str, float] = {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}

Segment = str | int
Path_ = tuple[Segment, ...]
#: A path pattern: ``"*"`` matches any single segment; ``"**"`` (last only) matches the rest.
Pattern = tuple[Segment, ...]


@cache
def load_golden(name: str) -> dict[str, Any]:
    """Load a golden fixture by name (without ``.json``). Treat the result as read-only."""
    with (GOLDEN_DIR / f"{name}.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise TypeError(f"golden fixture {name!r} is not a JSON object")
    return data


def path_matches(path: Path_, pattern: Pattern) -> bool:
    for i, seg in enumerate(pattern):
        if seg == "**":
            return True
        if i >= len(path):
            return False
        if seg != "*" and seg != path[i]:
            return False
    return len(path) == len(pattern)


def ulp_distance(a: float, b: float) -> int:
    """Number of representable doubles between ``a`` and ``b`` (0 means bit-identical)."""

    def ordered(x: float) -> int:
        i: int = struct.unpack("<q", struct.pack("<d", x))[0]
        return i if i >= 0 else -(i & 0x7FFF_FFFF_FFFF_FFFF)

    return abs(ordered(a) - ordered(b))


def format_path(path: Path_) -> str:
    out = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in path)
    return out.lstrip(".") or "<root>"


@dataclass
class ComparisonStats:
    numeric: int = 0
    exact: int = 0
    tolerance_allowed: int = 0
    tolerance_needed: int = 0
    max_ulp: int = 0

    def merge(self, other: ComparisonStats) -> None:
        self.numeric += other.numeric
        self.exact += other.exact
        self.tolerance_allowed += other.tolerance_allowed
        self.tolerance_needed += other.tolerance_needed
        self.max_ulp = max(self.max_ulp, other.max_ulp)


#: Aggregated statistics per comparison label, reported at the end of the test session.
STATS: dict[str, ComparisonStats] = {}


class GoldenMismatchError(AssertionError):
    """Raised when actual values do not match a golden fixture."""


def assert_matches(
    actual: object,
    expected: object,
    *,
    label: str,
    tolerant: Sequence[Pattern] = (),
    max_report: int = 25,
) -> ComparisonStats:
    """Compare ``actual`` with golden ``expected`` under the rules in the module docstring."""
    stats = ComparisonStats()
    errors: list[str] = []
    _compare(actual, expected, (), tuple(tolerant), stats, errors)
    STATS.setdefault(label, ComparisonStats()).merge(stats)
    if errors:
        shown = "\n  ".join(errors[:max_report])
        more = f"\n  ... and {len(errors) - max_report} more" if len(errors) > max_report else ""
        raise GoldenMismatchError(f"{label}: {len(errors)} mismatch(es)\n  {shown}{more}")
    return stats


def _compare(
    actual: object,
    expected: object,
    path: Path_,
    tolerant: tuple[Pattern, ...],
    stats: ComparisonStats,
    errors: list[str],
) -> None:
    where = format_path(path)
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            errors.append(f"{where}: expected an object, got {type(actual).__name__}")
            return
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing or extra:
            errors.append(f"{where}: key mismatch (missing={missing}, unexpected={extra})")
        for key in expected:
            if key in actual:
                _compare(actual[key], expected[key], (*path, key), tolerant, stats, errors)
        return
    if isinstance(expected, list):
        if not isinstance(actual, list | tuple):
            errors.append(f"{where}: expected an array, got {type(actual).__name__}")
            return
        if len(actual) != len(expected):
            errors.append(f"{where}: length {len(actual)} != expected {len(expected)}")
            return
        for i, (a, e) in enumerate(zip(actual, expected, strict=False)):
            _compare(a, e, (*path, i), tolerant, stats, errors)
        return
    if expected is None:
        if actual is not None:
            errors.append(f"{where}: expected null, got {actual!r}")
        return
    if isinstance(expected, bool):
        if not isinstance(actual, bool) or actual != expected:
            errors.append(f"{where}: expected {expected!r}, got {actual!r}")
        return
    if isinstance(expected, str):
        if expected in NON_FINITE and isinstance(actual, float):
            _compare_number(actual, NON_FINITE[expected], path, tolerant, stats, errors)
        elif actual != expected:
            errors.append(f"{where}: expected {expected!r}, got {actual!r}")
        return
    if isinstance(expected, int | float):
        _compare_number(actual, expected, path, tolerant, stats, errors)
        return
    raise TypeError(f"{where}: unsupported fixture value type {type(expected).__name__}")


def _compare_number(
    actual: object,
    expected: float,
    path: Path_,
    tolerant: tuple[Pattern, ...],
    stats: ComparisonStats,
    errors: list[str],
) -> None:
    where = format_path(path)
    if isinstance(actual, bool) or not isinstance(actual, int | float):
        errors.append(f"{where}: expected number {expected!r}, got {actual!r}")
        return
    stats.numeric += 1
    allowed = any(path_matches(path, p) for p in tolerant)
    if allowed:
        stats.tolerance_allowed += 1
    if actual == expected or (math.isnan(actual) and math.isnan(expected)):
        stats.exact += 1
        return
    if not (math.isfinite(actual) and math.isfinite(expected)):
        errors.append(f"{where}: expected {expected!r}, got {actual!r}")
        return
    ulps = ulp_distance(float(actual), float(expected))
    if isinstance(actual, int):
        errors.append(
            f"{where}: integer {actual!r} != expected {expected!r} (discrete: exact only)"
        )
    elif allowed and math.isclose(actual, expected, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
        stats.tolerance_needed += 1
        stats.max_ulp = max(stats.max_ulp, ulps)
    else:
        reason = "outside 1e-12 tolerance" if allowed else "exact match required"
        errors.append(f"{where}: expected {expected!r}, got {actual!r} ({ulps} ULP; {reason})")
