"""Error-correction lab: when does the three-qubit repetition code beat a bare qubit?

A logical qubit is spread over three (two CNOTs), every qubit then suffers an
error with probability p, and a decoder (two CNOTs and a Toffoli: syndrome
measurement and correction in deferred-measurement form) restores the
majority. With perfect gates the logical error for bit flips is 3p^2 - 2p^3,
below p for any p < 1/2. With realistic gates the code's own five gates add
errors, so it only pays off above a break-even error rate, which falls as the
gates improve: the idea behind every fault-tolerance threshold.

The same code against phase flips makes things worse (any odd number of flips
flips the logical phase), which is why real machines use codes that catch both
kinds, such as the surface code.

Exact density-matrix simulation with the same gate channels as everything else.
Readout error is left out: it is the same for the bare qubit and the code.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from pydantic import BaseModel
from qiskit import QuantumCircuit
from qiskit.quantum_info import DensityMatrix, Kraus, Operator, SuperOp

from inkubit.insights.circuit import gate_channels, scaled_preset
from inkubit.sim.noise import get_preset

GRID = 61
P_MIN, P_MAX = 1e-4, 0.5

_I = np.eye(2)
_X = np.array([[0, 1], [1, 0]])
_Z = np.array([[1, 0], [0, -1]])


class Curves(BaseModel):
    perfect: list[float]  # logical error with noiseless gates
    realistic: list[float]  # with the hardware's gate noise
    break_even: float | None  # smallest p above which the realistic code beats a bare qubit


class RepetitionLab(BaseModel):
    scale: float  # gate noise relative to the realistic preset
    p: list[float]
    bare: list[float]
    bit: Curves
    phase: Curves
    gate_error_2q: float  # the two-qubit depolarising probability used
    summary: str


def _steps(qc: QuantumCircuit) -> list[tuple[Operator, list[int]]]:
    return [(Operator(inst.operation), [qc.find_bit(q).index for q in inst.qubits]) for inst in qc.data]


def _encoder() -> QuantumCircuit:
    qc = QuantumCircuit(3)
    qc.cx(0, 1)
    qc.cx(0, 2)
    return qc


def _decoder() -> QuantumCircuit:
    qc = QuantumCircuit(3)
    qc.cx(0, 1)
    qc.cx(0, 2)
    qc.ccx(2, 1, 0)  # both copies disagree with q0: flip it back
    return qc


@lru_cache(maxsize=32)
def _noisy_block(which: str, scale: float) -> SuperOp:
    """The encoder or decoder as one channel, each gate followed by its noise at ``scale`` x realistic."""
    qc = _encoder() if which == "enc" else _decoder()
    channels = gate_channels(scaled_preset(get_preset("realistic"), scale)) if scale > 0 else {}
    total = SuperOp(np.eye(64))
    for op, qargs in _steps(qc):
        total = total.compose(SuperOp(op), qargs=qargs)
        if len(qargs) in channels:
            total = total.compose(channels[len(qargs)], qargs=qargs)
    return total


def _flips(p: float, pauli: np.ndarray, n: int) -> SuperOp:
    one = SuperOp(Kraus([math.sqrt(1 - p) * _I, math.sqrt(p) * pauli]))
    total = one
    for _ in range(n - 1):
        total = total.expand(one)
    return total


def _prepared(kind: str, sign: int) -> DensityMatrix:
    prep = QuantumCircuit(3)
    if sign < 0:
        prep.x(0)
    if kind == "phase":
        prep.h(0)  # |+> or |->: the code must keep the relative phase
    return DensityMatrix.from_instruction(prep)


def _observable(kind: str) -> np.ndarray:
    return np.kron(np.eye(4), _Z if kind == "bit" else _X)  # qubit 0 is the rightmost factor


def _logical_error(p: float, kind: str, scale: float) -> float:
    """Average error of the encoded qubit over the two basis inputs (reference version, via Qiskit)."""
    enc, dec = _noisy_block("enc", scale), _noisy_block("dec", scale)
    flips = _flips(p, _X if kind == "bit" else _Z, 3)
    err = 0.0
    for sign in (1, -1):
        rho = _prepared(kind, sign).evolve(enc).evolve(flips).evolve(dec)
        err += (1 - sign * float(np.trace(rho.data @ _observable(kind)).real)) / 2
    return err / 2


def _paulis(pauli: np.ndarray) -> list[np.ndarray]:
    return [np.kron(np.kron(*(pauli if j == k else _I for j in (2, 1))), pauli if k == 0 else _I) for k in range(3)]


def _logical_errors(ps: list[float], kind: str, scale: float) -> list[float]:
    """The same for many p at once: encode once, apply the flips in numpy, decode with one matrix product."""
    enc, dec = _noisy_block("enc", scale), _noisy_block("dec", scale).data
    flips = _paulis(_X if kind == "bit" else _Z)
    obs = _observable(kind)
    encoded = [(sign, _prepared(kind, sign).evolve(enc).data) for sign in (1, -1)]
    out = []
    for p in ps:
        err = 0.0
        for sign, rho in encoded:
            for f in flips:
                rho = (1 - p) * rho + p * (f @ rho @ f)
            vec = dec @ rho.reshape(-1, order="F")  # Qiskit superoperators act on column-stacked matrices
            err += (1 - sign * float(np.trace(vec.reshape(8, 8, order="F") @ obs).real)) / 2
        out.append(err / 2)
    return out


def _break_even(p: list[float], code: list[float]) -> float | None:
    """First p where the code drops below the bare qubit (linear interpolation in log p)."""
    diff = [c - x for c, x in zip(code, p)]
    for i in range(1, len(p)):
        if diff[i - 1] > 0 and diff[i] < -1e-9:
            t = diff[i - 1] / (diff[i - 1] - diff[i])
            return float(math.exp(math.log(p[i - 1]) + t * (math.log(p[i]) - math.log(p[i - 1]))))
    if diff and diff[0] <= 0 and any(d < -1e-12 for d in diff):
        return p[0]  # helps everywhere on the grid
    return None


@lru_cache(maxsize=32)
def repetition_lab(scale: float = 1.0) -> RepetitionLab:
    ps = [float(x) for x in np.geomspace(P_MIN, P_MAX, GRID)]
    curves = {}
    for kind in ("bit", "phase"):
        perfect = _logical_errors(ps, kind, 0.0)
        real = _logical_errors(ps, kind, scale)
        curves[kind] = Curves(perfect=[round(v, 8) for v in perfect], realistic=[round(v, 8) for v in real],
                              break_even=_break_even(ps, real))
    p2 = scaled_preset(get_preset("realistic"), scale).p2
    return RepetitionLab(scale=scale, p=ps, bare=ps, bit=curves["bit"], phase=curves["phase"],
                         gate_error_2q=p2, summary=_summary(scale, curves["bit"], curves["phase"]))


def _summary(scale: float, bit: Curves, phase: Curves) -> str:
    level = ("perfect" if scale == 0 else "today's realistic" if abs(scale - 1) < 1e-9
             else f"{1 / scale:.2g}x better" if scale < 1 else f"{scale:.2g}x worse")
    if bit.break_even is None:
        text = (f"With {level} gates the code never beats a bare qubit against bit flips: its five gates "
                "add more errors than it removes at every flip rate.")
    elif bit.break_even <= P_MIN * 1.0001:
        text = f"With {level} gates the code beats a bare qubit at every bit-flip rate shown."
    else:
        text = (f"With {level} gates the code only helps once bit flips are more likely than "
                f"{bit.break_even:.2%} per qubit; below that its own five gates add more errors than it "
                "removes. Better gates move this break-even point down: that is the threshold idea behind "
                "fault-tolerant quantum computing.")
    text += (" With perfect gates it always helps (logical error 3p² − 2p³). Against phase flips the same code "
             "makes things worse, since any odd number of flips changes the logical phase; real machines use "
             "codes that catch both kinds, such as the surface code.")
    return text
