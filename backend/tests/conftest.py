"""Shared pytest fixtures and the golden-parity tolerance report."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from tests.support import golden as golden_support


@pytest.fixture(scope="session")
def golden() -> Callable[[str], dict[str, Any]]:
    """Return a loader for golden fixtures: ``golden("dataset")`` (read-only, cached)."""
    return golden_support.load_golden


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    # Labels starting with "_" belong to the harness's own self-tests and are not reported.
    stats = {k: v for k, v in golden_support.STATS.items() if not k.startswith("_")}
    if not stats:
        return
    tr = terminalreporter
    tr.section("golden parity: numeric comparisons")
    header = ("label", "numeric", "exact", "tol.allowed", "tol.needed", "maxULP")
    tr.write_line(f"{header[0]:42s} " + " ".join(f"{h:>11s}" for h in header[1:]))
    total = golden_support.ComparisonStats()
    for label in sorted(stats):
        s = stats[label]
        total.merge(s)
        values = (s.numeric, s.exact, s.tolerance_allowed, s.tolerance_needed, s.max_ulp)
        tr.write_line(f"{label:42s} " + " ".join(f"{v:11d}" for v in values))
    tr.write_line(
        f"TOTAL: {total.numeric} numeric comparisons, {total.exact} bit-exact, "
        f"{total.tolerance_needed} needed the 1e-12 tolerance "
        f"(of {total.tolerance_allowed} on tolerance-allowed fields), max {total.max_ulp} ULP"
    )


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Run async tests on asyncio only (the API and database stack is asyncio-based)."""
    return "asyncio"
