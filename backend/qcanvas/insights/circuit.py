"""What happens inside a circuit, computed straight from the spec.

The state after every step (amplitudes and one Bloch vector per qubit), the
entanglement it creates and how much survives the noise, which noise source
costs the most (the error budget), how good the hardware must get for a 99%
match, readout-error correction of the measured counts, zero-noise
extrapolation, and OpenQASM exports.

Like the verifier, nothing here reads generated code: everything is exact
statevector or density-matrix simulation of the spec, so it is deterministic.
"""

from __future__ import annotations

import math
from dataclasses import replace
from functools import lru_cache

import numpy as np
from pydantic import BaseModel, Field
from qiskit import QuantumCircuit, qasm2, qasm3
from qiskit.quantum_info import DensityMatrix, Statevector, SuperOp, concurrence, partial_trace
from qiskit_aer.noise import thermal_relaxation_error

from qcanvas.codegen.template import format_angle
from qcanvas.sim.noise import TOFFOLI_CNOTS, NoisePreset, get_preset, toffoli_error
from qcanvas.spec.models import CircuitSpec, Operation
from qcanvas.verify.expected import (
    Distribution,
    _to_clbit_keys,
    append_operation,
    apply_readout_error,
    build_reference_circuit,
    ideal_distribution,
)
from qcanvas.verify.metrics import hellinger_fidelity

MAX_NOISY_QUBITS = 10  # density matrices grow as 4^n; above this the noisy analyses are skipped (with a note)
MAX_AMPLITUDES = 16
SWEEP_SCALES = (0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0)
TARGET_FIDELITY = 0.99
ENTANGLED_BELOW = 0.999  # Bloch vector length of a qubit that shares information with others
MAX_WEB_QUBITS = 8  # pairwise entanglement per step is listed up to this size
ZNE_SCALES = (1, 3, 5)  # noise levels for zero-noise extrapolation (gate folding)
ZNE_SHOTS = 4000
MAX_ZNE_QUBITS = 8
MAX_ZNE_GATES = 150


class Amplitude(BaseModel):
    basis: str  # Qiskit order: qubit 0 is the rightmost character
    probability: float
    phase: float  # radians in (-pi, pi], relative to the largest amplitude


class StepState(BaseModel):
    step: int  # 0 is the starting state
    op_index: int | None
    label: str
    amplitudes: list[Amplitude]
    hidden_probability: float = 0.0  # probability in basis states not listed
    bloch: list[list[float]]  # [x, y, z] per qubit
    entangled: list[bool]
    entropy: list[float] = Field(default_factory=list)  # bits of entanglement of each qubit with the rest
    links: list[list[float]] = Field(default_factory=list)  # [a, b, concurrence] for entangled pairs


class PairEntanglement(BaseModel):
    a: int
    b: int
    ideal: float  # concurrence, 0 (none) to 1 (maximal)
    noisy: float | None = None


class Entanglement(BaseModel):
    pairs: list[PairEntanglement]
    qubit_entropy: list[float]  # entanglement entropy (bits) of each qubit with the rest, ideal state
    summary: str


class BudgetItem(BaseModel):
    source: str
    label: str
    fidelity_loss: float


class ErrorBudget(BaseModel):
    total_loss: float
    items: list[BudgetItem]
    summary: str


class SweepPoint(BaseModel):
    scale: float
    fidelity: float
    success: float | None = None  # probability of the right answer, for circuits with one right answer


class NoiseSweep(BaseModel):
    baseline: str
    points: list[SweepPoint]
    target: float = TARGET_FIDELITY
    scale_for_target: float | None
    summary: str


class Mitigation(BaseModel):
    corrected: Distribution
    fidelity_raw: float
    fidelity_corrected: float
    summary: str


class LayoutCost(BaseModel):
    layout: str
    description: str
    depth: int
    two_qubit_gates: int
    swaps_added: int
    estimated_success: float  # rough: product of gate and readout fidelities, decoherence ignored


