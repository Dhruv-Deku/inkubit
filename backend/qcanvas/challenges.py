"""Quantum puzzles: build a target state or gate, checked exactly.

Every challenge carries a reference solution that defines its target: a state
(equal up to global phase) or, for gate puzzles, a unitary (equal up to global
phase). The reference is never sent to the browser. A check simulates the
player's spec exactly, so "solved" means a fidelity of at least 0.999, never a
sampled guess. Stars work like golf: solved, near par, at or under par.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel
from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator, Statevector, state_fidelity

from qcanvas.insights.circuit import Amplitude, noisy_state
from qcanvas.sim.noise import get_preset
from qcanvas.spec import SpecError, parse_spec
from qcanvas.spec.models import CircuitSpec
from qcanvas.verify.expected import append_operation

SOLVED_AT = 0.999
NOT_COUNTED = ("BARRIER", "MEASURE")


def _op(gate: str, *targets: int, controls: tuple[int, ...] = (), angle: float | None = None) -> dict[str, Any]:
    return {"gate": gate, "targets": list(targets), "controls": list(controls),
            "params": [] if angle is None else [angle]}


@dataclass(frozen=True)
class Challenge:
    id: str
    level: int  # 1 warm-up, 2 entanglement, 3 gate golf
    title: str
    goal: str
    kind: Literal["state", "gate"]
    num_qubits: int
    solution: tuple[dict[str, Any], ...]  # the reference; defines the target, never sent out
    par: int
    hints: tuple[str, ...]
    lesson: str
    allowed: tuple[str, ...] | None = None
    target_text: str = ""  # the target written out, e.g. "(|00⟩ + |11⟩)/√2"
    extra: dict[str, Any] = field(default_factory=dict)


H, X, Z, S, CX, CZ, RY = "H", "X", "Z", "S", "CX", "CZ", "RY"
W_ANGLE = 2 * math.acos(math.sqrt(1 / 3))  # RY angle that leaves |1⟩ with probability 2/3

CHALLENGES: tuple[Challenge, ...] = (
    Challenge(
        "coin", 1, "Fair coin", "Put q0 into an equal superposition of 0 and 1, with no phase between them.",
        "state", 1, (_op(H, 0),), 1,
        ("One gate is enough.", "The Hadamard gate turns |0⟩ into an equal mix of |0⟩ and |1⟩."),
        "H makes |+⟩ = (|0⟩ + |1⟩)/√2. Measured, it behaves like a fair coin, but it is one definite state: "
        "another H turns it back into |0⟩ every time, which a random coin could never do.",
        target_text="(|0⟩ + |1⟩)/√2"),
    Challenge(
        "minus", 1, "Minus sign", "Make |−⟩: the same 50/50 odds as the coin, but with a minus sign on |1⟩.",
        "state", 1, (_op(X, 0), _op(H, 0)), 2,
        ("Measuring |−⟩ gives exactly the same counts as |+⟩; only the phase differs.",
         "Either start from |1⟩ instead of |0⟩, or flip the phase after making the coin.",
         "Try X then H, or H then Z."),
        "|+⟩ and |−⟩ give identical counts; only interference tells them apart (H|−⟩ = |1⟩). Phases are "
        "invisible to one measurement but decide what the next gate does.",
        target_text="(|0⟩ − |1⟩)/√2"),
    Challenge(
        "quarter", 1, "Quarter turn", "Point q0's Bloch arrow along +y: the state (|0⟩ + i|1⟩)/√2.",
        "state", 1, (_op(H, 0), _op(S, 0)), 2,
        ("First get the arrow onto the equator of the Bloch sphere.",
         "S turns the arrow a quarter of the way around the z axis."),
        "S multiplies |1⟩ by i: a phase is a rotation about the z axis, which a plain measurement never sees.",
        target_text="(|0⟩ + i|1⟩)/√2"),
    Challenge(
        "x-from-hz", 1, "NOT without X", "Build a NOT gate (it swaps |0⟩ and |1⟩) using only H and Z.",
        "gate", 1, (_op(H, 0), _op(Z, 0), _op(H, 0)), 3,
        ("H swaps the roles of the x and z axes of the Bloch sphere.",
         "Z flips the phase of |1⟩. Seen through a Hadamard on each side, a phase flip becomes a bit flip."),
        "HZH = X. A Hadamard is a change of basis, so a phase flip in one basis is a bit flip in the other; "
        "real chips build many gates this way from a small native set.",
        allowed=(H, Z), target_text="X: |0⟩ → |1⟩, |1⟩ → |0⟩"),
    Challenge(
        "bell", 2, "Bell pair", "Make two qubits that always agree when measured, though neither has a value of its own.",
        "state", 2, (_op(H, 0), _op(CX, 1, controls=(0,))), 2,
        ("Put one qubit in superposition first.",
         "A CNOT copies its control's value onto its target, separately in each branch of the superposition."),
        "That is entanglement: each qubit alone is a perfect coin (its Bloch arrow has shrunk to the centre), "
        "yet the two coins always land the same way.",
        target_text="(|00⟩ + |11⟩)/√2"),
    Challenge(
        "singlet", 2, "Always opposite", "Make the singlet: the two qubits always disagree, and the two branches have opposite signs.",
        "state", 2, (_op(H, 0), _op(CX, 1, controls=(0,)), _op(X, 1), _op(Z, 0)), 4,
        ("Start from a Bell pair and fix it up.",
         "An X on one qubit turns agreement into disagreement.",
         "A Z on the right qubit adds the minus sign."),
        "The singlet is the only two-qubit state that looks the same in every measurement basis: the qubits "
        "disagree whichever axis you measure them along.",
        target_text="(|01⟩ − |10⟩)/√2"),
    Challenge(
        "graph", 2, "Hidden phase", "Make all four outcomes equally likely, with a single minus sign on |11⟩.",
        "state", 2, (_op(H, 0), _op(H, 1), _op(CZ, 1, controls=(0,))), 3,
        ("Every outcome equally likely: both qubits need a Hadamard.",
         "The minus sign belongs only to |11⟩: which two-qubit gate does exactly that?"),
        "Measured, this looks like two independent coins, yet it is maximally entangled: the entanglement lives "
        "entirely in the phase. Graph states like this are the raw material of measurement-based quantum computing.",
        target_text="(|00⟩ + |01⟩ + |10⟩ − |11⟩)/2"),
    Challenge(
        "ghz", 2, "Three-way agreement", "Make three qubits that all agree: all 0 or all 1, half the time each.",
        "state", 3, (_op(H, 0), _op(CX, 1, controls=(0,)), _op(CX, 2, controls=(1,))), 3,
        ("It is a Bell pair with one more member.", "Each extra qubit needs one more CNOT."),
        "A GHZ state. Lose any one qubit and the other two are left with no entanglement at all: the "
        "Entanglement panel shows no entangled pairs, only three-way entanglement.",
        target_text="(|000⟩ + |111⟩)/√2"),
    Challenge(
        "swap-cx", 3, "SWAP from CNOTs", "Exchange the states of q0 and q1 using only CNOTs.",
        "gate", 2, (_op(CX, 1, controls=(0,)), _op(CX, 0, controls=(1,)), _op(CX, 1, controls=(0,))), 3,
        ("Think of the XOR swap trick: a ^= b; b ^= a; a ^= b.", "Alternate the direction of the CNOT."),
        "Three CNOTs make a SWAP. Chips that wire each qubit only to its neighbours pay exactly this price to "
        "move data, which is why the chip-layout panel counts the SWAPs the router adds.",
        allowed=(CX,), target_text="SWAP: |01⟩ ↔ |10⟩"),
    Challenge(
        "cz-from-cx", 3, "CZ from one CNOT", "Build a controlled-Z (a minus sign on |11⟩ only) from Hadamards and a single CNOT.",
        "gate", 2, (_op(H, 1), _op(CX, 1, controls=(0,)), _op(H, 1)), 3,
        ("Remember NOT without X: HZH = X.", "Turn that around: a Hadamard on each side of the target turns X into Z."),
        "CZ = (I⊗H) CX (I⊗H): the same change of basis as HZH = X, now with a control. Compilers use it to turn "
        "any CZ into the CNOTs a chip supports.",
        allowed=(H, CX), target_text="CZ: |11⟩ → −|11⟩, other inputs unchanged"),
    Challenge(
        "w", 3, "Fair three-way share", "Make the W state: exactly one of three qubits is 1, each with probability 1/3.",
        "state", 3, (_op(RY, 0, angle=W_ANGLE), _op(RY, 1, angle=math.pi / 4), _op(CX, 1, controls=(0,)),
                     _op(RY, 1, angle=-math.pi / 4), _op(CX, 2, controls=(1,)), _op(CX, 1, controls=(0,)),
                     _op(X, 0)), 7,
        ("RY(θ) leaves |1⟩ with probability sin²(θ/2): it sets an uneven split.",
         "Give q0 a 2/3 chance of being 1, then split that branch evenly over q1.",
         "A controlled Hadamard is RY(π/4) on the target, then a CNOT, then RY(−π/4).",
         "Finish with CNOTs to spread the single 1, and an X to fix q0."),
        "Unlike GHZ, the W state is robust: lose one qubit and the other two are still entangled. Building it "
        "needs uneven rotations, which is why it takes seven gates here.",
        target_text="(|001⟩ + |010⟩ + |100⟩)/√3"),
)

BY_ID = {c.id: c for c in CHALLENGES}
LEVELS = {1: "Warm-up", 2: "Entanglement", 3: "Gate golf"}


class GateRow(BaseModel):
    """What a gate puzzle's target does to one basis input."""

    input: str
    output: str


