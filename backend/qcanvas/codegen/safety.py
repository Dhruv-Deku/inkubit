"""Static safety check for generated (possibly model-written) code.

This is a guard rail, not a sandbox: it rejects scripts that import anything
beyond the simulation stack or reach for files, processes or introspection.
The runner adds a timeout, a scratch directory and a scrubbed environment.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

ALLOWED_IMPORT_ROOTS = frozenset({"qiskit", "qiskit_aer", "json", "math", "cmath", "numpy", "typing", "__future__"})
FORBIDDEN_CALLS = frozenset({
    "eval", "exec", "compile", "open", "__import__", "input", "breakpoint",
    "globals", "locals", "vars", "setattr", "delattr", "memoryview",
})
FORBIDDEN_ATTRS = frozenset({
    "__subclasses__", "__globals__", "__builtins__", "__code__", "__closure__", "__dict__", "__mro__",
})


@dataclass(frozen=True)
class SafetyReport:
    """Result of the static check."""

    ok: bool
    problems: tuple[str, ...] = ()
    syntax_error: str | None = None


def check_code(code: str) -> SafetyReport:
    """Return whether ``code`` passes the static guard, and why not."""
    try:
        tree = ast.parse(code)
    except SyntaxError as err:
        return SafetyReport(ok=False, syntax_error=f"line {err.lineno}: {err.msg}")
    problems: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORT_ROOTS:
                    problems.append(f"line {node.lineno}: import of '{alias.name}' is not allowed")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level or root not in ALLOWED_IMPORT_ROOTS:
                problems.append(f"line {node.lineno}: import from '{node.module}' is not allowed")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            problems.append(f"line {node.lineno}: call to '{node.func.id}' is not allowed")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS:
            problems.append(f"line {node.lineno}: access to '{node.attr}' is not allowed")
    return SafetyReport(ok=not problems, problems=tuple(problems))