class ZeroNoise(BaseModel):
    scales: list[int]
    coefficients: list[float]  # Richardson weights: mitigated = sum c_i * p(scale_i)
    fidelity_at: list[float]  # match to the ideal at each noise level, readout corrected
    mitigated: Distribution
    fidelity_raw: float  # as the hardware reports it (gate noise and readout error)
    fidelity_readout: float  # after readout correction alone
    fidelity_mitigated: float  # after extrapolation, exact probabilities
    fidelity_shots: float  # the same with ZNE_SHOTS shots per noise level (seeded)
    fidelity_readout_shots: float  # readout correction alone from the same shots at 1x, for a fair comparison
    shots: int
    shot_overhead: float  # sum c_i^2: extra shots for the same error bars
    outcome: str  # the ideal's most likely outcome, for the extrapolation chart
    outcome_ideal: float
    outcome_at: list[float]  # its probability at each noise level (readout corrected, exact)
    outcome_zero: float  # the Richardson value at zero noise: the quadratic through outcome_at, at 0
    summary: str


class Exports(BaseModel):
    qasm2: str
    qasm3: str


class CircuitInsights(BaseModel):
    steps: list[StepState]
    entanglement: Entanglement | None = None
    budget: ErrorBudget | None = None
    sweep: NoiseSweep | None = None
    mitigation: Mitigation | None = None
    zne: ZeroNoise | None = None
    layouts: list[LayoutCost] = Field(default_factory=list)
    layout_summary: str = ""
    exports: Exports
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- step by step

def _angle(theta: float) -> str:
    return format_angle(theta).replace(" * ", "").replace(" / ", "/").replace("pi", "π")


def op_label(op: Operation) -> str:
    """Short human label: 'H on q0', 'CX q0→q1', 'CP(π/4) q0→q3'."""
    g = op.gate.replace("SDG", "S†").replace("TDG", "T†").replace("SX", "√X")
    qs = ", ".join(f"q{q}" for q in op.targets)
    if op.gate in ("RX", "RY", "RZ"):
        return f"{g}({_angle(op.params[0])}) on {qs}"
    if op.gate == "CP":
        return f"CP({_angle(op.params[0])}) q{op.controls[0]}→q{op.targets[0]}"
    if op.gate in ("CX", "CZ"):
        return f"{g} q{op.controls[0]}→q{op.targets[0]}"
    if op.gate == "CCX":
        return f"Toffoli q{op.controls[0]},q{op.controls[1]}→q{op.targets[0]}"
    if op.gate == "SWAP":
        return f"SWAP q{op.targets[0]}↔q{op.targets[1]}"
    return f"{g} on {qs}"


def _tensor(psi: np.ndarray, n: int) -> np.ndarray:
    # Qiskit is little-endian: qubit q is tensor axis n-1-q after a C-order reshape
    return psi.reshape([2] * n)


def _reduced(psi: np.ndarray, n: int, qubits: list[int]) -> np.ndarray:
    """Reduced density matrix of ``qubits`` (first listed = most significant) from a pure state."""
    axes = [n - 1 - q for q in qubits]
    t = np.moveaxis(_tensor(psi, n), axes, list(range(len(axes))))
    m = t.reshape(2 ** len(qubits), -1)
    return m @ m.conj().T


def _bloch(rho: np.ndarray) -> list[float]:
    return [round(float(2 * rho[1, 0].real), 6), round(float(2 * rho[1, 0].imag), 6),
            round(float((rho[0, 0] - rho[1, 1]).real), 6)]


def _entropy_bits(rho: np.ndarray) -> float:
    vals = np.linalg.eigvalsh(rho)
    return float(-sum(v * math.log2(v) for v in vals if v > 1e-12))


_YY = np.kron([[0, -1j], [1j, 0]], [[0, -1j], [1j, 0]])


def _concurrence(rho: np.ndarray) -> float:
    """Wootters concurrence of a two-qubit density matrix (equal to Qiskit's; a test checks it)."""
    r = rho @ _YY @ rho.conj() @ _YY
    lam = np.sqrt(np.clip(np.sort(np.linalg.eigvals(r).real)[::-1], 0.0, None))
    return float(max(0.0, lam[0] - lam[1] - lam[2] - lam[3]))