class ChallengeInfo(BaseModel):
    id: str
    level: int
    level_name: str
    title: str
    goal: str
    kind: Literal["state", "gate"]
    num_qubits: int
    par: int
    allowed: list[str] | None
    hint_count: int
    target_text: str
    target: list[Amplitude] | None = None  # state puzzles
    target_bloch: list[list[float]] | None = None
    table: list[GateRow] | None = None  # gate puzzles
    starter: dict[str, Any]


class ChallengeCheck(BaseModel):
    solved: bool
    fidelity: float  # state overlap, or process fidelity for gate puzzles
    gates: int
    par: int
    stars: int
    message: str
    illegal: list[str] = []
    state: list[Amplitude] | None = None  # the player's state (state puzzles)
    bloch: list[list[float]] | None = None
    rows_right: int | None = None  # gate puzzles: basis inputs the circuit already maps correctly
    noisy_fidelity: float | None = None  # state puzzles, realistic noise
    lesson: str | None = None


def _circuit(ops: list[Any], n: int) -> QuantumCircuit:
    qc = QuantumCircuit(n)
    for op in ops:
        if op.gate not in NOT_COUNTED:
            append_operation(qc, op)
    return qc


def _reference(ch: Challenge) -> QuantumCircuit:
    spec = parse_spec({"kind": "circuit", "num_qubits": ch.num_qubits, "num_clbits": ch.num_qubits,
                       "operations": list(ch.solution),
                       "measurements": [{"qubit": q, "clbit": q} for q in range(ch.num_qubits)]})
    assert isinstance(spec, CircuitSpec)
    return _circuit(spec.operations, ch.num_qubits)


