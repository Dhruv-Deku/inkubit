"""Quantum Rosetta: the languages of quantum computing, translated both ways, every translation checked.

In: Dirac notation (also LaTeX), OpenQASM 2 and 3, Quil and Qiskit gate calls, all read exactly; plain words
through the describe-in-words path; other code (Cirq, PennyLane, Q#, Braket) through Muse Spark, labelled.
Out: the state in Dirac notation and LaTeX, a circuit that prepares it (proven by exact simulation), what
each gate does in words with the state after it, and the same program in eight languages. Qiskit, OpenQASM
and Cirq versions are run here and must give the same state; the rest are written by fixed rules.
"""

from __future__ import annotations

import json
import math
import re
from fractions import Fraction
from functools import lru_cache
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from inkubit import PROJECT_DIR
from inkubit.adapters.base import ModelCall
from inkubit.notation import DiracForm, NotationError, dirac, factor, looks_like_ket, named_qubit, parse_ket, scalar
from inkubit.spec import parse_spec
from inkubit.spec.models import CircuitSpec, Operation

MAX_STEPS = 40
MAX_DIRAC_QUBITS = 8


class ReadError(ValueError):
    """The text could not be translated; the message says why and what would work."""


class Source(BaseModel):
    kind: str  # dirac, qasm, quil, qiskit, code, words
    label: str
    exact: bool
    normalized_from: float | None = None  # the norm as written, when it was not 1
    note: str = ""


class Preparation(BaseModel):
    method: str
    fidelity: float  # |<target|circuit state>|², exact
    gates: int
    two_qubit: int


class Step(BaseModel):
    label: str
    meaning: str  # what the gate does in general
    effect: str  # what it did here, from the exact states before and after
    dirac: str


class LangCode(BaseModel):
    id: str
    name: str
    code: str
    checked: bool  # run here and gave the same state
    note: str


class RosettaResult(BaseModel):
    source: Source
    spec: dict[str, Any]
    target: DiracForm | None = None  # the state as the user wrote it (Dirac input)
    state: DiracForm  # the state the circuit makes, before measurement
    preparation: Preparation | None = None
    steps: list[Step]
    languages: list[LangCode] = Field(default_factory=list)
    calls: list[ModelCall] = Field(default_factory=list)


# ---------------------------------------------------------------- spec helpers

def _snap(x: float) -> float:
    """An angle snapped to a simple fraction of π when it is one (to 1e-9), so it reads as π/4, not 0.785398…"""
    f = Fraction(x / math.pi).limit_denominator(64)
    return float(f) * math.pi if abs(float(f) * math.pi - x) < 1e-9 else x


def _op(gate: str, targets: list[int], controls: list[int] | None = None, params: list[float] | None = None) -> dict[str, Any]:
    return {"gate": gate, "targets": targets, "controls": controls or [], "params": [_snap(p) for p in params or []]}


def make_spec(n: int, ops: list[dict[str, Any]], title: str, measure: bool = True) -> CircuitSpec:
    return parse_spec({"kind": "circuit", "version": "1.0", "num_qubits": n, "num_clbits": n if measure else 0,
                       "operations": ops,
                       "measurements": [{"qubit": q, "clbit": q} for q in range(n)] if measure else [],
                       "metadata": {"title": title[:80], "origin": "text"}})  # type: ignore[return-value]


def statevector(spec: CircuitSpec) -> np.ndarray:
    from qiskit.quantum_info import Statevector

    from inkubit.verify.expected import build_reference_circuit

    return np.asarray(Statevector.from_instruction(build_reference_circuit(spec)).data)


def _fidelity(a: np.ndarray, b: np.ndarray) -> float:
    return float(abs(np.vdot(a, b)) ** 2)


# ---------------------------------------------------------------- what kind of text is it?

_QISKIT_CALL = re.compile(r"\b\w+\s*\.\s*(h|x|y|z|s|t|sdg|tdg|sx|rx|ry|rz|p|cx|cnot|cz|cp|swap|ccx|toffoli|measure|"
                          r"measure_all|barrier)\s*\(")
_QUIL_LINE = re.compile(r"(DAGGER\s+)?(H|X|Y|Z|S|T|I|RX|RY|RZ|PHASE|CNOT|CZ|CPHASE|SWAP|CCNOT)(\([^)]*\))?(\s+\d+)+"
                        r"|MEASURE\s+\d+(\s+\w+\[\d+\])?|DECLARE\s+.*|HALT|PRAGMA\s+.*", re.I)
_CODE_HINTS = re.compile(r"\bcirq\.|\bqml\.|\boperation\s+\w+|\bCircuit\(\)|\bimport\b|\bdef\s|\buse\s+\w+\s*=\s*Qubit|"
                         r"\bqubit\[|;\s*$", re.M)


def detect(text: str) -> str:
    t = text.strip()
    if re.match(r"\s*OPENQASM\b", t, re.I):
        return "qasm"
    if re.search(r"\bbraket\b|\bCircuit\(\)", t):  # Braket's circuit.rx(target, angle) looks like Qiskit but is not
        return "code"
    if _QISKIT_CALL.search(t) or "QuantumCircuit(" in t:
        return "qiskit"
    lines = [ln.split("#")[0].strip() for ln in t.splitlines()]
    lines = [ln for ln in lines if ln]
    if lines and all(_QUIL_LINE.fullmatch(ln) for ln in lines):
        return "quil"
    if looks_like_ket(t):
        return "dirac"
    if _CODE_HINTS.search(t):
        return "code"
    return "words"


# ---------------------------------------------------------------- exact readers

_BASIS = ["h", "x", "y", "z", "s", "t", "sdg", "tdg", "sx", "rx", "ry", "rz", "cx", "cz", "cp", "swap", "ccx",
          "measure"]


def circuit_to_ops(qc: Any, qubit_map: list[int] | None = None) -> list[dict[str, Any]]:
    """Spec operations for a Qiskit circuit already in the spec's gate set (local qubit i -> qubit_map[i])."""
    qmap = qubit_map or list(range(qc.num_qubits))
    ops: list[dict[str, Any]] = []
    for inst in qc.data:
        name = inst.operation.name
        qs = [qmap[qc.find_bit(q).index] for q in inst.qubits]
        if name == "barrier":
            continue
        if name == "measure":
            ops.append({"gate": "MEASURE", "targets": qs, "clbits": [qc.find_bit(c).index for c in inst.clbits]})
            continue
        try:
            params = [float(p) for p in inst.operation.params]
        except TypeError:
            raise ReadError(f"The gate {name} has an angle that is a symbol, not a number.") from None
        g = name.upper()
        if g in ("RX", "RY", "RZ") and abs(math.remainder(params[0], 4 * math.pi)) < 1e-12:
            continue
        if g in ("CX", "CZ"):
            ops.append(_op(g, [qs[1]], [qs[0]]))
        elif g == "CP":
            ops.append(_op("CP", [qs[1]], [qs[0]], params))
        elif g == "CCX":
            ops.append(_op("CCX", [qs[2]], qs[:2]))
        elif g == "SWAP":
            ops.append(_op("SWAP", qs))
        elif g.lower() in _BASIS:
            ops.append(_op(g, qs, params=params))
        else:
            raise ReadError(f"The gate {name} has no counterpart in Inkubit.")
    return ops