def _state(psi: np.ndarray, n: int, step: int, op_index: int | None, label: str) -> StepState:
    probs = np.abs(psi) ** 2
    order = np.argsort(-probs, kind="stable")
    psi = psi * np.exp(-1j * np.angle(psi[order[0]]))  # global phase is unobservable: largest amplitude real
    shown = [int(i) for i in order[:MAX_AMPLITUDES] if probs[i] > 1e-10]
    amps = [Amplitude(basis=format(i, f"0{n}b"), probability=round(float(probs[i]), 6),
                      phase=round(float(np.angle(psi[i])) if probs[i] > 1e-10 else 0.0, 6)) for i in shown]
    bloch, entangled, entropy = [], [], []
    for q in range(n):
        rho = _reduced(psi, n, [q])
        vec = _bloch(rho)
        bloch.append(vec)
        entangled.append(math.dist(vec, (0, 0, 0)) < ENTANGLED_BELOW)
        entropy.append(round(_entropy_bits(rho), 4))
    links: list[list[float]] = []
    if n <= MAX_WEB_QUBITS:
        tangled = [q for q in range(n) if entangled[q]]
        for i, a in enumerate(tangled):
            for b in tangled[i + 1:]:
                c = _concurrence(_reduced(psi, n, [a, b]))
                if c > 0.01:
                    links.append([a, b, round(c, 4)])
    hidden = max(0.0, 1.0 - sum(a.probability for a in amps))
    return StepState(step=step, op_index=op_index, label=label, amplitudes=amps,
                     hidden_probability=round(hidden, 6), bloch=bloch, entangled=entangled,
                     entropy=entropy, links=links)


def step_states(spec: CircuitSpec) -> list[StepState]:
    """The ideal state before the first gate and after every gate."""
    n = spec.num_qubits
    qc = QuantumCircuit(n)
    psi = Statevector.from_label("0" * n).data
    out = [_state(psi, n, 0, None, "start: every qubit is 0")]
    for i, op in enumerate(spec.operations):
        if op.gate in ("BARRIER", "MEASURE"):
            continue
        step = QuantumCircuit(n)
        append_operation(step, op)
        qc.compose(step, inplace=True)
        psi = Statevector(psi).evolve(step).data
        out.append(_state(psi, n, len(out), i, op_label(op)))
    return out


# ---------------------------------------------------------------- exact noisy state

def _depolarizing(lam: float, k: int) -> SuperOp:
    """(1 - lam) rho + lam Tr(rho) I/d on k qubits, the definition Aer uses."""
    d = 2 ** k
    vec_i = np.eye(d).reshape(-1)
    return SuperOp((1 - lam) * np.eye(d * d) + (lam / d) * np.outer(vec_i, vec_i))


@lru_cache(maxsize=64)
def gate_channels(preset: NoisePreset) -> dict[int, SuperOp]:
    """The channel applied after every 1-, 2- and 3-qubit gate, built in closed form.

    Equal to ``sim.noise.gate_errors(preset)`` (a test checks it), without building the
    64-term three-qubit Pauli error that makes the generic conversion slow.
    """
    if preset.p1 == 0 and preset.p2 == 0 and preset.t1_us is None:
        return {}
    out = {1: _depolarizing(preset.p1, 1), 2: _depolarizing(preset.p2, 2), 3: _depolarizing(toffoli_error(preset), 3)}
    if preset.t1_us is not None and preset.t2_us is not None:
        for k, duration in ((1, preset.gate_1q_us), (2, preset.gate_2q_us), (3, TOFFOLI_CNOTS * preset.gate_2q_us)):
            relax = SuperOp(thermal_relaxation_error(preset.t1_us, preset.t2_us, duration).to_quantumchannel())
            many = relax
            for _ in range(k - 1):
                many = many.expand(relax)
            out[k] = out[k].compose(many)
    return out


def noisy_state(spec: CircuitSpec, preset: NoisePreset) -> DensityMatrix:
    """Density matrix before measurement, evolving gate by gate with the preset's error channels.

    The same channels the verifier hands to Aer, applied after every gate, but without the
    simulator's fixed per-call cost; a test checks the two agree.
    """
    n = spec.num_qubits
    channels = gate_channels(preset)
    rho = DensityMatrix.from_label("0" * n)
    qc = QuantumCircuit(n)
    for op in spec.operations:
        append_operation(qc, op)
    for inst in qc.data:
        qargs = [qc.find_bit(q).index for q in inst.qubits]
        rho = rho.evolve(inst.operation, qargs=qargs)
        if len(qargs) in channels:
            rho = rho.evolve(channels[len(qargs)], qargs=qargs)
    return rho


