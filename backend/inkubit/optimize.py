"""Shorter circuits, proven equal.

Up to three optimizers propose a cheaper version of a circuit:

* rewrite rules, each with a reason a student can check (H·H = 1; a CNOT whose
  control is still |0> never fires; a Z right before measuring changes nothing a
  measurement can see);
* the Qiskit transpiler at optimization level 3, converted back into the spec's gates;
* the two together (rules, then Qiskit, then the rules again);
* Muse Spark (live only), which gets one more try after seeing why a proposal failed.

Nothing is accepted on trust. Every proposal is simulated exactly against the
original and classified: the same gate for every input (process fidelity), the
same output state from |0...0>, or the same measured outcome odds. Only
proposals with the same outcome odds are accepted; a rejected one is shown with
the outcome where it differs. The thresholds are floating-point precision, not
a physics tolerance: a fidelity of 1 - 1e-12 means states 1e-6 apart.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field
from qiskit.quantum_info import Operator, Statevector

from inkubit.adapters.base import ModelCall, Proposal
from inkubit.insights.circuit import MAX_NOISY_QUBITS, noisy_distribution, op_label
from inkubit.sim.noise import get_preset
from inkubit.spec import SpecError, parse_spec
from inkubit.spec.models import SINGLE_QUBIT_GATES, CircuitSpec, Measurement, Operation
from inkubit.verify.expected import build_reference_circuit, ideal_distribution
from inkubit.verify.metrics import hellinger_fidelity, total_variation_distance

SAME_FIDELITY = 1e-12  # 1 - F below this: states closer than 1e-6, i.e. equal to floating-point precision
SAME_ODDS = 1e-9  # total variation distance below this: the same outcome probabilities
MAX_PROCESS_QUBITS = 8  # the unitary comparison stores 4^n numbers; above this, state and odds only
MAX_PASSES = 400
TWO_Q_COST = {"CX": 1, "CZ": 1, "CP": 2, "SWAP": 3, "CCX": 6}  # CNOTs each needs on today's chips
UNITARY_GATES = ["H", "X", "Y", "Z", "S", "T", "SDG", "TDG", "SX", "RX", "RY", "RZ", "CX", "CZ", "CP", "SWAP", "CCX"]

Level = Literal["unitary", "state", "outcomes", "none"]


class Cost(BaseModel):
    gates: int
    two_qubit: int  # CNOTs on hardware: CX and CZ 1, CP 2, SWAP 3, Toffoli 6
    depth: int
    fidelity: float | None = None  # match to the noiseless ideal on realistic hardware (exact)


class Proof(BaseModel):
    level: Level
    process_fidelity: float | None = None
    state_fidelity: float
    outcome_tvd: float
    detail: str


class Rewrite(BaseModel):
    rule: str
    level: Literal["any input", "from |0>", "measured odds"]
    text: str


class Candidate(BaseModel):
    source: Literal["rules", "qiskit", "combined", "muse"]
    label: str
    spec: dict[str, Any] | None = None
    cost: Cost | None = None
    proof: Proof | None = None
    accepted: bool = False  # same outcome odds, proven
    better: bool = False  # accepted and cheaper than the original
    note: str = ""
    rewrites: list[Rewrite] = Field(default_factory=list)
    call: ModelCall | None = None
    attempts: int = 0


class OptimizeResult(BaseModel):
    original: Cost
    candidates: list[Candidate]
    best: int | None = None
    summary: str
    ai_note: str = ""


# ---------------------------------------------------------------- cost and proof

def _gates(ops: list[Operation]) -> list[Operation]:
    return [op for op in ops if op.gate not in ("MEASURE", "BARRIER")]


def cost(spec: CircuitSpec) -> Cost:
    ops = _gates(spec.operations)
    fid = None
    if spec.num_qubits <= MAX_NOISY_QUBITS:
        noisy = noisy_distribution(spec, get_preset("realistic"))
        fid = round(hellinger_fidelity(ideal_distribution(spec), noisy), 6)
    return Cost(gates=sum(len(op.targets) if op.gate in SINGLE_QUBIT_GATES else 1 for op in ops),
                two_qubit=sum(TWO_Q_COST.get(op.gate, 0) for op in ops),
                depth=build_reference_circuit(spec).depth(), fidelity=fid)


def _rank(c: Cost) -> tuple[int, int, int]:
    return (c.two_qubit, c.gates, c.depth)


def prove(original: CircuitSpec, candidate: CircuitSpec) -> Proof:
    """Exact comparison of two circuits on the same qubits and measurements."""
    if candidate.num_qubits != original.num_qubits:
        return Proof(level="none", state_fidelity=0.0, outcome_tvd=1.0,
                     detail=f"It uses {candidate.num_qubits} qubits; the original has {original.num_qubits}.")
    a, b = build_reference_circuit(original), build_reference_circuit(candidate)
    state = float(abs(np.vdot(Statevector(a).data, Statevector(b).data)) ** 2)
    da, db = ideal_distribution(original), ideal_distribution(candidate)
    tvd = total_variation_distance(da, db)
    proc = None
    if original.num_qubits <= MAX_PROCESS_QUBITS:
        d = 2 ** original.num_qubits
        proc = float(abs(np.trace(Operator(a).data.conj().T @ Operator(b).data)) ** 2 / d ** 2)
    clean = lambda x: round(min(1.0, x), 12)  # noqa: E731
    out = dict(process_fidelity=None if proc is None else clean(proc), state_fidelity=clean(state),
               outcome_tvd=round(tvd, 12))
    if proc is not None and 1 - proc < SAME_FIDELITY:
        return Proof(level="unitary", detail="The same gate for every input state (up to a global phase).", **out)
    if 1 - state < SAME_FIDELITY:
        return Proof(level="state", detail="The same final state from |0…0⟩ (up to a global phase); "
                                           "other input states would behave differently.", **out)
    if tvd < SAME_ODDS:
        return Proof(level="outcomes", detail="The same measured outcome odds; the states before measurement "
                                              "differ only in ways a measurement cannot see.", **out)
    worst = max(set(da) | set(db), key=lambda k: abs(da.get(k, 0.0) - db.get(k, 0.0)))
    return Proof(level="none", detail=f"Outcome {worst} has probability {db.get(worst, 0.0):.1%} here but "
                                      f"{da.get(worst, 0.0):.1%} in the original.", **out)


# ---------------------------------------------------------------- rewrite rules

PHASE = {"Z": math.pi, "S": math.pi / 2, "SDG": -math.pi / 2, "T": math.pi / 4, "TDG": -math.pi / 4}
SELF_INVERSE = {"H", "X", "Y", "Z", "CX", "CZ", "SWAP", "CCX"}
DIAGONAL = {"Z", "S", "SDG", "T", "TDG", "RZ", "CZ", "CP"}
CLASSICAL = {"X", "CX", "CCX", "SWAP"}  # gates that only permute basis states
_SYMBOL = {"H": "H", "X": "X", "Y": "Y", "Z": "Z", "CX": "CX", "CZ": "CZ", "SWAP": "SWAP", "CCX": "CCX"}
_EPS = 1e-12


def _phase(op: Operation) -> float | None:
    """A diagonal single-qubit gate as diag(1, e^(i phi)), up to a global phase."""
    if op.gate in PHASE:
        return PHASE[op.gate]
    if op.gate == "RZ":
        return op.params[0]
    return None


def _wrap(phi: float) -> float:
    return math.remainder(phi, 2 * math.pi)


def _phase_gate(q: int, phi: float, source: Any = None) -> Operation | None:
    """The shortest named gate for diag(1, e^(i phi)) on ``q``, or None for the identity."""
    phi = _wrap(phi)
    if abs(phi) < _EPS:
        return None
    for name, v in PHASE.items():
        if abs(_wrap(phi - v)) < _EPS:
            return Operation(gate=name, targets=[q], source=source)
    return Operation(gate="RZ", targets=[q], params=[phi], source=source)


def _cp_angle(op: Operation) -> float | None:
    return math.pi if op.gate == "CZ" else op.params[0] if op.gate == "CP" else None


def _pair_gate(c: int, t: int, theta: float, source: Any = None) -> Operation | None:
    theta = _wrap(theta)
    if abs(theta) < _EPS:
        return None
    if abs(abs(theta) - math.pi) < _EPS:
        return Operation(gate="CZ", controls=[c], targets=[t], source=source)
    return Operation(gate="CP", controls=[c], targets=[t], params=[theta], source=source)


class _Engine:
    """Applies rewrite rules to one circuit until none applies, keeping a reason for each."""

    def __init__(self, spec: CircuitSpec):
        self.spec = spec
        self.n = spec.num_qubits
        ops: list[Operation] = []
        for op in spec.operations:  # one gate per qubit, so each can be removed on its own
            if op.gate in SINGLE_QUBIT_GATES and len(op.targets) > 1:
                ops += [op.model_copy(update={"targets": [q]}) for q in op.targets]
            else:
                ops.append(op)
        self.slots: list[Operation | None] = list(ops)
        self.measurements = list(spec.measurements)
        self.log: list[Rewrite] = []

    # helpers
    def qubits(self, op: Operation) -> list[int]:
        if op.gate == "BARRIER":
            return list(op.targets) or list(range(self.n))
        return [*op.controls, *op.targets]

    def next_on(self, i: int, qs: list[int]) -> int | None:
        want = set(qs)
        for j in range(i + 1, len(self.slots)):
            op = self.slots[j]
            if op is not None and want & set(self.qubits(op)):
                return j
        return None

    def note(self, rule: str, level: str, text: str) -> None:
        self.log.append(Rewrite(rule=rule, level=level, text=text))  # type: ignore[arg-type]

    def result(self) -> CircuitSpec:
        ops = [op for op in self.slots if op is not None]
        return self.spec.model_copy(update={"operations": ops, "measurements": self.measurements})

    # rules that hold for every input
    def tidy(self, i: int, a: Operation) -> bool:
        """A rotation by a named angle is that named gate, and a rotation by nothing is nothing."""
        new: Operation | None
        if a.gate == "RZ":
            new = _phase_gate(a.targets[0], a.params[0], a.source)
        elif a.gate in ("RX", "RY"):
            theta = _wrap(a.params[0])
            new = None if abs(theta) < _EPS else Operation(gate=a.gate[1], targets=list(a.targets), source=a.source) \
                if abs(abs(theta) - math.pi) < _EPS else a
            if new is a and a.gate == "RX" and abs(theta - math.pi / 2) < _EPS:
                new = Operation(gate="SX", targets=list(a.targets), source=a.source)
        elif a.gate == "CP":
            new = _pair_gate(a.controls[0], a.targets[0], a.params[0], a.source)
        else:
            return False
        if new is a or (new is not None and new.gate == a.gate):
            return False
        self.slots[i] = new
        self.note("tidy", "any input", f"{op_label(a)} " + ("does nothing: the angle is a full turn." if new is None
                                                            else f"is {op_label(new)} (up to a global phase)."))
        return True

    def local(self) -> bool:
        for i, a in enumerate(self.slots):
            if a is None or a.gate in ("MEASURE", "BARRIER"):
                continue
            if self.tidy(i, a):
                return True
            qa = self.qubits(a)
            j = self.next_on(i, qa)
            if j is None:
                continue
            b = self.slots[j]
            assert b is not None
            if b.gate not in ("MEASURE", "BARRIER") and set(self.qubits(b)) == set(qa) and self.pair(i, a, j, b):
                return True
            if a.gate == "H" and self.around_h(i, a, j, b):
                return True
        return False

    def pair(self, i: int, a: Operation, j: int, b: Operation) -> bool:
        la, lb = op_label(a), op_label(b)
        if a.gate == b.gate and a.gate in SELF_INVERSE:
            same = (a.controls == b.controls and a.targets == b.targets) if a.gate == "CX" else \
                (set(a.controls) == set(b.controls) and a.targets == b.targets) if a.gate == "CCX" else True
            if same:
                self.slots[i] = self.slots[j] = None
                g = _SYMBOL[a.gate]
                self.note("cancel", "any input", f"{la} twice in a row cancels ({g}·{g} = 1).")
                return True
        pa, pb = _phase(a), _phase(b)
        if pa is not None and pb is not None:
            merged = _phase_gate(a.targets[0], pa + pb, a.source)
            self.slots[i], self.slots[j] = merged, None
            self.note("merge", "any input", f"{la} then {lb} " + (
                "cancel: together they do nothing." if merged is None else f"combine into {op_label(merged)}."))
            return True
        if a.gate == b.gate and a.gate in ("RX", "RY"):
            theta = _wrap(a.params[0] + b.params[0])
            merged = None if abs(theta) < _EPS else a.model_copy(update={"params": [theta]})
            self.slots[i], self.slots[j] = merged, None
            self.note("merge", "any input", f"{la} then {lb} " + (
                "cancel: the turns add up to a full circle." if merged is None else f"combine into {op_label(merged)}."))
            return True
        if a.gate == b.gate == "SX":
            self.slots[i], self.slots[j] = Operation(gate="X", targets=list(a.targets), source=a.source), None
            self.note("merge", "any input", f"√X twice on q{a.targets[0]} is an X (√X·√X = X).")
            return True
        ta, tb = _cp_angle(a), _cp_angle(b)
        if ta is not None and tb is not None:
            merged = _pair_gate(a.controls[0], a.targets[0], ta + tb, a.source)
            self.slots[i], self.slots[j] = merged, None
            self.note("merge", "any input", f"{la} then {lb} " + (
                "cancel: together they do nothing." if merged is None else f"combine into {op_label(merged)}."))
            return True
        return False

    def around_h(self, i: int, a: Operation, j: int, b: Operation) -> bool:
        """H on both sides: HZH = X, HXH = Z, and H on a target turns CX into CZ and back."""
        q = a.targets[0]
        k = self.next_on(j, [q])
        if k is None:
            return False
        c = self.slots[k]
        assert c is not None
        if c.gate != "H" or c.targets != [q]:
            return False
        if b.gate in ("Z", "X") and b.targets == [q]:
            new = "X" if b.gate == "Z" else "Z"
            self.slots[i], self.slots[j], self.slots[k] = Operation(gate=new, targets=[q], source=b.source), None, None
            self.note("conjugate", "any input", f"H, {b.gate}, H on q{q} is a single {new} (H{b.gate}H = {new}).")
            return True
        if b.gate == "CX" and b.targets == [q]:
            self.slots[j] = Operation(gate="CZ", controls=list(b.controls), targets=[q], source=b.source)
            self.slots[i] = self.slots[k] = None
            self.note("conjugate", "any input",
                      f"H on q{q} on both sides of {op_label(b)} turns it into CZ q{b.controls[0]}→q{q} (HXH = Z).")
            return True
        if b.gate == "CZ" and q in (*b.controls, *b.targets):
            other = b.controls[0] if b.targets == [q] else b.targets[0]
            self.slots[j] = Operation(gate="CX", controls=[other], targets=[q], source=b.source)
            self.slots[i] = self.slots[k] = None
            self.note("conjugate", "any input",
                      f"H on q{q} on both sides of {op_label(b)} turns it into CX q{other}→q{q} (HZH = X).")
            return True
        return False

    # rules that use the starting state |0...0>
    def start(self) -> bool:
        known: dict[int, int] = {q: 0 for q in range(self.n)}  # qubits still in a known basis state
        changed = False

        def ket(q: int) -> str:
            return f"|{known[q]}⟩"

        for i, op in enumerate(self.slots):
            if op is None or op.gate in ("MEASURE", "BARRIER"):
                continue
            g, lab = op.gate, op_label(op)
            if g in SINGLE_QUBIT_GATES:
                q = op.targets[0]
                if q not in known:
                    continue
                if _phase(op) is not None:
                    self.slots[i] = None
                    self.note("start", "from |0>", f"{lab}: q{q} is still {ket(q)} here, so it only adds a global "
                                                   "phase and changes nothing.")
                    changed = True
                elif g in ("X", "Y"):
                    known[q] ^= 1
                else:
                    del known[q]
            elif g == "CX":
                c, t = op.controls[0], op.targets[0]
                if c in known and known[c] == 0:
                    self.slots[i] = None
                    self.note("start", "from |0>", f"{lab}: the control q{c} is still |0⟩ here, so it never fires.")
                    changed = True
                elif c in known:
                    self.slots[i] = Operation(gate="X", targets=[t], source=op.source)
                    self.note("start", "from |0>", f"{lab}: the control q{c} is |1⟩ here, so it always fires; "
                                                   f"it is just an X on q{t}.")
                    changed = True
                    if t in known:
                        known[t] ^= 1
                else:
                    known.pop(t, None)
            elif g in ("CZ", "CP"):
                a, b = op.controls[0], op.targets[0]
                theta = _cp_angle(op) or 0.0
                zero = next((q for q in (a, b) if known.get(q) == 0), None)
                if zero is not None:
                    self.slots[i] = None
                    self.note("start", "from |0>", f"{lab}: q{zero} is still |0⟩ here, and {g} only acts when both "
                                                   "qubits are 1, so it does nothing.")
                    changed = True
                elif a in known and b in known:
                    self.slots[i] = None
                    self.note("start", "from |0>", f"{lab}: both qubits are |1⟩ here, so it only adds a global phase.")
                    changed = True
                elif a in known or b in known:
                    one, other = (a, b) if a in known else (b, a)
                    new = _phase_gate(other, theta, op.source)
                    self.slots[i] = new
                    self.note("start", "from |0>", f"{lab}: q{one} is |1⟩ here, so it acts on q{other} alone"
                                                   + (f", as {op_label(new)}." if new else "."))
                    changed = True
            elif g == "CCX":
                c1, c2, t = op.controls[0], op.controls[1], op.targets[0]
                zero = next((c for c in (c1, c2) if known.get(c) == 0), None)
                if zero is not None:
                    self.slots[i] = None
                    self.note("start", "from |0>", f"{lab}: the control q{zero} is still |0⟩ here, so it never fires.")
                    changed = True
                elif c1 in known and c2 in known:
                    self.slots[i] = Operation(gate="X", targets=[t], source=op.source)
                    self.note("start", "from |0>", f"{lab}: both controls are |1⟩ here, so it is just an X on q{t}.")
                    changed = True
                    if t in known:
                        known[t] ^= 1
                elif c1 in known or c2 in known:
                    one, other = (c1, c2) if c1 in known else (c2, c1)
                    self.slots[i] = Operation(gate="CX", controls=[other], targets=[t], source=op.source)
                    self.note("start", "from |0>", f"{lab}: q{one} is |1⟩ here, so it is a CNOT q{other}→q{t}.")
                    changed = True
                    known.pop(t, None)
                else:
                    known.pop(t, None)
            elif g == "SWAP":
                a, b = op.targets
                if a in known and b in known and known[a] == known[b]:
                    self.slots[i] = None
                    self.note("start", "from |0>", f"{lab}: both qubits are {ket(a)} here, so swapping changes nothing.")
                    changed = True
                elif a in known or b in known:
                    va, vb = known.pop(a, None), known.pop(b, None)
                    if va is not None:
                        known[b] = va
                    if vb is not None:
                        known[a] = vb
            if changed:
                return True  # one rewrite at a time, so every reason is about the circuit as it then stands
        return False

    # rules that only need the measured outcome odds to stay the same
    def end(self) -> bool:
        measured = {q for q, _ in self.result().measured_pairs()}
        live = set(measured)
        for i in range(len(self.slots) - 1, -1, -1):  # backward light cone of the measured qubits
            op = self.slots[i]
            if op is None or op.gate in ("MEASURE", "BARRIER"):
                continue
            qs = set(self.qubits(op))
            if qs & live:
                live |= qs
                continue
            self.slots[i] = None
            unread = ", ".join(f"q{q}" for q in sorted(qs))
            one = len(qs) == 1
            self.note("unmeasured", "measured odds",
                      f"{op_label(op)}: {unread} {'is' if one else 'are'} never measured afterwards and "
                      f"{'passes' if one else 'pass'} nothing on to a qubit that is.")
            return True
        tail = {q: True for q in range(self.n)}  # nothing but diagonal gates and measurement after this point
        for i in range(len(self.slots) - 1, -1, -1):
            op = self.slots[i]
            if op is None or op.gate in ("MEASURE", "BARRIER"):
                continue
            qs = self.qubits(op)
            if all(tail[q] for q in qs):
                if op.gate in DIAGONAL:
                    self.slots[i] = None
                    self.note("before-measure", "measured odds",
                              f"{op_label(op)} right before measurement only changes phases, which a measurement "
                              "cannot see.")
                    return True
                if op.gate == "SWAP":
                    a, b = op.targets
                    self.slots[i] = None
                    self.relabel(a, b)
                    self.note("before-measure", "measured odds",
                              f"{op_label(op)} right before measurement: measure q{a} and q{b} into each other's "
                              "classical bits instead (saves 3 CNOTs).")
                    return True
            for q in qs:
                tail[q] = False
        return False

    def relabel(self, a: int, b: int) -> None:
        swap = {a: b, b: a}
        for i, op in enumerate(self.slots):
            if op is not None and op.gate == "MEASURE":
                self.slots[i] = op.model_copy(update={"targets": [swap.get(q, q) for q in op.targets]})
        self.measurements = [Measurement(qubit=swap.get(m.qubit, m.qubit), clbit=m.clbit) for m in self.measurements]


def rewrite(spec: CircuitSpec) -> tuple[CircuitSpec, list[Rewrite]]:
    """Apply the rules until none applies: every-input identities first, then |0...0>, then measurement."""
    eng = _Engine(spec)
    for _ in range(MAX_PASSES):
        if not (eng.local() or eng.start() or eng.end()):
            break
    return eng.result(), eng.log


# ---------------------------------------------------------------- Qiskit and model proposals

_FROM_QISKIT = {g.lower(): g for g in UNITARY_GATES}


def qiskit_proposal(spec: CircuitSpec) -> CircuitSpec | str:
    """The Qiskit transpiler's best effort (level 3) in the spec's gate set, or why it could not be used."""
    from qiskit import transpile

    qc = build_reference_circuit(spec)
    out = transpile(qc, basis_gates=[g.lower() for g in UNITARY_GATES], optimization_level=3, seed_transpiler=1234)
    if out.num_qubits != spec.num_qubits:
        return "the transpiler changed the number of qubits"
    # level 3 may drop SWAPs by relabelling qubits; read each qubit from where it ends up
    perm = out.layout.final_index_layout() if out.layout is not None else list(range(spec.num_qubits))
    ops: list[dict[str, Any]] = []
    for inst in out.data:
        name = inst.operation.name
        qs = [out.find_bit(q).index for q in inst.qubits]
        gate = _FROM_QISKIT.get(name)
        if gate is None:
            return f"it produced a '{name}' gate, which specs do not have"
        params = [float(p) for p in inst.operation.params]
        if gate in ("CX", "CZ", "CP"):
            ops.append({"gate": gate, "controls": [qs[0]], "targets": [qs[1]], "params": params})
        elif gate == "CCX":
            ops.append({"gate": gate, "controls": qs[:2], "targets": [qs[2]]})
        else:
            ops.append({"gate": gate, "targets": qs, "params": params})
    return _with_measurements(spec, ops, perm)


def _with_measurements(spec: CircuitSpec, ops: list[dict[str, Any]],
                       perm: list[int] | None = None) -> CircuitSpec | str:
    """A candidate spec: new gates, the original's measurements (qubit q read from ``perm[q]``), validated."""
    where = perm or list(range(spec.num_qubits))
    raw = spec.model_dump(mode="json", exclude_none=True, by_alias=True)
    meas = [op.model_dump(mode="json", exclude_none=True) for op in spec.operations if op.gate == "MEASURE"]
    for m in meas:
        m["targets"] = [where[q] for q in m["targets"]]
    raw["operations"] = [*ops, *meas]
    raw["measurements"] = [{**m, "qubit": where[m["qubit"]]} for m in raw.get("measurements", [])]
    try:
        out = parse_spec(raw)
    except SpecError as err:
        return "it is not a valid circuit: " + "; ".join(str(i) for i in err.issues[:3])
    assert isinstance(out, CircuitSpec)
    return out


