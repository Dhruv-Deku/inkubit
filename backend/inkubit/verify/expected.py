"""Expected outcome distributions computed straight from the spec.

Nothing here touches generated code: the reference circuit is rebuilt from
the spec with its own small builder, so a bug in codegen (or in model-written
code) cannot hide itself by also corrupting the expectation.
"""

from __future__ import annotations

from qiskit import QuantumCircuit
from qiskit.quantum_info import DensityMatrix, Statevector
from qiskit_aer import AerSimulator

from inkubit.sim.noise import NoisePreset, build_gate_noise_model, get_preset
from inkubit.spec.models import CircuitSpec, Operation

Distribution = dict[str, float]

_ONE_Q = {"H": "h", "X": "x", "Y": "y", "Z": "z", "S": "s", "T": "t", "SDG": "sdg", "TDG": "tdg", "SX": "sx"}
_ROT = {"RX": "rx", "RY": "ry", "RZ": "rz"}
_EPS = 1e-12


def append_operation(qc: QuantumCircuit, op: Operation) -> None:
    """Append the unitary action of one spec operation (BARRIER and MEASURE add nothing)."""
    g = op.gate
    if g in _ONE_Q:
        for q in op.targets:
            getattr(qc, _ONE_Q[g])(q)
    elif g in _ROT:
        for q in op.targets:
            getattr(qc, _ROT[g])(op.params[0], q)
    elif g == "CX":
        qc.cx(op.controls[0], op.targets[0])
    elif g == "CZ":
        qc.cz(op.controls[0], op.targets[0])
    elif g == "CP":
        qc.cp(op.params[0], op.controls[0], op.targets[0])
    elif g == "CCX":
        qc.ccx(op.controls[0], op.controls[1], op.targets[0])
    elif g == "SWAP":
        qc.swap(op.targets[0], op.targets[1])


def build_reference_circuit(spec: CircuitSpec) -> QuantumCircuit:
    """The unitary part of the spec (no measurements) as a QuantumCircuit."""
    qc = QuantumCircuit(spec.num_qubits)
    for op in spec.operations:
        append_operation(qc, op)
    return qc


def _to_clbit_keys(probs: dict[str, float], spec: CircuitSpec, pairs: list[tuple[int, int]]) -> Distribution:
    """Map probabilities keyed over measured qubits (qargs order) to Qiskit clbit strings."""
    nc = spec.num_clbits
    out: Distribution = {}
    for key, p in probs.items():
        if p < _EPS:
            continue
        bits = ["0"] * nc
        for i, (_, c) in enumerate(pairs):
            bits[nc - 1 - c] = key[len(key) - 1 - i]
        k = "".join(bits)
        out[k] = out.get(k, 0.0) + float(p)
    return out


def ideal_distribution(spec: CircuitSpec) -> Distribution:
    """Exact noiseless outcome probabilities, keyed like Qiskit counts."""
    pairs = spec.measured_pairs()
    sv = Statevector.from_instruction(build_reference_circuit(spec))
    return _to_clbit_keys(sv.probabilities_dict(qargs=[q for q, _ in pairs]), spec, pairs)


def apply_readout_error(dist: Distribution, spec: CircuitSpec, p01: float, p10: float) -> Distribution:
    """Exactly apply independent per-bit readout flips to measured classical bits."""
    nc = spec.num_clbits
    out = dict(dist)
    for _, c in spec.measured_pairs():
        idx = nc - 1 - c
        nxt: Distribution = {}
        for key, p in out.items():
            bit = key[idx]
            flip = p01 if bit == "0" else p10
            flipped = key[:idx] + ("1" if bit == "0" else "0") + key[idx + 1:]
            nxt[key] = nxt.get(key, 0.0) + p * (1 - flip)
            if flip:
                nxt[flipped] = nxt.get(flipped, 0.0) + p * flip
        out = nxt
    return {k: v for k, v in out.items() if v > _EPS}


def noisy_state(spec: CircuitSpec, preset: NoisePreset | str) -> DensityMatrix:
    """Exact state just before measurement under the preset's gate noise (density matrix)."""
    preset = get_preset(preset) if isinstance(preset, str) else preset
    qc = build_reference_circuit(spec)
    gate_noise = build_gate_noise_model(preset)
    if gate_noise is None:
        return DensityMatrix(Statevector.from_instruction(qc))
    qc.save_density_matrix()
    sim = AerSimulator(method="density_matrix", noise_model=gate_noise)
    return DensityMatrix(sim.run(qc, shots=1).result().data()["density_matrix"])


def noisy_distribution(spec: CircuitSpec, preset: NoisePreset | str) -> Distribution:
    """Exact outcome probabilities under a noise preset (density-matrix simulation)."""
    preset = get_preset(preset) if isinstance(preset, str) else preset
    if preset.is_ideal:
        return ideal_distribution(spec)
    pairs = spec.measured_pairs()
    if build_gate_noise_model(preset) is None:
        dist = ideal_distribution(spec)
    else:
        rho = noisy_state(spec, preset)
        dist = _to_clbit_keys(rho.probabilities_dict(qargs=[q for q, _ in pairs]), spec, pairs)
    return apply_readout_error(dist, spec, preset.readout_p01, preset.readout_p10)
