"""Static checks that keep the analytics bit-exact and standard-library only.

* No ``sum()`` (compensated summation in Python 3.12+), ``math.fsum`` or ``round()`` (banker's
  rounding) in analytics code: use ``jsmath`` helpers instead.
* No third-party imports (numpy, pandas, ...) and no ``statistics`` module.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ANALYTICS_DIR = Path(__file__).resolve().parents[2] / "app" / "analytics"
SOURCES = sorted(ANALYTICS_DIR.glob("*.py"))
BANNED_CALLS = {"sum", "round"}
BANNED_ATTRS = {("math", "fsum")}
BANNED_MODULES = {"statistics"}


def test_analytics_sources_found() -> None:
    assert len(SOURCES) >= 12


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_order_changing_arithmetic_builtins(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in BANNED_CALLS, f"{path.name}:{node.lineno} {node.func.id}()"
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert (node.value.id, node.attr) not in BANNED_ATTRS, f"{path.name}:{node.lineno}"


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_only_stdlib_and_local_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        for name in names:
            top = name.split(".")[0]
            assert top not in BANNED_MODULES, f"{path.name}: imports {name}"
            assert top in sys.stdlib_module_names or top in {
                "app",
                "__future__",
            }, f"{path.name}: third-party import {name}"