def noisy_distribution(spec: CircuitSpec, preset: NoisePreset) -> Distribution:
    """Exact outcome probabilities under ``preset`` (gate noise, then readout error)."""
    pairs = spec.measured_pairs()
    rho = noisy_state(spec, preset)
    dist = _to_clbit_keys(rho.probabilities_dict(qargs=[q for q, _ in pairs]), spec, pairs)
    return apply_readout_error(dist, spec, preset.readout_p01, preset.readout_p10)


# ---------------------------------------------------------------- entanglement

def entanglement(spec: CircuitSpec, preset: NoisePreset, rho_noisy: DensityMatrix | None) -> Entanglement:
    n = spec.num_qubits
    psi = Statevector.from_instruction(build_reference_circuit(spec)).data
    entropy = [round(_entropy_bits(_reduced(psi, n, [q])), 4) for q in range(n)]
    pairs: list[PairEntanglement] = []
    for a in range(n):
        for b in range(a + 1, n):
            ideal = float(concurrence(DensityMatrix(_reduced(psi, n, [a, b]))))
            noisy = None
            if rho_noisy is not None:
                rest = [q for q in range(n) if q not in (a, b)]
                noisy = round(float(concurrence(partial_trace(rho_noisy, rest) if rest else rho_noisy)), 4)
            if ideal > 0.01 or (noisy or 0) > 0.01:
                pairs.append(PairEntanglement(a=a, b=b, ideal=round(ideal, 4), noisy=noisy))
    pairs.sort(key=lambda p: -p.ideal)
    return Entanglement(pairs=pairs, qubit_entropy=entropy, summary=_entanglement_summary(pairs, entropy, preset))


def _entanglement_summary(pairs: list[PairEntanglement], entropy: list[float], preset: NoisePreset) -> str:
    tangled = [q for q, s in enumerate(entropy) if s > 0.01]
    if not tangled:
        return "This circuit creates no entanglement: every qubit can be described on its own."
    if pairs:
        top = pairs[0]
        text = (f"q{top.a} and q{top.b} are {'maximally ' if top.ideal > 0.99 else ''}entangled "
                f"(concurrence {top.ideal:.2f}")
        if top.noisy is not None and not preset.is_ideal:
            kept = top.noisy / top.ideal if top.ideal else 0
            text += f"; with {preset.label.lower()} noise it drops to {top.noisy:.2f}, so {kept:.0%} survives"
        text += ")."
        if len(pairs) > 1:
            text += f" {len(pairs) - 1} more pair{'s are' if len(pairs) > 2 else ' is'} entangled too."
        return text
    names = ", ".join(f"q{q}" for q in tangled)
    return (f"{names} share one entangled state (each carries up to {max(entropy):.2f} bit of entanglement "
            f"entropy), yet no pair is entangled on its own: the entanglement belongs to the whole group, "
            f"the hallmark of GHZ-type states.")


# ---------------------------------------------------------------- noise analyses

def _fidelity(spec: CircuitSpec, ideal: Distribution, preset: NoisePreset) -> float:
    return hellinger_fidelity(ideal, noisy_distribution(spec, preset))


def error_budget(spec: CircuitSpec, preset: NoisePreset, ideal: Distribution) -> ErrorBudget:
    """Fidelity lost to each noise source acting alone, and to all of them together."""
    zero = dict(p1=0.0, p2=0.0, readout_p01=0.0, readout_p10=0.0, t1_us=None, t2_us=None)
    parts = [("gates_1q", "Single-qubit gate errors", dict(zero, p1=preset.p1)),
             ("gates_2q", "Two-qubit gate errors", dict(zero, p2=preset.p2)),
             ("decoherence", "Decoherence (T1/T2)", dict(zero, t1_us=preset.t1_us, t2_us=preset.t2_us)),
             ("readout", "Readout errors", dict(zero, readout_p01=preset.readout_p01, readout_p10=preset.readout_p10))]
    items = []
    for source, label, fields in parts:
        alone = replace(preset, **fields)
        if alone.is_ideal and alone.t1_us is None:
            continue
        items.append(BudgetItem(source=source, label=label,
                                fidelity_loss=round(1 - _fidelity(spec, ideal, alone), 6)))
    items.sort(key=lambda it: -it.fidelity_loss)
    total = round(1 - _fidelity(spec, ideal, preset), 6)
    if items and items[0].fidelity_loss > 1e-4:
        top = items[0]
        summary = f"{top.label} cost the most: {top.fidelity_loss:.1%} of the match to the noiseless ideal"
        if len(items) > 1:
            summary += f", against {items[1].fidelity_loss:.1%} for {items[1].label[0].lower()}{items[1].label[1:]}"
        summary += f". All sources together cost {total:.1%}; improving {top.label[0].lower()}{top.label[1:]} helps this circuit most."
    else:
        summary = f"Noise barely affects this circuit: all sources together cost {total:.1%}."
    return ErrorBudget(total_loss=total, items=items, summary=summary)


