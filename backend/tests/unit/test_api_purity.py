"""The API layer must not compute: mappers and routers only copy v1 results.

Any arithmetic in these modules could make API responses differ from ``legacy_v1.analyze()``.
This static scan fails on arithmetic operators, unary minus, augmented assignment, and calls to
numeric builtins or ``math``. (Comparisons, ``len`` and negative literals such as an
index of ``-1`` are allowed.)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
SCANNED = sorted(
    [APP / "services" / "mappers.py", APP / "api" / "deps.py", *(APP / "api" / "v1").glob("*.py")]
)
ARITHMETIC = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.MatMult)
NUMERIC_CALLS = {"round", "sum", "abs", "min", "max", "pow", "divmod", "float", "int"}
NUMERIC_MODULES = {"math", "statistics", "numpy", "np"}


def test_scan_covers_the_api_layer() -> None:
    assert APP / "services" / "mappers.py" in SCANNED
    assert any(p.name == "router.py" for p in SCANNED)


@pytest.mark.parametrize("path", SCANNED, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_no_numeric_computation(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ARITHMETIC):
            problems.append(f"line {node.lineno}: arithmetic {type(node.op).__name__}")
        elif isinstance(node, ast.AugAssign):
            problems.append(f"line {node.lineno}: augmented assignment")
        elif (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.USub)
            and not isinstance(node.operand, ast.Constant)  # literals such as records[-1]
        ):
            problems.append(f"line {node.lineno}: unary minus")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in NUMERIC_CALLS
        ):
            problems.append(f"line {node.lineno}: {node.func.id}()")
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in NUMERIC_MODULES
        ):
            problems.append(f"line {node.lineno}: {node.value.id}.{node.attr}")
    assert problems == [], f"{path.name} computes instead of copying: {problems}"


def test_negative_literals_are_constants_but_negated_names_are_not() -> None:
    tree = ast.parse("a = rows[-1]\nb = -value\n")
    unary = {n.lineno: n for n in ast.walk(tree) if isinstance(n, ast.UnaryOp)}
    assert isinstance(unary[1].operand, ast.Constant)  # rows[-1]: a literal, allowed
    assert not isinstance(unary[2].operand, ast.Constant)  # -value: computation, flagged