def _amplitudes(psi: np.ndarray, n: int) -> list[Amplitude]:
    probs = np.abs(psi) ** 2
    lead = int(np.argmax(probs))
    psi = psi * np.exp(-1j * np.angle(psi[lead]))
    return [Amplitude(basis=format(i, f"0{n}b"), probability=round(float(p), 6), phase=round(float(np.angle(psi[i])), 6))
            for i, p in enumerate(probs) if p > 1e-9]


def _bloch_vectors(psi: Statevector, n: int) -> list[list[float]]:
    from qiskit.quantum_info import partial_trace

    out = []
    for q in range(n):
        rho = partial_trace(psi, [k for k in range(n) if k != q]).data if n > 1 else np.outer(psi.data, psi.data.conj())
        out.append([round(float(2 * rho[1, 0].real), 6), round(float(2 * rho[1, 0].imag), 6),
                    round(float((rho[0, 0] - rho[1, 1]).real), 6)])
    return out


def _ket(v: np.ndarray, n: int) -> str:
    """A basis vector times a phase as text ('−|11⟩', 'i|01⟩'); a superposition as its terms."""
    terms = []
    for i in np.flatnonzero(np.abs(v) > 1e-9):
        a = v[i]
        sign = {(1, 0): "", (-1, 0): "−", (0, 1): "i", (0, -1): "−i"}.get((round(a.real), round(a.imag)), f"{a:.2f}")
        terms.append(f"{sign}|{format(int(i), f'0{n}b')}⟩")
    return " + ".join(terms).replace("+ −", "− ")


def info(ch: Challenge) -> ChallengeInfo:
    ref = _reference(ch)
    n = ch.num_qubits
    out = ChallengeInfo(
        id=ch.id, level=ch.level, level_name=LEVELS[ch.level], title=ch.title, goal=ch.goal, kind=ch.kind,
        num_qubits=n, par=ch.par, allowed=list(ch.allowed) if ch.allowed else None, hint_count=len(ch.hints),
        target_text=ch.target_text,
        starter={"kind": "circuit", "version": "1.0", "num_qubits": n, "num_clbits": n, "operations": [],
                 "measurements": [{"qubit": q, "clbit": q} for q in range(n)],
                 "metadata": {"title": f"Challenge: {ch.title}", "origin": "manual"}})
    if ch.kind == "state":
        psi = Statevector(ref)
        out.target = _amplitudes(psi.data, n)
        out.target_bloch = _bloch_vectors(psi, n)
    else:
        u = Operator(ref).data
        out.table = [GateRow(input=f"|{format(i, f'0{n}b')}⟩", output=_ket(u[:, i] * np.exp(-1j * np.angle(u[0, 0])), n))
                     for i in range(2 ** n)]
    return out