def scaled_preset(base: NoisePreset, scale: float) -> NoisePreset:
    """``base`` with every error rate times ``scale`` (coherence times divided by it)."""
    t1 = None if base.t1_us is None or scale == 0 else base.t1_us / scale
    t2 = None if base.t2_us is None or scale == 0 else base.t2_us / scale
    if t1 is not None and t2 is not None:
        t2 = min(t2, 2 * t1)  # physical bound T2 <= 2 T1
    return replace(base, p1=min(base.p1 * scale, 0.75), p2=min(base.p2 * scale, 0.9375),
                   readout_p01=min(base.readout_p01 * scale, 0.5), readout_p10=min(base.readout_p10 * scale, 0.5),
                   t1_us=t1, t2_us=t2)


def noise_sweep(spec: CircuitSpec, preset: NoisePreset, ideal: Distribution) -> NoiseSweep:
    """Fidelity as hardware gets better or worse, and the noise level needed for a 99% match."""
    base = preset if not preset.is_ideal else get_preset("realistic")
    answer = max(ideal, key=ideal.get) if max(ideal.values()) > 0.99 else None

    def point(s: float) -> SweepPoint:
        dist = noisy_distribution(spec, scaled_preset(base, s))
        return SweepPoint(scale=s, fidelity=round(hellinger_fidelity(ideal, dist), 6),
                          success=round(dist.get(answer, 0.0), 6) if answer else None)

    points = [point(s) for s in SWEEP_SCALES]
    scale: float | None = None  # largest noise scale that still reaches the target
    failing = [p.scale for p in points if p.fidelity < TARGET_FIDELITY]
    if failing:
        hi = min(failing)
        lo = max([p.scale for p in points if p.scale < hi and p.fidelity >= TARGET_FIDELITY], default=0.0)
        for _ in range(7):  # bisection (geometric once the bracket is above zero)
            mid = math.sqrt(lo * hi) if lo > 0 else (lo + hi) / 2
            if point(mid).fidelity >= TARGET_FIDELITY:
                lo = mid
            else:
                hi = mid
        scale = round(lo, 4)
    ok_now = next(p.fidelity for p in points if p.scale == 1.0) >= TARGET_FIDELITY
    label = base.label.lower()
    if ok_now:
        summary = (f"Already above a {TARGET_FIDELITY:.0%} match at {label} noise"
                   + (f"; it stays there until noise is {scale:.2g}× today's level." if scale else
                      f", even with {SWEEP_SCALES[-1]:g}× the noise."))
    elif scale:
        summary = (f"For a {TARGET_FIDELITY:.0%} match, noise must fall to {scale:.2g}× today's {label} level: "
                   f"hardware about {1 / scale:.1f}× better.")
    else:
        summary = f"Even near-perfect hardware stays below a {TARGET_FIDELITY:.0%} match for this circuit."
    if preset.is_ideal:
        summary += " (Baseline: the realistic preset, since this run was noiseless.)"
    return NoiseSweep(baseline=base.name, points=points, scale_for_target=scale, summary=summary)