def _program(n: int, nclb: int, ops: list[dict[str, Any]], title: str, notes: set[str]) -> CircuitSpec:
    """A spec from read operations; a program that measures nothing gets every qubit measured at the end."""
    measurements = []
    if not any(o["gate"] == "MEASURE" for o in ops):
        measurements = [{"qubit": q, "clbit": q} for q in range(n)]
        nclb = max(nclb, n)
        notes = notes | {"It measures nothing, so every qubit is measured at the end."}
    return parse_spec({"kind": "circuit", "version": "1.0", "num_qubits": n, "num_clbits": nclb, "operations": ops,
                       "measurements": measurements,
                       "metadata": {"title": title, "origin": "text", "notes": " ".join(sorted(notes)) or None}})  # type: ignore[return-value]


def read_qasm(text: str) -> tuple[CircuitSpec, str]:
    from qiskit import qasm2, qasm3, transpile

    t = text.strip()
    v3 = bool(re.match(r"OPENQASM\s+3", t, re.I))
    if not v3 and "include" not in t:
        t = re.sub(r"(OPENQASM\s+2(\.0)?\s*;)", r'\1 include "qelib1.inc";', t, count=1, flags=re.I)
    try:
        qc = qasm3.loads(t) if v3 else qasm2.loads(t, custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS)
    except Exception as err:  # noqa: BLE001 - the parser's own message is the useful part
        raise ReadError(f"The OpenQASM did not parse: {str(err)[:300]}") from None
    if qc.num_qubits > 12 or qc.num_clbits > 12:
        raise ReadError("Inkubit simulates up to 12 qubits and 12 classical bits exactly.")
    qc = transpile(qc, basis_gates=_BASIS, optimization_level=0)
    spec = _program(max(1, qc.num_qubits), qc.num_clbits, circuit_to_ops(qc), "From OpenQASM", set())
    return spec, "OpenQASM 3" if v3 else "OpenQASM 2"


def _angle(expr: str) -> float:
    try:
        return scalar(expr)
    except NotationError as err:
        raise ReadError(f"I could not read the angle '{expr.strip()}': {err}") from None


def read_quil(text: str) -> tuple[CircuitSpec, str]:
    ops: list[dict[str, Any]] = []
    nclb, maxq, maxc, notes = 0, -1, -1, set()
    for raw in text.splitlines():
        line = raw.split("#")[0].strip()
        if not line or re.match(r"(HALT|PRAGMA)\b", line, re.I):
            continue
        m = re.match(r"DECLARE\s+\w+\s+BIT(?:\[(\d+)\])?", line, re.I)
        if m:
            nclb = int(m.group(1) or 1)
            continue
        m = re.fullmatch(r"MEASURE\s+(\d+)(?:\s+\w+\[(\d+)\])?", line, re.I)
        if m:
            q, c = int(m.group(1)), int(m.group(2) if m.group(2) is not None else m.group(1))
            ops.append({"gate": "MEASURE", "targets": [q], "clbits": [c]})
            maxq, maxc = max(maxq, q), max(maxc, c)
            continue
        m = re.fullmatch(r"(DAGGER\s+)?([A-Z]+)(?:\(([^)]*)\))?((?:\s+\d+)+)", line, re.I)
        if not m:
            raise ReadError(f"I could not read the Quil line '{line}'.")
        dag, g, arg, qs = bool(m.group(1)), m.group(2).upper(), m.group(3), [int(x) for x in m.group(4).split()]
        maxq = max(maxq, *qs)
        theta = _angle(arg) * (-1 if dag else 1) if arg is not None else None
        if g == "I":
            continue
        if g in ("H", "X", "Y", "Z"):
            ops.append(_op(g, qs))
        elif g in ("S", "T"):
            ops.append(_op(g + ("DG" if dag else ""), qs))
        elif g in ("RX", "RY", "RZ") and theta is not None:
            ops.append(_op(g, qs, params=[theta]))
        elif g == "PHASE" and theta is not None:
            ops.append(_op("RZ", qs, params=[theta]))
            notes.add("PHASE(θ) is read as RZ(θ): the same gate up to a global phase.")
        elif g == "CNOT":
            ops.append(_op("CX", [qs[1]], [qs[0]]))
        elif g == "CZ":
            ops.append(_op("CZ", [qs[1]], [qs[0]]))
        elif g == "CPHASE" and theta is not None:
            ops.append(_op("CP", [qs[1]], [qs[0]], [theta]))
        elif g == "SWAP":
            ops.append(_op("SWAP", qs))
        elif g == "CCNOT":
            ops.append(_op("CCX", [qs[2]], qs[:2]))
        else:
            raise ReadError(f"The Quil gate {g} has no counterpart in Inkubit.")
    if maxq < 0:
        raise ReadError("There are no gates in that Quil program.")
    return _program(maxq + 1, max(nclb, maxc + 1), ops, "From Quil", notes), "Quil"


