"""Fault injection for demo mode: break the first attempt on purpose.

Each fault is a realistic mistake (the kind a model or a person makes), so the
repair the audience watches is a real repair of a real failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from qcanvas.agent.codeparse import extract_calls
from qcanvas.spec.models import CircuitSpec


@dataclass(frozen=True)
class Fault:
    """A named, describable code fault."""

    name: str
    label: str
    description: str
    applies: Callable[[str, CircuitSpec], bool]
    inject: Callable[[str, CircuitSpec], str]


def _lines(code: str) -> list[str]:
    return code.split("\n")


def _first_call(code: str, names: set[str]):
    return next((c for c in extract_calls(code) if c.name in names), None)


def _drop_lines(code: str, start: int, end: int) -> str:
    lines = _lines(code)
    del lines[start - 1:end]
    return "\n".join(lines)


def _replace_line(code: str, lineno: int, new: str) -> str:
    lines = _lines(code)
    lines[lineno - 1] = new
    return "\n".join(lines)


def _inject_wrong_import(code: str, spec: CircuitSpec) -> str:
    return code.replace("from qiskit_aer import AerSimulator", "from qiskit.providers.aer import AerSimulator")


def _inject_missing_measurement(code: str, spec: CircuitSpec) -> str:
    drop = {n for c in extract_calls(code) if c.name == "measure" for n in range(c.lineno, c.end_lineno + 1)}
    return "\n".join(ln for i, ln in enumerate(_lines(code), start=1) if i not in drop)


def _inject_wrong_qubit(code: str, spec: CircuitSpec) -> str:
    call = _first_call(code, {"h", "x", "y", "z", "s", "t"})
    assert call is not None
    q = int(call.args[0])
    wrong = (q + 1) % spec.num_qubits
    line = _lines(code)[call.lineno - 1]
    new = re.sub(rf"\.{call.name}\(\s*{q}\s*\)", f".{call.name}({wrong})", line, count=1)
    return _replace_line(code, call.lineno, new)


def _inject_swapped_cx(code: str, spec: CircuitSpec) -> str:
    call = _first_call(code, {"cx"})
    assert call is not None
    c, t = call.args
    line = _lines(code)[call.lineno - 1]
    new = re.sub(rf"\.cx\(\s*{c}\s*,\s*{t}\s*\)", f".cx({t}, {c})", line, count=1)
    return _replace_line(code, call.lineno, new)


def _inject_missing_cnot(code: str, spec: CircuitSpec) -> str:
    call = _first_call(code, {"cx"})
    assert call is not None
    return _drop_lines(code, call.lineno, call.end_lineno)


def _inject_fake_result(code: str, spec: CircuitSpec) -> str:
    zeros = "0" * spec.num_clbits
    marker = "    counts = simulator.run(compiled, shots=SHOTS).result().get_counts()"
    return code.replace(marker, marker + f'\n    counts = {{"{zeros}": SHOTS}}  # shortcut: skip the noisy part')


def _has(code: str, names: set[str]) -> bool:
    return _first_call(code, names) is not None


FAULTS: dict[str, Fault] = {f.name: f for f in [
    Fault("wrong_import", "Wrong import",
          "imports AerSimulator from the pre-1.0 path qiskit.providers.aer",
          lambda code, s: "from qiskit_aer import AerSimulator" in code, _inject_wrong_import),
    Fault("missing_measurement", "Missing measurement",
          "drops every measurement, so the run records nothing",
          lambda code, s: _has(code, {"measure"}), _inject_missing_measurement),
    Fault("wrong_qubit_index", "Wrong qubit index",
          "applies the first single-qubit gate to the neighbouring qubit",
          lambda code, s: s.num_qubits > 1 and _has(code, {"h", "x", "y", "z", "s", "t"}), _inject_wrong_qubit),
    Fault("swapped_control_target", "Swapped control and target",
          "reverses the first CNOT (control and target swapped)",
          lambda code, s: _has(code, {"cx"}), _inject_swapped_cx),
    Fault("missing_cnot", "Missing CNOT",
          "deletes the first CNOT, so nothing gets entangled",
          lambda code, s: _has(code, {"cx"}), _inject_missing_cnot),
    Fault("fake_result", "Faked result",
          "overwrites the counts with a made-up all-zeros result (the offline repairer has no rule for this)",
          lambda code, s: "get_counts()" in code, _inject_fake_result),
]}

REPAIRABLE_DEMO_ORDER = ["missing_cnot", "swapped_control_target", "wrong_qubit_index",
                         "missing_measurement", "wrong_import"]


def pick_demo_fault(code: str, spec: CircuitSpec) -> Fault:
    """The most telling fault that applies to this circuit."""
    for name in REPAIRABLE_DEMO_ORDER:
        if FAULTS[name].applies(code, spec):
            return FAULTS[name]
    return FAULTS["wrong_import"]


def inject(code: str, spec: CircuitSpec, name: str) -> tuple[str, Fault]:
    """Apply fault ``name`` (or ``auto``) and return the broken code and the fault."""
    fault = pick_demo_fault(code, spec) if name == "auto" else FAULTS.get(name)
    if fault is None:
        raise ValueError(f"unknown fault '{name}'; choose auto or one of {', '.join(FAULTS)}")
    if not fault.applies(code, spec):
        raise ValueError(f"fault '{fault.name}' does not apply to this circuit")
    broken = fault.inject(code, spec)
    if broken == code:
        if name == "auto":
            for other in REPAIRABLE_DEMO_ORDER:
                alt = FAULTS[other]
                if alt is not fault and alt.applies(code, spec) and (b := alt.inject(code, spec)) != code:
                    return b, alt
        raise ValueError(f"fault '{fault.name}' could not be planted in this script")
    return broken, fault
