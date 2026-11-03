"""Rule-based repairer: the offline stand-in for the model repairer.

It makes small, explainable patches for known failure classes: wrong import
paths, and gate/measurement calls that drift from the spec (missing, extra,
wrong qubit, reversed control/target). Anything else it honestly cannot fix.
"""

from __future__ import annotations

import ast
import re
from difflib import SequenceMatcher

from inkubit.agent.codeparse import GateCall, extract_calls
from inkubit.codegen.template import generate_code
from inkubit.spec.models import CircuitSpec

_IMPORT_FIXES = [
    (re.compile(r"qiskit\.providers\.aer"), "qiskit_aer", "AerSimulator lives in qiskit_aer since Qiskit 1.0"),
    (re.compile(r"from qiskit import Aer\b"), "from qiskit_aer import Aer", "Aer moved to qiskit_aer"),
]


def fix_imports(code: str) -> tuple[str, list[str]]:
    """Rewrite known outdated import paths."""
    changes: list[str] = []
    for pattern, repl, why in _IMPORT_FIXES:
        if pattern.search(code):
            code = pattern.sub(repl, code)
            changes.append(f"fixed the import ({why})")
    return code, changes


def _describe_replace(old: GateCall, new: GateCall) -> str:
    if old.name == new.name and old.name in ("cx", "cz") and old.args == new.args[::-1]:
        return f"swapped control and target back: {old.pretty()} -> {new.pretty()}"
    if old.name == new.name:
        return f"moved the gate to the drawn qubit: {old.pretty()} -> {new.pretty()}"
    return f"replaced {old.pretty()} with {new.pretty()} to match the drawing"


def align_with_spec(code: str, spec: CircuitSpec, noise: str) -> tuple[str, list[str]]:
    """Make the script's gate and measurement calls match the spec, line by line."""
    reference = generate_code(spec, noise=noise)
    ref_calls, ref_lines = extract_calls(reference), reference.split("\n")
    calls, lines = extract_calls(code), code.split("\n")
    if not calls and "build_circuit" not in code:
        return code, []

    matcher = SequenceMatcher(a=[c.key for c in calls], b=[c.key for c in ref_calls], autojunk=False)
    indent = re.match(r"\s*", lines[calls[0].lineno - 1]).group(0) if calls else "    "
    var = calls[0].obj if calls else _circuit_var(code)
    new_block: list[str] = []
    changes: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for c in calls[i1:i2]:
                new_block.extend(lines[c.lineno - 1:c.end_lineno])
            continue
        ref_block = [indent + re.sub(r"^qc\.", f"{var}.", ref_lines[c.lineno - 1].strip()) for c in ref_calls[j1:j2]]
        if tag == "replace":
            for old, new in zip(calls[i1:i2], ref_calls[j1:j2]):
                changes.append(_describe_replace(old, new))
            for old in calls[i1 + (j2 - j1):i2]:
                changes.append(f"removed {old.pretty()}, which is not in the drawing")
            for new in ref_calls[j1 + (i2 - i1):j2]:
                changes.append(f"added the missing {new.pretty()}")
        elif tag == "delete":
            changes += [f"removed {c.pretty()}, which is not in the drawing" for c in calls[i1:i2]]
        elif tag == "insert":
            changes += [f"added the missing {c.pretty()}" for c in ref_calls[j1:j2]]
        new_block.extend(ref_block)
    if not changes:
        return code, []
    if spec.is_dynamic():  # gates sit inside if_test blocks, so rebuilding the call list flat would break them
        return _restore_function(code, reference), changes

    remove = {n for c in calls for n in range(c.lineno, c.end_lineno + 1)}
    if calls:
        anchor = calls[0].lineno - 1
    else:
        anchor = next((i for i, ln in enumerate(lines) if ln.strip() == "return qc"), len(lines))
    out: list[str] = []
    for i, line in enumerate(lines):
        if i == anchor:
            out.extend(new_block)
        if i + 1 not in remove:
            out.append(line)
    return "\n".join(out), changes


def _function_span(code: str, name: str) -> tuple[int, int] | None:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node.lineno, node.end_lineno or node.lineno
    return None


def _restore_function(code: str, reference: str, name: str = "build_circuit") -> str:
    """Replace the script's ``name`` function with the reference's, keeping everything else."""
    ours, theirs = _function_span(code, name), _function_span(reference, name)
    if ours is None or theirs is None:
        return reference
    lines, ref = code.split("\n"), reference.split("\n")
    return "\n".join(lines[:ours[0] - 1] + ref[theirs[0] - 1:theirs[1]] + lines[ours[1]:])


def _circuit_var(code: str) -> str:
    """Name of the variable assigned a QuantumCircuit(...), defaulting to ``qc``."""
    m = re.search(r"^\s*(\w+)\s*=\s*QuantumCircuit\(", code, re.M)
    return m.group(1) if m else "qc"


def rule_based_repair(code: str, spec: CircuitSpec, noise: str, category: str) -> tuple[str, list[str]]:
    """Apply the rules that fit the diagnosis; return (new code, list of changes)."""
    if category == "import_error":
        return fix_imports(code)
    if category in ("no_counts", "lost_entanglement", "wrong_marginal", "mismatch"):
        new, changes = align_with_spec(code, spec, noise)
        if changes:
            return new, changes
    return code, []