def _args(s: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _ints(a: str) -> list[int]:
    a = a.strip()
    m = re.fullmatch(r"range\((\d+)\)", a)
    if m:
        return list(range(int(m.group(1))))
    nums = re.findall(r"-?\d+", a) if a.startswith("[") else ([a] if re.fullmatch(r"\d+", a) else [])
    if not nums:
        raise ReadError(f"'{a}' should be a qubit number (variables are not followed).")
    return [int(x) for x in nums]


_CALL_ARGS = re.compile(r"\b\w+\s*\.\s*(h|x|y|z|s|t|sdg|tdg|sx|rx|ry|rz|p|cx|cnot|cz|cp|swap|ccx|toffoli|measure_all|"
                        r"measure|barrier)\s*\(((?:[^()]|\([^()]*\))*)\)")


def read_qiskit(text: str) -> tuple[CircuitSpec, str]:
    ops: list[dict[str, Any]] = []
    m = re.search(r"QuantumCircuit\(\s*(\d+)\s*(?:,\s*(\d+))?", text)
    n0, c0 = (int(m.group(1)), int(m.group(2)) if m.group(2) else 0) if m else (0, 0)
    maxq, maxc, measure_all, notes = n0 - 1, c0 - 1, False, set()
    for call in _CALL_ARGS.finditer(text):
        g, a = call.group(1).lower(), _args(call.group(2))
        if g == "barrier":
            continue
        if g == "measure_all":
            measure_all = True
            continue
        if g == "measure":
            qs, cs = _ints(a[0]), _ints(a[1]) if len(a) > 1 else _ints(a[0])
            for q, c in zip(qs, cs):
                ops.append({"gate": "MEASURE", "targets": [q], "clbits": [c]})
                maxq, maxc = max(maxq, q), max(maxc, c)
            continue
        if g in ("rx", "ry", "rz", "p"):
            theta, qs = _angle(a[0]), _ints(a[1])
            ops.append(_op("RZ" if g == "p" else g.upper(), qs, params=[theta]))
            if g == "p":
                notes.add("p(θ) is read as RZ(θ): the same gate up to a global phase.")
        elif g == "cp":
            theta, c, t = _angle(a[0]), _ints(a[1])[0], _ints(a[2])[0]
            ops.append(_op("CP", [t], [c], [theta]))
            qs = [c, t]
        elif g in ("cx", "cnot", "cz"):
            c, t = _ints(a[0])[0], _ints(a[1])[0]
            ops.append(_op("CZ" if g == "cz" else "CX", [t], [c]))
            qs = [c, t]
        elif g == "swap":
            qs = [_ints(a[0])[0], _ints(a[1])[0]]
            ops.append(_op("SWAP", qs))
        elif g in ("ccx", "toffoli"):
            qs = [_ints(x)[0] for x in a[:3]]
            ops.append(_op("CCX", [qs[2]], qs[:2]))
        else:
            qs = _ints(a[0])
            ops.append(_op(g.upper(), qs))
        maxq = max(maxq, *qs)
    if not ops and not measure_all:
        raise ReadError("I found no gate calls such as qc.h(0) or qc.cx(0, 1).")
    n = maxq + 1
    if measure_all:
        ops += [{"gate": "MEASURE", "targets": [q], "clbits": [maxc + 1 + q]} for q in range(n)]
        maxc += n
    return _program(n, maxc + 1, ops, "From Qiskit", notes), "Qiskit gate calls"


# ---------------------------------------------------------------- a circuit for any state, proven

def _one_qubit(v: np.ndarray, q: int) -> list[dict[str, Any]]:
    name = named_qubit(v)
    recipe = {"0": [], "1": ["X"], "+": ["H"], "−": ["X", "H"], "+i": ["H", "S"], "−i": ["H", "SDG"]}
    if name is not None:
        return [_op(g, [q]) for g in recipe[name]]
    a, b = v
    theta = 2 * math.atan2(abs(b), abs(a))
    phi = math.remainder(np.angle(b) - np.angle(a), 2 * math.pi)
    ops = [_op("RY", [q], params=[theta])]
    if abs(phi) > 1e-10:
        ops.append(_op("RZ", [q], params=[phi]))
    return ops


def _two_term(v: np.ndarray, qs: list[int]) -> list[dict[str, Any]] | None:
    """a|x⟩ + c|x̄⟩ (GHZ-like): one rotation, a CNOT fan-out and X flips, len(qs)-1 two-qubit gates."""
    k = len(qs)
    nz = [i for i in range(len(v)) if abs(v[i]) > 1e-9]
    if len(nz) != 2 or nz[0] ^ nz[1] != (1 << k) - 1:
        return None
    zero, one = (nz[0], nz[1]) if not (nz[0] >> (k - 1)) & 1 else (nz[1], nz[0])  # lead qubit 0 / 1
    lead = np.array([v[zero], v[one]])
    ops = _one_qubit(lead / np.linalg.norm(lead), qs[0])
    ops += [_op("CX", [q], [qs[0]]) for q in qs[1:]]
    base = format(zero, f"0{k}b")
    ops += [_op("X", [qs[m]]) for m in range(1, k) if base[m] == "1"]
    return ops


def _general(v: np.ndarray, qs: list[int]) -> list[dict[str, Any]]:
    from qiskit import QuantumCircuit, transpile
    from qiskit.circuit.library import StatePreparation

    k = len(qs)
    qc = QuantumCircuit(k)
    qc.append(StatePreparation(v / np.linalg.norm(v)), range(k))
    qc = transpile(qc, basis_gates=["cx", "ry", "rz", "h", "x"], optimization_level=3, seed_transpiler=7)
    ops, touched = [], set()
    for o in circuit_to_ops(qc, [qs[k - 1 - j] for j in range(k)]):  # local qubit j is the block's j-th lowest
        if o["gate"] == "RZ" and o["targets"][0] not in touched:
            continue  # a phase on a qubit still in |0⟩ is only a global phase
        touched.update(o["targets"] + o["controls"])
        ops.append(o)
    return ops


_SEARCH_ONE = ("H", "X", "Z", "S", "SDG", "T", "TDG")


def _nice(v: np.ndarray) -> bool:
    """Amplitudes a Clifford+T circuit can reach in a few gates: magnitudes 2^(-k/2), phases multiples of π/4."""
    for a in v:
        m = abs(a)
        if m < 1e-9:
            continue
        k = -2 * math.log2(m)
        if abs(k - round(k)) > 1e-6 or abs(math.remainder(np.angle(a) / (math.pi / 4), 1)) > 1e-6:
            return False
    return True


def _search(v: np.ndarray, qs: list[int], depth: int, budget: int = 40000) -> list[dict[str, Any]] | None:
    """The shortest circuit of textbook gates (H, X, Z, S, T, their inverses, CX, CZ) that makes ``v``."""
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Operator

    from inkubit.verify.expected import append_operation

    k = len(qs)
    moves = [_op(g, [q]) for g in _SEARCH_ONE for q in range(k)]
    moves += [_op("CX", [t], [c]) for c in range(k) for t in range(k) if c != t]
    moves += [_op("CZ", [t], [c]) for c in range(k) for t in range(c + 1, k)]
    mats = []
    for m in moves:
        qc = QuantumCircuit(k)
        append_operation(qc, Operation(**m))
        mats.append(Operator(qc).data)

    def key(s: np.ndarray) -> bytes:
        i = int(np.argmax(np.abs(s) > 1e-9))
        return np.round(s * np.exp(-1j * np.angle(s[i])), 6).tobytes()

    start = np.zeros(2 ** k, dtype=complex)
    start[0] = 1
    if _fidelity(start, v) > 1 - 1e-9:
        return []
    seen, frontier = {key(start)}, [(start, [])]
    for _ in range(depth):
        nxt = []
        for s, path in frontier:
            for i, mat in enumerate(mats):
                s2 = mat @ s
                if _fidelity(s2, v) > 1 - 1e-9:
                    local = [moves[j] for j in path + [i]]
                    m = {j: qs[k - 1 - j] for j in range(k)}  # local qubit j is the block's j-th lowest
                    return [{**o, "targets": [m[t] for t in o["targets"]], "controls": [m[c] for c in o["controls"]]}
                            for o in local]
                kk = key(s2)
                if kk not in seen:
                    seen.add(kk)
                    nxt.append((s2, path + [i]))
                    if len(seen) > budget:
                        return None
        frontier = nxt
    return None


@lru_cache(maxsize=1)
def _gallery() -> list[tuple[str, int, list[dict[str, Any]], np.ndarray]]:
    out = []
    for path in sorted((PROJECT_DIR / "examples" / "specs").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("kind") != "circuit":
            continue
        try:
            spec = parse_spec(data)
        except Exception:  # noqa: BLE001 - an invalid example is skipped (one is invalid on purpose)
            continue
        if spec.is_dynamic():  # feed-forward branches on measurements, so it prepares no single state
            continue
        ops = [o.model_dump(exclude={"source", "clbits"}) for o in spec.operations if o.gate not in ("MEASURE", "BARRIER")]
        out.append((spec.metadata.title or path.stem, spec.num_qubits, ops, statevector(spec)))  # type: ignore[arg-type]
    return out


def _cost(ops: list[dict[str, Any]]) -> tuple[int, int]:
    return sum(1 for o in ops if o["controls"] or o["gate"] == "SWAP"), len(ops)


def prepare(target: np.ndarray, n: int) -> tuple[list[dict[str, Any]], Preparation]:
    """The cheapest circuit found that makes ``target`` from |0…0⟩, checked by exact simulation."""
    candidates: list[tuple[list[dict[str, Any]], str]] = []
    parts = factor(target, n) if n > 1 else [([0], target)]
    if parts:
        ops, kinds = [], set()
        for qs, v in parts:
            if len(qs) == 1:
                ops += _one_qubit(v, qs[0])
                kinds.add("one rotation per independent qubit")
            else:
                options = []
                if (two := _two_term(v, qs)) is not None:
                    options.append((two, "a GHZ-style fan-out of CNOTs"))
                if len(qs) <= 3 and _nice(v) and (found := _search(v, qs, 6 if len(qs) == 2 else 4)) is not None:
                    options.append((found, "the shortest circuit of textbook gates (exhaustive search)"))
                if not options:
                    options.append((_general(v, qs), "Qiskit's state preparation, compiled and optimized"))
                best, how = min(options, key=lambda o: _cost(o[0]))
                ops += best
                kinds.add(how)
        split = f", built group by group ({len(parts)} independent groups)" if len(parts) > 1 else ""
        candidates.append((ops, " + ".join(sorted(kinds)) + split))
    else:
        candidates.append((_general(target, list(range(n - 1, -1, -1))), "Qiskit's state preparation, compiled and optimized"))
    for title, gn, gops, sv in _gallery():
        if gn == n and _fidelity(sv, target) > 1 - 1e-9:
            candidates.append((gops, f"the textbook circuit: {title}"))
    ops, method = min(candidates, key=lambda c: _cost(c[0]))
    spec = make_spec(n, ops, "State from Dirac notation")
    fid = _fidelity(statevector(spec), target)
    if fid < 1 - 1e-8:
        raise RuntimeError(f"state preparation failed its own check (fidelity {fid})")
    two, total = _cost(ops)
    return ops, Preparation(method=method, fidelity=round(fid, 9), gates=total, two_qubit=two)


# ---------------------------------------------------------------- what each gate does, in words

GATE_MEANING = {
    "H": "Hadamard: turns 0 into an equal mix of 0 and 1, and that mix back into 0",
    "X": "NOT: swaps 0 and 1",
    "Y": "swaps 0 and 1 and adds a phase of ±i",
    "Z": "phase flip: leaves 0 alone and multiplies 1 by −1",
    "S": "quarter-turn phase: multiplies 1 by i",
    "SDG": "undoes S: multiplies 1 by −i",
    "T": "eighth-turn phase: multiplies 1 by e^(iπ/4)",
    "TDG": "undoes T: multiplies 1 by e^(−iπ/4)",
    "SX": "square root of NOT: twice in a row is a NOT",
    "RX": "rotates the qubit about the X axis of the Bloch sphere",
    "RY": "rotates the qubit about the Y axis: moves weight between 0 and 1 with no complex phase",
    "RZ": "rotates the qubit about the Z axis: changes the phase between 0 and 1",
    "CX": "controlled NOT: flips the target wherever the control is 1",
    "CZ": "controlled Z: multiplies by −1 wherever both qubits are 1",
    "CP": "controlled phase: multiplies by e^(iθ) wherever both qubits are 1",
    "SWAP": "swaps the states of two qubits",
    "CCX": "Toffoli: flips the target wherever both controls are 1 (a reversible AND)",
}


def _names(qs: list[int]) -> str:
    names = [f"q{q}" for q in qs]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _effect(op: Operation, before: np.ndarray, after: np.ndarray, fb: DiracForm, fa: DiracForm, n: int) -> str:
    if _fidelity(before, after) > 1 - 1e-9:
        if op.controls:
            idx = np.arange(2 ** n)
            on = np.ones(2 ** n, dtype=bool)
            for c in op.controls:
                on &= ((idx >> c) & 1) == 1
            if float((np.abs(before[on]) ** 2).sum()) < 1e-12:
                return f"Nothing changes: the control{'s are' if len(op.controls) > 1 else ' is'} never 1 here."
        return "Nothing changes: the state was already one this gate leaves alone (up to a global phase)."
    parts = []
    gb, ga = {tuple(g) for g in fb.groups}, {tuple(g) for g in fa.groups}
    grown = [g for g in fa.groups if tuple(g) not in gb]
    lost = [g for g in fb.groups if tuple(g) not in ga]
    if grown:
        parts.append(f"entangles {_names(max(grown, key=len))}")
    elif lost and len(fa.groups) < len(fb.groups) or (lost and sum(map(len, fa.groups)) < sum(map(len, fb.groups))):
        parts.append(f"undoes the entanglement of {_names(max(lost, key=len))}")
    pb, pa = np.abs(before) ** 2, np.abs(after) ** 2
    if np.allclose(pb, pa, atol=1e-9):
        parts.append("changes only phases: every outcome keeps its odds, and the difference shows up later "
                     "through interference")
    elif fa.terms > fb.terms:
        parts.append(f"creates a superposition of {fa.terms} outcomes" if fb.terms == 1
                     else f"spreads the state over {fa.terms} outcomes")
    elif fa.terms < fb.terms:
        parts.append(f"amplitudes interfere and cancel, leaving {fa.terms} outcome{'s' if fa.terms > 1 else ''}")
    elif not parts and op.gate == "X":
        parts.append(f"flips {_names(op.targets)} in every term")
    elif not parts and op.gate == "SWAP":
        parts.append(f"swaps {_names(op.targets)}")
    elif not parts and fa.terms == fb.terms == 1:
        parts.append(f"turns the state into {fa.text}")
    elif not parts:
        parts.append("moves probability between outcomes")
    text = "; ".join(parts)
    return text[0].upper() + text[1:] + "."


def narrate(spec: CircuitSpec) -> list[Step]:
    from inkubit.verify.expected import require_static

    require_static(spec)
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Statevector

    from inkubit.insights.circuit import op_label
    from inkubit.verify.expected import append_operation

    n = spec.num_qubits
    psi = np.zeros(2 ** n, dtype=complex)
    psi[0] = 1
    form = dirac(psi, n)
    steps = [Step(label="start", meaning="every qubit begins as 0", effect="The starting state.", dirac=form.text)]
    for op in spec.operations:
        if op.gate in ("MEASURE", "BARRIER"):
            continue
        if len(steps) > MAX_STEPS:
            break
        qc = QuantumCircuit(n)
        append_operation(qc, op)
        new = np.asarray(Statevector(psi).evolve(qc).data)
        nf = dirac(new, n)
        meaning = GATE_MEANING.get(op.gate, op.gate)
        steps.append(Step(label=op_label(op), meaning=meaning, effect=_effect(op, psi, new, form, nf, n), dirac=nf.text))
        psi, form = new, nf
    return steps


# ---------------------------------------------------------------- the same program in eight languages

def _pi_text(theta: float, pi: str, float_ints: bool = False) -> str:
    f = Fraction(theta / math.pi).limit_denominator(64)
    if abs(float(f) * math.pi - theta) > 1e-9 or f == 0:
        return repr(round(theta, 12))
    num, den = f.numerator, f.denominator
    k = (lambda x: f"{x}.0") if float_ints else str
    top = pi if abs(num) == 1 else f"{k(abs(num))} * {pi}"
    sign = "-" if num < 0 else ""
    return f"{sign}{top}" if den == 1 else f"{sign}{top} / {k(den)}"


def _uses_angles(spec: CircuitSpec) -> bool:
    return any(op.params for op in spec.operations)


def to_qiskit(spec: CircuitSpec) -> str:
    from inkubit.verify.expected import require_static

    require_static(spec)
    one = {"H": "h", "X": "x", "Y": "y", "Z": "z", "S": "s", "T": "t", "SDG": "sdg", "TDG": "tdg", "SX": "sx"}
    lines = ["from qiskit import QuantumCircuit"] + (["import numpy as np"] if _uses_angles(spec) else []) + [
        "", f"qc = QuantumCircuit({spec.num_qubits}, {spec.num_clbits})" if spec.num_clbits else f"qc = QuantumCircuit({spec.num_qubits})"]
    for op in spec.operations:
        g, a = op.gate, (_pi_text(op.params[0], "np.pi") if op.params else "")
        if g in one:
            lines += [f"qc.{one[g]}({q})" for q in op.targets]
        elif g in ("RX", "RY", "RZ"):
            lines += [f"qc.{g.lower()}({a}, {q})" for q in op.targets]
        elif g in ("CX", "CZ"):
            lines.append(f"qc.{g.lower()}({op.controls[0]}, {op.targets[0]})")
        elif g == "CP":
            lines.append(f"qc.cp({a}, {op.controls[0]}, {op.targets[0]})")
        elif g == "SWAP":
            lines.append(f"qc.swap({op.targets[0]}, {op.targets[1]})")
        elif g == "CCX":
            lines.append(f"qc.ccx({op.controls[0]}, {op.controls[1]}, {op.targets[0]})")
        elif g == "MEASURE":
            lines += [f"qc.measure({q}, {c})" for q, c in zip(op.targets, op.clbits)]
    lines += [f"qc.measure({m.qubit}, {m.clbit})" for m in spec.measurements]
    return "\n".join(lines) + "\n"


def to_cirq(spec: CircuitSpec) -> str:
    from inkubit.verify.expected import require_static

    require_static(spec)
    one = {"H": "cirq.H", "X": "cirq.X", "Y": "cirq.Y", "Z": "cirq.Z", "S": "cirq.S", "T": "cirq.T",
           "SDG": "(cirq.S**-1)", "TDG": "(cirq.T**-1)", "SX": "(cirq.X**0.5)"}
    body = []
    for op in spec.operations:
        g, a = op.gate, (_pi_text(op.params[0], "np.pi") if op.params else "")
        if g in one:
            body += [f"{one[g]}(q[{t}])" for t in op.targets]
        elif g in ("RX", "RY", "RZ"):
            body += [f"cirq.{g.lower()}({a})(q[{t}])" for t in op.targets]
        elif g == "CX":
            body.append(f"cirq.CNOT(q[{op.controls[0]}], q[{op.targets[0]}])")
        elif g == "CZ":
            body.append(f"cirq.CZ(q[{op.controls[0]}], q[{op.targets[0]}])")
        elif g == "CP":
            body.append(f"cirq.CZPowGate(exponent=({a}) / np.pi)(q[{op.controls[0]}], q[{op.targets[0]}])")
        elif g == "SWAP":
            body.append(f"cirq.SWAP(q[{op.targets[0]}], q[{op.targets[1]}])")
        elif g == "CCX":
            body.append(f"cirq.CCX(q[{op.controls[0]}], q[{op.controls[1]}], q[{op.targets[0]}])")
    body += [f'cirq.measure(q[{q}], key="c{c}")' for q, c in spec.measured_pairs()]
    head = ["import cirq"] + (["import numpy as np"] if _uses_angles(spec) else [])
    return "\n".join(head + ["", f"q = cirq.LineQubit.range({spec.num_qubits})", "circuit = cirq.Circuit(["]
                     + [f"    {b}," for b in body] + ["])", "# Cirq lists qubit 0 first in its results (Qiskit lists it last)"]) + "\n"


def to_pennylane(spec: CircuitSpec) -> str:
    one = {"H": "qml.Hadamard", "X": "qml.PauliX", "Y": "qml.PauliY", "Z": "qml.PauliZ", "S": "qml.S", "T": "qml.T",
           "SX": "qml.SX"}
    body = []
    for op in spec.operations:
        g, a = op.gate, (_pi_text(op.params[0], "np.pi") if op.params else "")
        if g in one:
            body += [f"{one[g]}(wires={t})" for t in op.targets]
        elif g in ("SDG", "TDG"):
            body += [f"qml.adjoint(qml.{g[0]})(wires={t})" for t in op.targets]
        elif g in ("RX", "RY", "RZ"):
            body += [f"qml.{g}({a}, wires={t})" for t in op.targets]
        elif g == "CX":
            body.append(f"qml.CNOT(wires=[{op.controls[0]}, {op.targets[0]}])")
        elif g == "CZ":
            body.append(f"qml.CZ(wires=[{op.controls[0]}, {op.targets[0]}])")
        elif g == "CP":
            body.append(f"qml.ControlledPhaseShift({a}, wires=[{op.controls[0]}, {op.targets[0]}])")
        elif g == "SWAP":
            body.append(f"qml.SWAP(wires=[{op.targets[0]}, {op.targets[1]}])")
        elif g == "CCX":
            body.append(f"qml.Toffoli(wires=[{op.controls[0]}, {op.controls[1]}, {op.targets[0]}])")
    measured = sorted({q for q, _ in spec.measured_pairs()}, reverse=True)
    ret = f"qml.probs(wires={measured})  # wires listed high to low, so outcomes read like Qiskit's" if measured else "qml.state()"
    head = ["import pennylane as qml"] + (["import numpy as np"] if _uses_angles(spec) else [])
    return "\n".join(head + ["", f'dev = qml.device("default.qubit", wires={spec.num_qubits})', "", "@qml.qnode(dev)",
                             "def circuit():"] + [f"    {b}" for b in body] + [f"    return {ret}"]) + "\n"


def to_qsharp(spec: CircuitSpec) -> str:
    one = {"H": "H", "X": "X", "Y": "Y", "Z": "Z", "S": "S", "T": "T", "SDG": "Adjoint S", "TDG": "Adjoint T"}
    body = []
    for op in spec.operations:
        g = op.gate
        a = _pi_text(op.params[0], "PI()", float_ints=True) if op.params else ""
        if a and "PI" not in a and "." not in a and "e" not in a:
            a += ".0"
        if g in one:
            body += [f"{one[g]}(q[{t}]);" for t in op.targets]
        elif g == "SX":
            body += [f"H(q[{t}]); S(q[{t}]); H(q[{t}]); // √X = H S H" for t in op.targets]
        elif g in ("RX", "RY", "RZ"):
            body += [f"{g[0]}{g[1].lower()}({a}, q[{t}]);" for t in op.targets]
        elif g == "CX":
            body.append(f"CNOT(q[{op.controls[0]}], q[{op.targets[0]}]);")
        elif g == "CZ":
            body.append(f"Controlled Z([q[{op.controls[0]}]], q[{op.targets[0]}]);")
        elif g == "CP":
            body.append(f"Controlled R1([q[{op.controls[0]}]], ({a}, q[{op.targets[0]}]));")
        elif g == "SWAP":
            body.append(f"SWAP(q[{op.targets[0]}], q[{op.targets[1]}]);")
        elif g == "CCX":
            body.append(f"CCNOT(q[{op.controls[0]}], q[{op.controls[1]}], q[{op.targets[0]}]);")
    pairs = sorted(spec.measured_pairs(), key=lambda p: p[1])
    head = ["import Std.Math.*;", ""] if _uses_angles(spec) else []
    ret = [f"    let results = [{', '.join(f'M(q[{q}])' for q, _ in pairs)}];", "    ResetAll(q);", "    return results;"] \
        if pairs else ["    ResetAll(q);", "    return [];"]
    return "\n".join(head + ["operation Main() : Result[] {", f"    use q = Qubit[{spec.num_qubits}];"]
                     + [f"    {b}" for b in body] + ret + ["}"]) + "\n"


def to_quil(spec: CircuitSpec) -> str:
    one = {"H": "H", "X": "X", "Y": "Y", "Z": "Z", "S": "S", "T": "T", "SDG": "DAGGER S", "TDG": "DAGGER T"}
    lines = [f"DECLARE ro BIT[{spec.num_clbits}]"] if spec.num_clbits else []
    for op in spec.operations:
        g = op.gate
        a = _pi_text(op.params[0], "pi").replace(" ", "") if op.params else ""
        if g in one:
            lines += [f"{one[g]} {t}" for t in op.targets]
        elif g == "SX":
            lines += [f"RX(pi/2) {t}  # √X, up to a global phase" for t in op.targets]
        elif g in ("RX", "RY", "RZ"):
            lines += [f"{g}({a}) {t}" for t in op.targets]
        elif g == "CX":
            lines.append(f"CNOT {op.controls[0]} {op.targets[0]}")
        elif g == "CZ":
            lines.append(f"CZ {op.controls[0]} {op.targets[0]}")
        elif g == "CP":
            lines.append(f"CPHASE({a}) {op.controls[0]} {op.targets[0]}")
        elif g == "SWAP":
            lines.append(f"SWAP {op.targets[0]} {op.targets[1]}")
        elif g == "CCX":
            lines.append(f"CCNOT {op.controls[0]} {op.controls[1]} {op.targets[0]}")
    lines += [f"MEASURE {q} ro[{c}]" for q, c in spec.measured_pairs()]
    return "\n".join(lines) + "\n"


def to_braket(spec: CircuitSpec) -> str:
    one = {"H": "h", "X": "x", "Y": "y", "Z": "z", "S": "s", "T": "t", "SDG": "si", "TDG": "ti", "SX": "v"}
    body = []
    for op in spec.operations:
        g, a = op.gate, (_pi_text(op.params[0], "np.pi") if op.params else "")
        if g in one:
            body += [f"circuit.{one[g]}({t})" for t in op.targets]
        elif g in ("RX", "RY", "RZ"):
            body += [f"circuit.{g.lower()}({t}, {a})" for t in op.targets]
        elif g == "CX":
            body.append(f"circuit.cnot({op.controls[0]}, {op.targets[0]})")
        elif g == "CZ":
            body.append(f"circuit.cz({op.controls[0]}, {op.targets[0]})")
        elif g == "CP":
            body.append(f"circuit.cphaseshift({op.controls[0]}, {op.targets[0]}, {a})")
        elif g == "SWAP":
            body.append(f"circuit.swap({op.targets[0]}, {op.targets[1]})")
        elif g == "CCX":
            body.append(f"circuit.ccnot({op.controls[0]}, {op.controls[1]}, {op.targets[0]})")
    head = ["from braket.circuits import Circuit"] + (["import numpy as np"] if _uses_angles(spec) else [])
    return "\n".join(head + ["", "circuit = Circuit()"] + body
                     + ["# Braket measures every qubit at the end of a run unless told otherwise"]) + "\n"


def _cirq_state(code: str, n: int) -> np.ndarray | None:
    try:
        import cirq  # noqa: F401 - only to see whether Cirq is installed
    except ImportError:
        return None
    ns: dict[str, Any] = {}
    exec(code, ns)  # noqa: S102 - our own generated code, built from a validated spec of numbers
    c = ns["circuit"]
    unitary = ns["cirq"].Circuit(op for op in c.all_operations() if not ns["cirq"].is_measurement(op))
    v = ns["cirq"].final_state_vector(unitary, qubit_order=ns["q"], ignore_terminal_measurements=True, dtype=np.complex128)
    return np.asarray(v).reshape([2] * n).transpose(list(range(n - 1, -1, -1))).reshape(-1)  # to Qiskit order


def languages(spec: CircuitSpec) -> list[LangCode]:
    from qiskit import qasm2, qasm3
    from qiskit.quantum_info import Statevector

    from inkubit.insights.circuit import exports

    ref = statevector(spec)
    n = spec.num_qubits
    ex = exports(spec)

    def same(sv: np.ndarray | None) -> tuple[bool, str]:
        if sv is None:
            return False, "not run here (the library is not installed)"
        f = _fidelity(ref, sv)
        return f > 1 - 1e-8, f"run here: same state (fidelity {f:.6f})" if f > 1 - 1e-8 else f"run here: DIFFERENT state ({f:.4f})"

    def qiskit_sv(qc: Any) -> np.ndarray:
        return np.asarray(Statevector.from_instruction(qc.remove_final_measurements(inplace=False)).data)

    out = []
    code = to_qiskit(spec)
    ns: dict[str, Any] = {}
    exec(code, ns)  # noqa: S102 - our own generated code
    ok, note = same(qiskit_sv(ns["qc"]))
    out.append(LangCode(id="qiskit", name="Qiskit", code=code, checked=ok, note=note))
    ok, note = same(qiskit_sv(qasm2.loads(ex.qasm2, custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS)))
    out.append(LangCode(id="qasm2", name="OpenQASM 2", code=ex.qasm2, checked=ok, note=note))
    try:
        sv3: np.ndarray | None = qiskit_sv(qasm3.loads(ex.qasm3))
    except Exception:  # noqa: BLE001 - the optional OpenQASM 3 importer is missing
        sv3 = None
    ok, note = same(sv3)
    out.append(LangCode(id="qasm3", name="OpenQASM 3", code=ex.qasm3, checked=ok, note=note))
    code = to_cirq(spec)
    ok, note = same(_cirq_state(code, n))
    out.append(LangCode(id="cirq", name="Cirq", code=code, checked=ok, note=note))
    rules = "written from the same circuit by fixed rules; not run here"
    out.append(LangCode(id="pennylane", name="PennyLane", code=to_pennylane(spec), checked=False, note=rules))
    out.append(LangCode(id="qsharp", name="Q#", code=to_qsharp(spec), checked=False, note=rules))
    quil = to_quil(spec)
    back = _fidelity(ref, statevector(read_quil(quil)[0]))
    out.append(LangCode(id="quil", name="Quil", code=quil, checked=False,
                        note=rules + (" (read back by Inkubit's Quil reader: same state)" if back > 1 - 1e-8 else "")))
    out.append(LangCode(id="braket", name="Amazon Braket", code=to_braket(spec), checked=False, note=rules))
    return out


# ---------------------------------------------------------------- all together

def _model_read(text: str, kind: str, models: Any) -> tuple[CircuitSpec, ModelCall]:
    from inkubit.textspec import UnknownTextError

    live = models.settings.provider == "meta" and models.settings.has_key
    if kind == "code" and not live:
        raise ReadError("Reading Cirq, PennyLane, Q# or Braket code needs the live model. Offline, Inkubit reads "
                        "Dirac notation, OpenQASM, Quil and Qiskit gate calls exactly.")
    prompt = text if kind == "words" else (
        "Translate this quantum program into the circuit, gate by gate, exactly as written (same qubits, gates, "
        f"angles and measurements; qubit 0 is the program's first qubit):\n{text}")
    try:
        draft = models.reasoning.spec_from_text(prompt)
    except UnknownTextError as err:
        raise ReadError(str(err)) from None
    if draft.spec.get("kind") != "circuit":
        raise ReadError("That describes a network; the Rosetta translates circuits and states.")
    if not draft.valid:
        raise ReadError("The reading was not a valid circuit: " + "; ".join(draft.issues[:3]))
    return parse_spec(draft.spec), draft.call  # type: ignore[return-value]


def translate(text: str, models: Any = None, with_languages: bool = True) -> RosettaResult:
    text = text.strip()
    if not text:
        raise ReadError("There is nothing to translate.")
    kind = detect(text)
    calls: list[ModelCall] = []
    target = prep = None
    if kind == "dirac":
        vec, norm = parse_ket(text)
        n = int(round(math.log2(len(vec))))
        ops, prep = prepare(vec, n)
        spec = make_spec(n, ops, "State from Dirac notation")
        target = dirac(vec, n)
        source = Source(kind="dirac", label="Dirac notation", exact=True,
                        normalized_from=round(norm, 6) if abs(norm - 1) > 1e-6 else None,
                        note="" if abs(norm - 1) <= 1e-6 else f"normalised: the amplitudes as written had length {norm:.4g}")
    elif kind in ("qasm", "quil", "qiskit"):
        spec, label = {"qasm": read_qasm, "quil": read_quil, "qiskit": read_qiskit}[kind](text)
        source = Source(kind=kind, label=label, exact=True, note=spec.metadata.notes or "")
    else:
        if models is None:
            raise ReadError("Plain words and other code languages need the reader; use Dirac notation, OpenQASM, "
                            "Quil or Qiskit gate calls here.")
        spec, call = _model_read(text, kind, models)
        calls.append(call)
        by = "Muse Spark" if call.provider == "meta" else "the offline parser"
        source = Source(kind=kind, label=("plain words" if kind == "words" else "code") + f", read by {by}",
                        exact=call.provider != "meta",
                        note="A model's reading: check the circuit below against what you meant." if call.provider == "meta" else "")
    if spec.num_qubits > MAX_DIRAC_QUBITS and kind != "dirac":
        source.note = (source.note + " " if source.note else "") + "Large state: only the biggest terms are written out."
    sv = statevector(spec)
    return RosettaResult(source=source, spec=spec.model_dump(mode="json", by_alias=True, exclude_none=True),
                         target=target, state=dirac(sv, spec.num_qubits), preparation=prep, steps=narrate(spec),
                         languages=languages(spec) if with_languages else [], calls=calls)


# ---------------------------------------------------------------- a dictionary of the language

DICTIONARY: list[tuple[str, str, str, str | None]] = [
    ("Qubit", "A bit that can be 0, 1 or a weighted mix of both until it is measured.", "|0⟩", None),
    ("Ket |ψ⟩", "Physicists' way of writing a state: |0⟩ and |1⟩ are the two basis states, and a sum of them "
                "with numbers in front is a superposition.", "√3/2|0⟩ + 1/2|1⟩", None),
    ("Superposition", "A qubit (or a register) in a mix of basis states at once. Measuring picks one.", "qc.h(0)", None),
    ("Amplitude", "The number in front of each basis state. Its size squared is the chance of seeing that outcome "
                  "(the Born rule), so 1/2|0⟩ + √3/2|1⟩ gives 0 a quarter of the time.", "1/2|0⟩ + √3/2|1⟩", None),
    ("Phase", "The angle of an amplitude. It never changes the odds by itself, but it decides how amplitudes add up "
              "later.", "qc.h(0)\nqc.z(0)", None),
    ("Relative vs global phase", "Multiplying the whole state by one phase changes nothing you can measure; a phase "
                                  "between terms does.", "qc.h(0)\nqc.s(0)", None),
    ("Interference", "Amplitudes add like waves and can cancel. H then H brings a superposition back to 0; with a Z in "
                     "between it lands on 1.", "qc.h(0)\nqc.z(0)\nqc.h(0)", None),
    ("Measurement", "Looking at qubits: you get 0s and 1s with the Born-rule odds, and the superposition is gone.",
     "qc.h(0)\nqc.measure(0, 0)", None),
    ("Bloch sphere", "A picture of one qubit as a point on a sphere: north is 0, south is 1, and the equator holds the "
                     "equal mixes, told apart by their phase.", "qc.rx(pi/2, 0)", None),
    ("Gate", "A reversible operation on qubits, drawn as a box on a wire. Every gate can be undone.", "qc.x(0)", None),
    ("Hadamard (H)", "The gate that makes an equal superposition from 0 or 1, and turns it back.", "qc.h(0)", None),
    ("CNOT", "Flips the target qubit wherever the control qubit is 1. With a superposed control it creates "
             "entanglement.", "qc.x(0)\nqc.cx(0, 1)", None),
    ("Tensor product ⊗", "How the states of separate qubits combine into one register: |0⟩ ⊗ |1⟩ = |01⟩.", "|0⟩ ⊗ |+⟩", None),
    ("Product state", "A register whose qubits are each in a state of their own; it can be written as a ⊗ of "
                      "one-qubit states.", "|+⟩|−⟩", None),
    ("Entanglement", "Qubits whose joint state cannot be split into one state per qubit. Measuring one tells you "
                     "about the other, however far apart.", "(|00⟩ + |11⟩)/√2", None),
    ("Bell states", "The four maximally entangled two-qubit states, the basic unit of quantum networks.",
     "(|01⟩ − |10⟩)/√2", None),
    ("GHZ state", "All qubits 0 or all 1, in superposition: one shared coin flip for the whole group.", "|GHZ⟩", None),
    ("W state", "Exactly one qubit is 1, but nobody knows which. Its entanglement survives losing a qubit.", "|W⟩", None),
    ("Unitary", "The maths of a gate: a rotation of the state that keeps the total probability 1 and can be undone.",
     "qc.h(0)\nqc.s(0)\nqc.sdg(0)\nqc.h(0)", None),
    ("Decoherence and noise", "Real qubits leak into their surroundings, so phases and entanglement fade. Inkubit "
                              "simulates this with a realistic noise model on every run.", "(|00⟩ + |11⟩)/√2", None),
    ("Fidelity", "How close two states are, from 0 to 1. Inkubit proves its translations with fidelity 1.",
     "|+⟩", None),
    ("Teleportation", "Moving a qubit's state using one shared Bell pair and two classical bits.", "|Φ+⟩", None),
    ("Grover search", "Finds a marked item in √N steps instead of N by amplifying its amplitude.",
     "qc.h(0)\nqc.h(1)\nqc.cz(0, 1)\nqc.h(0)\nqc.h(1)\nqc.x(0)\nqc.x(1)\nqc.cz(0, 1)\nqc.x(0)\nqc.x(1)\nqc.h(0)\nqc.h(1)",
     None),
    ("Shor's algorithm", "Factors numbers by finding a period with the quantum Fourier transform; the reason today's "
                         "public-key encryption must change.", "qc.h(0)\nqc.h(1)", "Shor's algorithm lab"),
    ("QAOA", "A quantum heuristic for optimization: alternate a cost layer and a mixing layer, tune the angles.",
     "|++⟩", "Split the party"),
    ("VQE", "Finds a molecule's lowest energy by tuning a short circuit while a classical optimizer watches the "
            "energy.", "qc.ry(-0.2256, 0)", "Molecule lab"),
    ("Quantum key distribution", "Sharing a secret key with photons: an eavesdropper must measure them, and the errors "
                                  "she causes give her away.", "|+⟩", "Catch the spy"),
    ("Error correction", "Spreading one logical qubit over several physical ones so errors can be found and fixed.",
     "qc.x(0)\nqc.cx(0, 1)\nqc.cx(0, 2)", "Error-correction lab"),
]


@lru_cache(maxsize=1)
def dictionary() -> list[dict[str, Any]]:
    out = []
    for term, plain, example, see in DICTIONARY:
        res = translate(example, None, with_languages=False)
        out.append({"term": term, "plain": plain, "example": example, "dirac": res.state.text,
                    "entangled": bool(res.state.groups), "see": see})
    return out
