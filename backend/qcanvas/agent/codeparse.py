"""Read the gate calls out of a Qiskit script (for diffing code against the spec)."""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass

GATE_METHODS = frozenset({"h", "x", "y", "z", "s", "t", "rx", "ry", "rz", "cx", "cz", "swap", "measure", "barrier"})


@dataclass(frozen=True)
class GateCall:
    """One ``<circuit>.<gate>(args)`` statement."""

    name: str
    args: tuple[float | int | str, ...]
    lineno: int  # 1-based, first line of the statement
    end_lineno: int
    obj: str = "qc"  # the circuit variable the method is called on

    @property
    def key(self) -> tuple[str, tuple[float | int | str, ...]]:
        return (self.name, self.args)

    def pretty(self) -> str:
        return f"qc.{self.name}({', '.join(_fmt(a) for a in self.args)})"


def _fmt(a: float | int | str) -> str:
    if isinstance(a, float):
        frac = a / math.pi
        for den in (1, 2, 3, 4, 6, 8):
            if abs(frac * den - round(frac * den)) < 1e-9 and round(frac * den) != 0:
                num = round(frac * den)
                top = "pi" if abs(num) == 1 else f"{abs(num)}*pi"
                s = top if den == 1 else f"{top}/{den}"
                return ("-" if num < 0 else "") + s
        return f"{a:.4g}"
    return str(a)


def _eval(node: ast.AST) -> float | int | str:
    """Evaluate a numeric argument made of literals, ``pi`` and + - * /."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id == "pi":
        return math.pi
    if isinstance(node, ast.Attribute) and node.attr == "pi":
        return math.pi
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = _eval(node.operand)
        return -v if not isinstance(v, str) else f"-{v}"
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(left, str) or isinstance(right, str):
            return ast.unparse(node)
        ops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
               ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}
        fn = ops.get(type(node.op))
        return fn(left, right) if fn else ast.unparse(node)
    return ast.unparse(node)


def _normalise(v: float | int | str) -> float | int | str:
    if isinstance(v, float):
        return round(v, 9)
    return v


def extract_calls(code: str, function: str = "build_circuit") -> list[GateCall]:
    """Gate calls inside ``function`` (or the whole module if it is absent)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    scope: ast.AST = tree
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function:
            scope = node
            break
    calls: list[GateCall] = []
    for node in ast.walk(scope):
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            continue
        func = node.value.func
        if isinstance(func, ast.Attribute) and func.attr in GATE_METHODS:
            args = tuple(_normalise(_eval(a)) for a in node.value.args)
            obj = func.value.id if isinstance(func.value, ast.Name) else ast.unparse(func.value)
            calls.append(GateCall(func.attr, args, node.lineno, node.end_lineno or node.lineno, obj))
    return sorted(calls, key=lambda c: c.lineno)
