"""Quiz-reviewer tools for the ADK generate–review loops. Writer agents do not get these."""

from __future__ import annotations

import ast
import operator
from typing import Any

_BINOPS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARYOPS: dict[type[ast.unaryop], Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_numeric(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_numeric(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
        return float(_UNARYOPS[type(node.op)](_eval_numeric(node.operand)))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left = _eval_numeric(node.left)
        right = _eval_numeric(node.right)
        return float(_BINOPS[type(node.op)](left, right))
    raise ValueError("unsupported numeric expression")


def evaluate_numeric_expression(expression: str) -> float:
    tree = ast.parse(expression.strip(), mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name | ast.Call | ast.Attribute | ast.Subscript):
            raise ValueError("unsupported numeric expression")
    return _eval_numeric(tree)


def check_numeric_answer(expression: str, claimed_value: str) -> dict[str, object]:
    """Compare a claimed numeric key to a safely evaluated expression.

    Reviewer-only. A mismatch means the answer key is wrong and must be rejected.
    """
    try:
        actual = evaluate_numeric_expression(expression)
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        return {
            "ok": False,
            "reject_key": True,
            "reason": f"Could not evaluate expression: {exc}",
            "expression": expression,
            "claimed_value": claimed_value,
        }
    try:
        claimed = float(str(claimed_value).strip())
    except ValueError:
        return {
            "ok": False,
            "reject_key": True,
            "reason": "Claimed value is not a number.",
            "expression": expression,
            "actual": actual,
            "claimed_value": claimed_value,
        }
    matches = abs(actual - claimed) <= 1e-6 * max(1.0, abs(actual))
    if matches:
        return {
            "ok": True,
            "reject_key": False,
            "expression": expression,
            "actual": actual,
            "claimed_value": claimed_value,
        }
    return {
        "ok": False,
        "reject_key": True,
        "reason": "Claimed answer does not match the evaluated expression.",
        "expression": expression,
        "actual": actual,
        "claimed_value": claimed_value,
    }