def _stars(solved: bool, gates: int, par: int) -> int:
    if not solved:
        return 0
    return 3 if gates <= par else 2 if gates <= par + 2 else 1


def check(ch: Challenge, raw_spec: dict[str, Any]) -> ChallengeCheck:
    """Score a player's circuit against the challenge's target."""
    n = ch.num_qubits
    try:
        spec = parse_spec(raw_spec)
    except SpecError as err:
        first = err.issues[0] if err.issues else "the spec is not valid"
        return ChallengeCheck(solved=False, fidelity=0.0, gates=0, par=ch.par, stars=0,
                              message=f"Fix the spec first: {first}")
    if not isinstance(spec, CircuitSpec):
        return ChallengeCheck(solved=False, fidelity=0.0, gates=0, par=ch.par, stars=0,
                              message="Challenges are circuits; this is a network.")
    if spec.num_qubits != n:
        return ChallengeCheck(solved=False, fidelity=0.0, gates=0, par=ch.par, stars=0,
                              message=f"This puzzle uses {n} qubit{'s' if n > 1 else ''}; your circuit has {spec.num_qubits}.")
    ops = [op for op in spec.operations if op.gate not in NOT_COUNTED]
    illegal = sorted({op.gate for op in ops if ch.allowed and op.gate not in ch.allowed})
    qc = _circuit(spec.operations, n)
    ref = _reference(ch)
    gates = len(ops)
    rows_right = None
    state = bloch = None
    noisy = None
    if ch.kind == "state":
        psi, target = Statevector(qc), Statevector(ref)
        fid = float(abs(np.vdot(target.data, psi.data)) ** 2)
        state, bloch = _amplitudes(psi.data, n), _bloch_vectors(psi, n)
        same_odds = np.allclose(np.abs(psi.data) ** 2, np.abs(target.data) ** 2, atol=1e-6)
    else:
        u, t = Operator(qc).data, Operator(ref).data
        d = 2 ** n
        fid = float(abs(np.trace(t.conj().T @ u)) ** 2 / d ** 2)
        rows_right = sum(abs(np.vdot(t[:, i], u[:, i])) ** 2 > SOLVED_AT for i in range(d))
        same_odds = np.allclose(np.abs(u) ** 2, np.abs(t) ** 2, atol=1e-6)
    solved = fid >= SOLVED_AT and not illegal
    if solved and ch.kind == "state" and n <= 6:
        rho = noisy_state(spec, get_preset("realistic"))
        noisy = round(float(state_fidelity(rho, Statevector(ref))), 4)
    stars = _stars(solved, gates, ch.par)
    if illegal:
        message = f"This puzzle allows only {', '.join(ch.allowed or ())}; remove {', '.join(illegal)}."
    elif solved:
        message = (f"Solved in {gates} gate{'s' if gates != 1 else ''}"
                   + (" — under par!" if gates < ch.par else " — par." if gates == ch.par
                      else f"; par is {ch.par}, can you trim {gates - ch.par}?"))
    elif gates == 0:
        message = "Add gates to the circuit: click a gate, then click a wire."
    elif same_odds:
        message = ("The probabilities are already right; a relative phase is off." if ch.kind == "state"
                   else "Every input lands on the right output; a phase is off.")
    elif ch.kind == "state":
        message = f"Overlap with the target: {fid:.0%}."
    else:
        message = f"{rows_right} of {2 ** n} basis inputs already map correctly (process fidelity {fid:.0%})."
    return ChallengeCheck(solved=solved, fidelity=round(fid, 6), gates=gates, par=ch.par, stars=stars, message=message,
                          illegal=illegal, state=state, bloch=bloch, rows_right=rows_right, noisy_fidelity=noisy,
                          lesson=ch.lesson if solved else None)


def hint_facts(ch: Challenge, raw_spec: dict[str, Any], number: int) -> dict[str, Any]:
    """What a hint may use: the goal, the player's circuit and score, and the authored hint (never the solution)."""
    result = check(ch, raw_spec)
    ops = raw_spec.get("operations", []) if isinstance(raw_spec, dict) else []
    return {
        "challenge": ch.title, "goal": ch.goal, "target": ch.target_text, "kind": ch.kind,
        "allowed_gates": list(ch.allowed) if ch.allowed else "any", "par": ch.par,
        "player_circuit": [{k: v for k, v in op.items() if k in ("gate", "targets", "controls", "params")}
                           for op in ops if isinstance(op, dict)],
        "check": result.message, "fidelity": result.fidelity,
        "player_state": [a.model_dump() for a in result.state] if result.state else None,
        "hint_number": number, "authored_hint": ch.hints[min(number, len(ch.hints) - 1)],
    }
