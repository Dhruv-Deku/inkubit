"""Write eight more algorithms into the gallery, each checked against its known answer before it is saved.

    .venv/Scripts/python scripts/make_algorithms.py

hidden_shift        the hidden-shift algorithm for a bent function: finds the shift s in one query (Roetteler 2010)
grover_two_marked   Grover search with two of eight items marked: one query finds one of them with certainty
quantum_counting    phase estimation of the Grover operator counts the marked items (Brassard, Høyer, Tapp 1998)
draper_adder        addition in Fourier space (Draper 2000): 5 + 6 = 11 with no carries computed
hhl_2x2             the HHL linear-system algorithm on a 2x2 system: the solution's ratio, read from the ancilla = 1 branch
shor_code           Shor's nine-qubit code corrects a Y error (a bit flip and a phase flip at once)
chsh_game           the CHSH game: quantum players win cos²(π/8) ≈ 85.4% of the time, classical ones at most 75%
mermin_game         the GHZ (Mermin) game: three quantum players always win; classical ones at most 75%

Every spec uses only Q-Canvas gates; circuits built with Qiskit's library are compiled to them first. The check is
the exact ideal distribution of the saved spec, rebuilt by Q-Canvas's own spec reader, against the answer derived
on paper (in the docstring of each builder), so a spec that drifts from its answer is never written.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from qcanvas.spec import parse_spec  # noqa: E402
from qcanvas.verify.expected import ideal_distribution  # noqa: E402

SPEC_GATES = ["h", "x", "y", "z", "s", "sdg", "t", "tdg", "sx", "rx", "ry", "rz", "cx", "cz", "cp", "swap", "ccx"]


def op(gate: str, targets, controls=None, params=None) -> dict:
    o = {"gate": gate, "targets": list(targets)}
    if controls:
        o["controls"] = list(controls)
    if params is not None:
        o["params"] = [float(p) for p in params]
    return o


def from_qiskit(qc) -> list[dict]:
    """Compile a Qiskit circuit to Q-Canvas gates and turn it into spec operations."""
    from qiskit import transpile

    # level 1: levels 2 and 3 may remove SWAPs and record a qubit permutation instead, which a spec cannot carry
    t = transpile(qc, basis_gates=SPEC_GATES, optimization_level=1, seed_transpiler=7)
    final = t.layout.final_layout if t.layout else None
    assert final is None or all(final[q] == i for i, q in enumerate(t.qubits)), "compiled with a hidden permutation"
    out = []
    for inst in t.data:
        name, qs = inst.operation.name, [t.find_bit(q).index for q in inst.qubits]
        ps = [float(p) for p in inst.operation.params]
        if name in ("barrier", "measure"):
            continue
        if name in ("cx", "cz", "cp"):
            out.append(op(name.upper(), [qs[1]], [qs[0]], ps or None))
        elif name == "ccx":
            out.append(op("CCX", [qs[2]], qs[:2]))
        elif name == "swap":
            out.append(op("SWAP", qs))
        else:
            out.append(op(name.upper(), [qs[0]], params=ps or None))
    return out


def spec(n: int, ops: list[dict], measured: list[int], title: str, notes: str) -> dict:
    return {"kind": "circuit", "version": "1.0", "num_qubits": n, "num_clbits": len(measured), "operations": ops,
            "measurements": [{"qubit": q, "clbit": c} for c, q in enumerate(measured)],
            "metadata": {"title": title, "notes": notes, "origin": "manual"}}


# ---------------------------------------------------------------- the algorithms

def hidden_shift() -> tuple[dict, dict]:
    """f(x) = x0x1 ⊕ x2x3 is bent and self-dual. g(x) = f(x ⊕ s). H, phase oracle of g, H, phase oracle of f̃ = f,
    H gives |s⟩ with certainty. Here s = 1011 (q3 q2 q1 q0)."""
    s = [1, 1, 0, 1]  # s_q for q = 0..3: the string reads q3 q2 q1 q0 = 1011
    hs = [op("H", range(4))]
    xs = [op("X", [q]) for q in range(4) if s[q]]
    bent = [op("CZ", [1], [0]), op("CZ", [3], [2])]
    ops = hs + xs + bent + xs + hs + bent + hs
    return (spec(4, ops, [0, 1, 2, 3], "Hidden shift (bent function, s = 1011)",
                 "f(x) = x0·x1 ⊕ x2·x3 and g(x) = f(x ⊕ s) are known only as phase oracles. Classically finding the shift s "
                 "takes many queries; here one query to each oracle, between Hadamards, gives s = 1011 every time."),
            {"1011": 1.0})


def grover_two_marked() -> tuple[dict, dict]:
    """N = 8, M = 2 marked (011 and 110): sin(θ/2) = √(M/N) = 1/2, so θ/2 = 30°, and one Grover step rotates the
    state to 3θ/2 = 90°: the marked subspace exactly. Each marked item comes out with probability 1/2."""
    def ccz():
        return [op("H", [2]), op("CCX", [2], [0, 1]), op("H", [2])]
    def phase_on(bits):  # flip the phase of one basis state q2 q1 q0 = bits
        flips = [op("X", [q]) for q in range(3) if bits[2 - q] == "0"]
        return flips + ccz() + flips
    oracle = phase_on("011") + phase_on("110")
    diffuse = [op("H", range(3)), op("X", range(3))] + ccz() + [op("X", range(3)), op("H", range(3))]
    ops = [op("H", range(3))] + oracle + diffuse
    return (spec(3, ops, [0, 1, 2], "Grover search with two marked items",
                 "Two of eight items are marked (011 and 110). With two marked, a single Grover query rotates the state "
                 "exactly onto them: either one comes out, never anything else, where a classical search needs 3.5 looks "
                 "on average."),
            {"011": 0.5, "110": 0.5})


def quantum_counting() -> tuple[dict, dict]:
    """Phase estimation (3 counting qubits) of the Grover operator for 2 marked items among 4 (00 and 11). The
    uniform start state lives in the span of eigenvectors with phases ±θ/2π, sin(θ/2) = √(2/4), so θ/2π = 1/4 and
    3/4: k = 2 and 6, each with probability 1/2, and M = 4 sin²(πk/8) = 2 for both."""
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import GroverOperator, PhaseEstimation

    oracle = QuantumCircuit(2)
    oracle.z(0)
    oracle.z(1)  # (-1)^(q0 ⊕ q1) up to a sign: marks 00 and 11 (the global sign only moves phases by 1/2)
    grover = GroverOperator(oracle)
    qc = QuantumCircuit(5)
    qc.h([3, 4])
    qc.append(PhaseEstimation(3, grover), [0, 1, 2, 3, 4])
    # Qiskit's PhaseEstimation leaves the most significant bit on its first evaluation qubit: read q2 q1 q0 as k's
    # bits from low to high, so the string is k in binary
    return (spec(5, from_qiskit(qc), [2, 1, 0], "Quantum counting (2 marked of 4)",
                 "Phase estimation of the Grover operator counts the marked items without finding them. Three counting "
                 "qubits read k = 2 or 6, and M = 4·sin²(πk/8) = 2 either way: two of the four items are marked."),
            {"010": 0.5, "110": 0.5})


def draper_adder() -> tuple[dict, dict]:
    """a = 5 (q0..q2) and b = 6 (q3..q5, with q6 as the carry) in binary, b's register taken to Fourier space and
    rotated by a, then back: b becomes a + b = 11 = 1011, a stays 101. The string reads q6..q0: 1011 101."""
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import DraperQFTAdder

    qc = QuantumCircuit(7)
    for q, bit in zip(range(3), [1, 0, 1]):  # a = 5: q0 = 1, q1 = 0, q2 = 1
        if bit:
            qc.x(q)
    for q, bit in zip(range(3, 6), [0, 1, 1]):  # b = 6: q3 = 0, q4 = 1, q5 = 1
        if bit:
            qc.x(q)
    qc.append(DraperQFTAdder(3, kind="half"), range(7))
    return (spec(7, from_qiskit(qc), list(range(7)), "Draper adder: 5 + 6 in Fourier space",
                 "Adds a = 5 (q0-q2) to b = 6 (q3-q5, carry q6) with controlled phases in the Fourier basis, no carry "
                 "logic at all. The result reads q6..q0 = 1011 101: b holds 11, a is untouched."),
            {"1011101": 1.0})


def hhl_2x2() -> tuple[dict, dict]:
    """A = [[1, −1/3], [−1/3, 1]] (eigenvalues 2/3 and 4/3), b = |0⟩. With t = 3π/4 the eigenphases are exactly 1/4
    and 1/2, so two clock qubits hold them without error. The ancilla is rotated by C/λ (C = 2/3): in the ancilla = 1
    branch the b qubit holds A⁻¹b ∝ (1, 1/3), amplitudes (3/4, 1/4); P(a=1, b=0) = 9/16, P(a=1, b=1) = 1/16, and the
    a = 0 branch is (√3/4)(1, −1): 3/16 each. Qubits: b = q0, clock q1 q2, ancilla q3; clbit 0 = b, 1 = ancilla."""
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import PhaseEstimation, RYGate, UnitaryGate
    from scipy.linalg import expm

    a = np.array([[1, -1 / 3], [-1 / 3, 1]])
    t = 3 * np.pi / 4
    pe = PhaseEstimation(2, UnitaryGate(expm(1j * a * t)))
    qc = QuantumCircuit(4)
    qc.append(pe, [1, 2, 0])  # evaluation qubits first, then the target
    c = 2 / 3
    for v in (1, 2):  # control value v over (q1, q2); q1 holds the phase's most significant bit (PhaseEstimation)
        phase = (v & 1) / 2 + ((v >> 1) & 1) / 4
        lam = 2 * np.pi * phase / t  # eigenvalue whose phase λt/2π the clock holds
        qc.append(RYGate(2 * np.arcsin(c / lam)).control(2, ctrl_state=v), [1, 2, 3])
    qc.append(pe.inverse(), [1, 2, 0])
    return (spec(4, from_qiskit(qc), [0, 3], "HHL: solve a 2x2 linear system",
                 "Solves A x = b for A = [[1, -1/3], [-1/3, 1]], b = (1, 0). When the ancilla reads 1, the other qubit holds "
                 "x = A⁻¹b ∝ (1, 1/3): outcomes 0 and 1 in the ratio 9 : 1, the classical answer squared."),
            {"10": 9 / 16, "11": 1 / 16, "00": 3 / 16, "01": 3 / 16})


def shor_code() -> tuple[dict, dict]:
    """Encode |−⟩ in Shor's code (phase-flip code over three bit-flip codes), apply Y on qubit 4 (a bit flip and a
    phase flip), decode with majority votes (CX, CX, Toffoli per block, then across blocks), H: q0 reads 1, always."""
    ops = [op("X", [0]), op("H", [0])]  # |−⟩
    ops += [op("CX", [3], [0]), op("CX", [6], [0]), op("H", [0, 3, 6])]
    for lead in (0, 3, 6):
        ops += [op("CX", [lead + 1], [lead]), op("CX", [lead + 2], [lead])]
    ops += [op("Y", [4])]  # the error
    for lead in (0, 3, 6):
        ops += [op("CX", [lead + 1], [lead]), op("CX", [lead + 2], [lead]), op("CCX", [lead], [lead + 1, lead + 2])]
    ops += [op("H", [0, 3, 6]), op("CX", [3], [0]), op("CX", [6], [0]), op("CCX", [0], [3, 6]), op("H", [0])]
    return (spec(9, ops, [0], "Shor's 9-qubit code corrects a Y error",
                 "One logical qubit |−⟩ spread over nine. A Y error on qubit 4 flips its bit and its phase at once; the "
                 "inner bit-flip codes and the outer phase-flip code each undo their half, and q0 reads 1 every time."),
            {"1": 1.0})


def chsh_game() -> tuple[dict, dict]:
    """Referee bits x (q2), y (q3) uniform; Alice (q0) and Bob (q1) share a Bell pair and measure along Bloch angles
    θA = xπ/2, θB = π/4 − yπ/2 (RY(−θ) then Z). They win when a ⊕ b = x ∧ y, with probability cos²(π/8) for every
    (x, y). Controlled RY is RY(θ/2), CX, RY(−θ/2), CX. Clbits: a, b, x, y."""
    def cry(theta, c, t):
        return [op("RY", [t], params=[theta / 2]), op("CX", [t], [c]), op("RY", [t], params=[-theta / 2]), op("CX", [t], [c])]
    ops = [op("H", [0, 2, 3]), op("CX", [1], [0])]
    ops += cry(-np.pi / 2, 2, 0)  # Alice: RY(−xπ/2)
    ops += [op("RY", [1], params=[-np.pi / 4])] + cry(np.pi / 2, 3, 1)  # Bob: RY(−π/4 + yπ/2)
    p = math.cos(math.pi / 8) ** 2
    ans = {}
    for a in (0, 1):
        for b in (0, 1):
            for x in (0, 1):
                for y in (0, 1):
                    win = (a ^ b) == (x & y)
                    ans[f"{y}{x}{b}{a}"] = 0.25 * (p if win else 1 - p) / 2
    return (spec(4, ops, [0, 1, 2, 3], "The CHSH game",
                 "A referee sends random bits x and y; Alice and Bob, who share a Bell pair but cannot talk, win when "
                 "a xor b = x and y. Any classical strategy wins at most 75% of the time; this one wins cos²(π/8) = 85.4%."),
            ans)


def mermin_game() -> tuple[dict, dict]:
    """Inputs x, y, z (q3, q4, q5) uniform over the four strings with x ⊕ y ⊕ z = 0; players q0..q2 share
    (|000⟩ + |111⟩)/√2 and measure X (input 0) or Y (input 1: S† then H). XXX = +1 and XYY = YXY = YYX = −1, so the
    output parity always equals x ∨ y ∨ z: every outcome is a win. Clbits: a, b, c, x, y, z."""
    ops = [op("H", [0]), op("CX", [1], [0]), op("CX", [2], [0]), op("H", [3, 4]), op("CX", [5], [3]), op("CX", [5], [4])]
    for player, inp in ((0, 3), (1, 4), (2, 5)):
        ops += [op("CP", [player], [inp], [-np.pi / 2])]
    ops += [op("H", [0, 1, 2])]
    ans = {}
    for x, y in ((0, 0), (0, 1), (1, 0), (1, 1)):
        z = x ^ y
        want = x | y | z
        for a in (0, 1):
            for b in (0, 1):
                c = want ^ a ^ b
                ans[f"{z}{y}{x}{c}{b}{a}"] = 0.25 / 4
    return (spec(6, ops, [0, 1, 2, 3, 4, 5], "The GHZ game (Mermin)",
                 "Three players get bits whose xor is 0 and must answer bits whose xor equals x or y or z. No classical "
                 "plan wins more than 3 times in 4; three players sharing a GHZ state win every single time."),
            ans)


BUILDERS = {"hidden_shift": hidden_shift, "grover_two_marked": grover_two_marked, "quantum_counting": quantum_counting,
            "draper_adder": draper_adder, "hhl_2x2": hhl_2x2, "shor_code": shor_code, "chsh_game": chsh_game,
            "mermin_game": mermin_game}


def main() -> None:
    for name, build in BUILDERS.items():
        raw, answer = build()
        got = ideal_distribution(parse_spec(raw))
        keys = set(got) | set(answer)
        err = max(abs(got.get(k, 0.0) - answer.get(k, 0.0)) for k in keys)
        if err > 1e-9:
            sys.exit(f"{name}: the circuit does not give its answer (max error {err:.2e}): {got}")
        (ROOT / "examples" / "specs" / f"{name}.json").write_text(json.dumps(raw, indent=1, ensure_ascii=False) + "\n",
                                                                  encoding="utf-8")
        print(f"{name:18s} {raw['num_qubits']} qubits, {len(raw['operations']):3d} gates: matches its answer to {err:.1e}")


if __name__ == "__main__":
    main()