def _compact(spec: CircuitSpec) -> list[dict[str, Any]]:
    return [{"gate": op.gate, "targets": op.targets, "controls": op.controls,
             "params": [round(p, 6) for p in op.params]} for op in _gates(spec.operations)]


def _facts(spec: CircuitSpec, current: Cost, best: Cost) -> dict[str, Any]:
    return {
        "num_qubits": spec.num_qubits,
        "measured_qubits": sorted({q for q, _ in spec.measured_pairs()}),
        "operations": _compact(spec),
        "cost": {"two_qubit_gates": current.two_qubit, "gates": current.gates, "depth": current.depth},
        "best_found_so_far": {"two_qubit_gates": best.two_qubit, "gates": best.gates},
        "cost_rules": "CX and CZ cost 1 two-qubit gate, CP 2, SWAP 3, CCX 6.",
    }


# ---------------------------------------------------------------- all together

_LEVEL_TEXT = {"unitary": "the same gate for every input", "state": "the same final state",
               "outcomes": "the same measured odds"}


def _judge(cand: Candidate, original: CircuitSpec, spec: CircuitSpec | str, base: Cost) -> Candidate:
    if isinstance(spec, CircuitSpec):
        try:
            spec = parse_spec(spec.model_dump(mode="json", exclude_none=True, by_alias=True))
        except SpecError as err:
            spec = "it is not a valid circuit: " + "; ".join(str(i) for i in err.issues[:3])
    if isinstance(spec, str):
        cand.note = f"Not usable: {spec}."
        return cand
    assert isinstance(spec, CircuitSpec)
    cand.spec = spec.model_dump(mode="json", exclude_none=True, by_alias=True)
    cand.cost = cost(spec)
    cand.proof = prove(original, spec)
    cand.accepted = cand.proof.level != "none"
    cand.better = cand.accepted and _rank(cand.cost) < _rank(base)
    if not cand.accepted:
        cand.note = "Rejected: " + cand.proof.detail
    elif not cand.better:
        cand.note = "Proven equal, but no cheaper than the original."
    return cand