def _invert_readout(spec: CircuitSpec, dist: Distribution, p01: float, p10: float) -> dict[str, float]:
    """Apply the inverse of each measured bit's confusion matrix (the result may dip below zero)."""
    det = (1 - p01) * (1 - p10) - p01 * p10
    inv = [[(1 - p10) / det, -p10 / det], [-p01 / det, (1 - p01) / det]]  # inv[true][read]
    nc = spec.num_clbits
    dist = dict(dist)
    for _, c in spec.measured_pairs():
        idx = nc - 1 - c
        out: dict[str, float] = {}
        for key, p in dist.items():
            read = int(key[idx])
            for true in (0, 1):
                k = key[:idx] + str(true) + key[idx + 1:]
                out[k] = out.get(k, 0.0) + inv[true][read] * p
        dist = out
    return dist


def _clip(dist: dict[str, float]) -> Distribution:
    """Clip negative estimates to zero and renormalise."""
    clipped = {k: max(v, 0.0) for k, v in dist.items()}
    total = sum(clipped.values()) or 1.0
    return {k: round(v / total, 6) for k, v in clipped.items() if v / total > 1e-6}


def correct_readout(spec: CircuitSpec, measured: Distribution, preset: NoisePreset,
                    ideal: Distribution) -> Mitigation | None:
    """Undo the known readout error by inverting each bit's confusion matrix."""
    p01, p10 = preset.readout_p01, preset.readout_p10
    if not (p01 or p10) or not measured:
        return None
    corrected = _clip(_invert_readout(spec, measured, p01, p10))
    raw_f, cor_f = hellinger_fidelity(ideal, measured), hellinger_fidelity(ideal, corrected)
    summary = (f"Undoing the known readout error lifts the match to the noiseless ideal from {raw_f:.3f} to "
               f"{cor_f:.3f}. What is left comes from gate errors and decoherence, which readout "
               f"correction cannot undo.")
    return Mitigation(corrected=corrected, fidelity_raw=round(raw_f, 6), fidelity_corrected=round(cor_f, 6),
                      summary=summary)


# ---------------------------------------------------------------- zero-noise extrapolation

_INVERSE = {"S": "SDG", "SDG": "S", "T": "TDG", "TDG": "T"}


def inverse_operation(op: Operation) -> Operation:
    """The gate that undoes ``op`` (up to a global phase: the inverse of SX is written RX(-pi/2))."""
    if op.gate in _INVERSE:
        return op.model_copy(update={"gate": _INVERSE[op.gate]})
    if op.gate in ("RX", "RY", "RZ", "CP"):
        return op.model_copy(update={"params": [-op.params[0]]})
    if op.gate == "SX":
        return op.model_copy(update={"gate": "RX", "params": [-math.pi / 2]})
    return op  # H, X, Y, Z, CX, CZ, SWAP, CCX are their own inverses