def optimize(spec: CircuitSpec, propose: Callable[[dict[str, Any]], Proposal] | None = None,
             ai_note: str = "") -> OptimizeResult:
    """Every optimizer's proposal, each proven or rejected by exact simulation, and the best one."""
    base = cost(spec)
    cands: list[Candidate] = []

    rewritten, log = rewrite(spec)
    rules = _judge(Candidate(source="rules", label="Rewrite rules", rewrites=log), spec, rewritten, base)
    if not log:
        rules.note = "No rule applies: nothing cancels, merges or goes unseen."
    cands.append(rules)

    try:
        qk: CircuitSpec | str = qiskit_proposal(spec)
    except Exception as err:  # noqa: BLE001 - reported in the row, never hidden
        qk = f"the transpiler failed ({type(err).__name__}: {err})"
    cands.append(_judge(Candidate(source="qiskit", label="Qiskit transpiler, level 3"), spec, qk, base))

    if log:  # without a rule to apply this would repeat the Qiskit row
        try:
            mid: CircuitSpec | str = qiskit_proposal(rewritten)
        except Exception as err:  # noqa: BLE001
            mid = f"the transpiler failed ({type(err).__name__}: {err})"
        steps = list(log)
        if isinstance(mid, CircuitSpec):
            mid, again = rewrite(mid)
            steps += [Rewrite(rule="qiskit", level="any input",
                              text="Qiskit transpiler, level 3: re-synthesised the gates left by the rules.")] + again
        cands.append(_judge(Candidate(source="combined", label="Rules + Qiskit", rewrites=steps), spec, mid, base))

    if propose is not None:
        best_so_far = min((c.cost for c in cands if c.better and c.cost), key=_rank, default=base)
        facts = _facts(spec, base, best_so_far)
        tries: list[Candidate] = []
        failed = ""
        for attempt in (1, 2):  # one revision after seeing exactly why the first proposal fell short
            try:
                prop = propose(facts)
            except Exception as err:  # noqa: BLE001 - reported in the row
                failed = f"The model call failed: {type(err).__name__}: {str(err)[:200]}"
                break
            ops = [op for op in prop.operations if str(op.get("gate", "")).upper() not in ("MEASURE", "BARRIER")]
            cand = _judge(Candidate(source="muse", label="Muse Spark 1.3", call=prop.call, attempts=attempt),
                          spec, _with_measurements(spec, ops), base)
            idea = prop.idea.strip()[:300]
            if cand.accepted and idea:
                cand.note = idea if cand.better else f"{idea} {cand.note}"
            tries.append(cand)
            if cand.better and cand.cost and _rank(cand.cost) <= _rank(best_so_far):
                break
            problem = cand.note if not cand.accepted else "It is correct but no cheaper than the best circuit so far."
            facts = {**facts, "previous_attempt": {"operations": ops, "problem": problem}}
        good = [c for c in tries if c.better and c.cost]
        if good:
            muse = min(good, key=lambda c: _rank(c.cost))  # type: ignore[arg-type, return-value]
        elif tries:
            muse = tries[-1]
        else:
            muse = Candidate(source="muse", label="Muse Spark 1.3", note=failed)
        muse.attempts = max(len(tries), 1)
        if failed and tries:
            muse.note = (muse.note + " " if muse.note else "") + f"(Second try failed: {failed[24:]})"
        cands.append(muse)

    better = [i for i, c in enumerate(cands) if c.better and c.cost]
    best = min(better, key=lambda i: (_rank(cands[i].cost), i)) if better else None  # type: ignore[arg-type]
    if best is None:
        summary = "No optimizer found a cheaper circuit with the same results: this one is already tight."
    else:
        b = cands[best]
        assert b.cost and b.proof
        summary = (f"{b.label} cut it from {base.gates} gates ({base.two_qubit} two-qubit) to {b.cost.gates} "
                   f"({b.cost.two_qubit}), proven to give {_LEVEL_TEXT[b.proof.level]}.")
        if base.fidelity is not None and b.cost.fidelity is not None:
            summary += (f" Fewer gates means less noise: the match to the ideal on realistic hardware goes from "
                        f"{base.fidelity:.3f} to {b.cost.fidelity:.3f}.")
        kept = [op.gate for op in parse_spec(b.spec).operations if op.gate not in ("MEASURE", "BARRIER")]  # type: ignore[union-attr, arg-type]
        before = [op.gate for op in _gates(spec.operations)]
        if b.proof.level != "unitary" and all(g in CLASSICAL for g in kept) and any(g not in CLASSICAL for g in before):
            summary += (" The shorter circuit only flips bits: this circuit's answer is fixed in advance, so it "
                        "shrinks to writing that answer down. That shortcut exists only because every input is "
                        "known; with an unknown input, the real use of such a circuit, it would not.")
    return OptimizeResult(original=base, candidates=cands, best=best, summary=summary, ai_note=ai_note)