def fold(spec: CircuitSpec, scale: int) -> CircuitSpec:
    """Global unitary folding: U (U^-1 U)^k, the same circuit with ``scale`` = 2k + 1 times the gates.

    This is how zero-noise extrapolation raises the noise on real hardware: every
    extra gate adds its own error while the ideal result stays the same.
    """
    gates = [op for op in spec.operations if op.gate not in ("MEASURE", "BARRIER")]
    meas = [op for op in spec.operations if op.gate == "MEASURE"]
    back = [inverse_operation(op) for op in reversed(gates)]
    ops = list(gates)
    for _ in range((scale - 1) // 2):
        ops += back + gates
    return spec.model_copy(update={"operations": ops + meas})


def richardson(scales: tuple[int, ...]) -> list[float]:
    """Weights c_i with sum c_i f(s_i) = f(0) for any polynomial f of degree < len(scales)."""
    return [math.prod(sj / (sj - si) for sj in scales if sj != si) for si in scales]


def zero_noise(spec: CircuitSpec, preset: NoisePreset, ideal: Distribution) -> ZeroNoise | None:
    """Zero-noise extrapolation by gate folding, after readout correction.

    Readout error is removed first (exactly, by the inverse confusion matrix), then
    the circuit runs at 1x, 3x and 5x its gate noise and each outcome's probability
    is extrapolated back to zero noise. Done twice: with exact probabilities, and
    with ``ZNE_SHOTS`` sampled shots per noise level, since on hardware every
    probability is estimated from shots and extrapolation amplifies their noise.
    """
    gates = sum(1 for op in spec.operations if op.gate not in ("MEASURE", "BARRIER"))
    if preset.is_ideal or spec.num_qubits > MAX_ZNE_QUBITS or not gates or gates > MAX_ZNE_GATES:
        return None
    coeffs = richardson(ZNE_SCALES)
    gate_only = replace(preset, readout_p01=0.0, readout_p10=0.0)
    exact = [noisy_distribution(fold(spec, s), gate_only) for s in ZNE_SCALES]
    keys = sorted(set(ideal).union(*exact))
    mitigated = _clip({k: sum(c * d.get(k, 0.0) for c, d in zip(coeffs, exact)) for k in keys})

    rng = np.random.default_rng(1234)
    sampled = []
    for s in ZNE_SCALES:
        full = noisy_distribution(fold(spec, s), preset)
        ks = sorted(full)
        p = np.array([full[k] for k in ks])
        counts = rng.multinomial(ZNE_SHOTS, p / p.sum())
        est = {k: n / ZNE_SHOTS for k, n in zip(ks, counts) if n}
        if preset.readout_p01 or preset.readout_p10:
            est = _invert_readout(spec, est, preset.readout_p01, preset.readout_p10)
        sampled.append(est)
    keys = sorted(set(keys).union(*sampled))
    from_shots = _clip({k: sum(c * d.get(k, 0.0) for c, d in zip(coeffs, sampled)) for k in keys})

    top = max(ideal, key=ideal.get)
    top_at = [round(d.get(top, 0.0), 6) for d in exact]
    top_zero = round(sum(c * p for c, p in zip(coeffs, top_at)), 6)
    raw = hellinger_fidelity(ideal, noisy_distribution(spec, preset))
    at = [round(hellinger_fidelity(ideal, d), 6) for d in exact]
    mit, shots_f = hellinger_fidelity(ideal, mitigated), hellinger_fidelity(ideal, from_shots)
    ro_shots = hellinger_fidelity(ideal, _clip(sampled[0]))
    overhead = sum(c * c for c in coeffs)
    verb = "lifts" if mit > at[0] + 1e-4 else "barely changes"
    summary = (f"Zero-noise extrapolation {verb} the match to the noiseless ideal: {raw:.3f} as measured, "
               f"{at[0]:.3f} after readout correction, {mit:.3f} after extrapolating from "
               f"{', '.join(f'{s}x' for s in ZNE_SCALES)} noise, with exact probabilities. ")
    if shots_f > ro_shots + 1e-3:
        summary += (f"With {ZNE_SHOTS:,} shots per level it still helps ({ro_shots:.3f} to {shots_f:.3f}), "
                    f"at {sum(ZNE_SCALES)}x the gate executions and about {overhead:.1f}x the shots for the "
                    f"same error bars, since extrapolation amplifies shot noise.")
    else:
        summary += (f"With {ZNE_SHOTS:,} shots per level, shot noise eats the gain ({ro_shots:.3f} without "
                    f"extrapolation, {shots_f:.3f} with it): extrapolation amplifies shot noise about "
                    f"{overhead:.1f}x, so it needs more shots to pay off.")
    return ZeroNoise(scales=list(ZNE_SCALES), coefficients=[round(c, 6) for c in coeffs], fidelity_at=at,
                     mitigated=mitigated, fidelity_raw=round(raw, 6), fidelity_readout=at[0],
                     fidelity_mitigated=round(mit, 6), fidelity_shots=round(shots_f, 6),
                     fidelity_readout_shots=round(ro_shots, 6), shots=ZNE_SHOTS,
                     shot_overhead=round(overhead, 4), outcome=top, outcome_ideal=round(ideal[top], 6),
                     outcome_at=top_at, outcome_zero=top_zero, summary=summary)


# ---------------------------------------------------------------- real chip layouts

BASIS = ["rz", "sx", "x", "cx"]  # IBM-style native gates; rz is virtual (error-free)
FALCON_7Q = [(0, 1), (1, 2), (1, 3), (3, 5), (4, 5), (5, 6)]  # 7-qubit heavy-hex chips (IBM Falcon r5.11H)


def chip_layouts(spec: CircuitSpec, preset: NoisePreset) -> tuple[list[LayoutCost], str]:
    """Compile onto all-to-all, a line and heavy-hex wiring; count routing SWAPs and estimate success."""
    from qiskit import transpile
    from qiskit.transpiler import CouplingMap

    n = spec.num_qubits
    base = preset if not preset.is_ideal else get_preset("realistic")
    qc = build_reference_circuit(spec)
    hex_map = CouplingMap(FALCON_7Q) if n <= 7 else CouplingMap.from_heavy_hex(3)
    hex_map.make_symmetric()
    layouts = [("all-to-all", "every qubit wired to every other (trapped ions)", None),
               ("line", f"{n} qubits in a row, each talking only to its neighbours", CouplingMap.from_line(n)),
               ("heavy-hex", f"IBM heavy-hex chip ({hex_map.size()} qubits)", hex_map)]
    read_ok = 1 - (base.readout_p01 + base.readout_p10) / 2
    out: list[LayoutCost] = []
    for name, desc, cmap in layouts:
        if n < 2 and cmap is not None:
            continue
        compiled = transpile(qc, coupling_map=cmap, basis_gates=BASIS, optimization_level=1, seed_transpiler=1234)
        ops = compiled.count_ops()
        cx, one = ops.get("cx", 0), ops.get("sx", 0) + ops.get("x", 0)
        success = (1 - base.p1) ** one * (1 - base.p2) ** cx * read_ok ** len(spec.measured_pairs())
        out.append(LayoutCost(layout=name, description=desc, depth=compiled.depth(), two_qubit_gates=cx,
                              swaps_added=0, estimated_success=round(success, 4)))
    if out:
        ref = out[0].two_qubit_gates
        for lay in out[1:]:
            lay.swaps_added = max(0, round((lay.two_qubit_gates - ref) / 3))
    worst = max(out, key=lambda lay: lay.swaps_added, default=None)
    if not worst or worst.swaps_added == 0:
        cx = out[0].two_qubit_gates if out else 0
        summary = ("Every two-qubit gate already sits between neighbouring qubits, so no layout needs extra SWAPs "
                   f"({cx} CNOT{'s' if cx != 1 else ''} on every chip).")
    else:
        summary = (f"Wired all-to-all it needs {out[0].two_qubit_gates} CNOTs. On a {worst.layout} chip, routing adds "
                   f"{worst.swaps_added} SWAP{'s' if worst.swaps_added != 1 else ''} ({worst.two_qubit_gates} CNOTs) "
                   f"and the rough success estimate drops from {out[0].estimated_success:.2f} to "
                   f"{worst.estimated_success:.2f}: the wiring of the chip costs accuracy too.")
    return out, summary


# ---------------------------------------------------------------- exports

def exports(spec: CircuitSpec) -> Exports:
    qc = QuantumCircuit(spec.num_qubits, spec.num_clbits, name=(spec.metadata.title or "qcanvas")[:40])
    qc.compose(build_reference_circuit(spec), inplace=True)
    for q, c in spec.measured_pairs():
        qc.measure(q, c)
    return Exports(qasm2=qasm2.dumps(qc), qasm3=qasm3.dumps(qc))  # QASM 2 uses Qiskit's qelib1.inc


# ---------------------------------------------------------------- all together

def analyze_circuit(spec: CircuitSpec, noise: str = "realistic",
                    measured: Distribution | None = None) -> CircuitInsights:
    """Every insight for one circuit under one noise preset."""
    preset = get_preset(noise)
    ideal = ideal_distribution(spec)
    notes: list[str] = []
    noisy_ok = spec.num_qubits <= MAX_NOISY_QUBITS
    if not noisy_ok:
        notes.append(f"Noise analyses skipped above {MAX_NOISY_QUBITS} qubits (the exact density matrix gets too large).")
    rho = noisy_state(spec, preset) if noisy_ok and not preset.is_ideal else None
    layouts, layout_summary = chip_layouts(spec, preset)
    return CircuitInsights(
        layouts=layouts,
        layout_summary=layout_summary,
        steps=step_states(spec),
        entanglement=entanglement(spec, preset, rho),
        budget=error_budget(spec, preset, ideal) if noisy_ok and not preset.is_ideal else None,
        sweep=noise_sweep(spec, preset, ideal) if noisy_ok else None,
        mitigation=correct_readout(spec, measured, preset, ideal) if measured else None,
        zne=zero_noise(spec, preset, ideal) if noisy_ok else None,
        exports=exports(spec),
        notes=notes,
    )
