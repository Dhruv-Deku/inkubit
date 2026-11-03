"""Deterministic template codegen: spec -> standalone, readable Qiskit script.

The script is what the user sees and what the agent runs. It prints one
machine-readable line, ``INKUBIT_RESULT {json}``, that the runner parses.
"""

from __future__ import annotations

import math
from fractions import Fraction

from inkubit.sim.noise import (ONE_QUBIT_GATES, THREE_QUBIT_GATES, TOFFOLI_CNOTS, TWO_QUBIT_GATES, NoisePreset,
                               get_preset, toffoli_error)
from inkubit.spec.models import CircuitSpec, Operation

RESULT_MARKER = "INKUBIT_RESULT"
DEFAULT_SHOTS = 4096
DEFAULT_SEED = 1234


def format_angle(theta: float) -> str:
    """Render an angle as a readable ``pi`` expression when it is a simple fraction of pi."""
    if theta == 0:
        return "0"
    frac = Fraction(theta / math.pi).limit_denominator(16)
    if abs(float(frac) * math.pi - theta) < 1e-9:
        num, den = frac.numerator, frac.denominator
        sign = "-" if num < 0 else ""
        num = abs(num)
        top = "pi" if num == 1 else f"{num} * pi"
        return f"{sign}{top}" if den == 1 else f"{sign}{top} / {den}"
    return repr(float(theta))


def _uses_pi(spec: CircuitSpec) -> bool:
    return any("pi" in format_angle(p) for op in spec.operations for p in op.params)


def operation_lines(i: int, op: Operation) -> list[str]:
    """Qiskit statements for one spec operation, each tagged with its op index."""
    tag = f"  # op {i}: {op.gate}"
    g = op.gate
    if g in ("H", "X", "Y", "Z", "S", "T", "SDG", "TDG", "SX"):
        return [f"    qc.{g.lower()}({q}){tag} on q{q}" for q in op.targets]
    if g in ("RX", "RY", "RZ"):
        angle = format_angle(op.params[0])
        return [f"    qc.{g.lower()}({angle}, {q}){tag}({angle}) on q{q}" for q in op.targets]
    if g in ("CX", "CZ"):
        c, t = op.controls[0], op.targets[0]
        return [f"    qc.{g.lower()}({c}, {t}){tag}, control q{c} -> target q{t}"]
    if g == "CP":
        c, t = op.controls[0], op.targets[0]
        angle = format_angle(op.params[0])
        return [f"    qc.cp({angle}, {c}, {t}){tag}({angle}), control q{c} -> target q{t}"]
    if g == "CCX":
        (c0, c1), t = op.controls, op.targets[0]
        return [f"    qc.ccx({c0}, {c1}, {t}){tag}, controls q{c0}, q{c1} -> target q{t}"]
    if g == "SWAP":
        a, b = op.targets
        return [f"    qc.swap({a}, {b}){tag} q{a} <-> q{b}"]
    if g == "BARRIER":
        args = ", ".join(str(q) for q in op.targets)
        return [f"    qc.barrier({args}){tag}"]
    if g == "MEASURE":
        return [f"    qc.measure({q}, {c}){tag} q{q} -> c{c}" for q, c in zip(op.targets, op.clbits)]
    raise ValueError(f"unsupported gate {g}")


def _noise_block(preset: NoisePreset, toffoli: bool = False) -> list[str]:
    if preset.is_ideal:
        return [
            "def build_noise_model():",
            '    """Preset \'ideal\': no noise."""',
            "    return None",
        ]
    lines = [
        "def build_noise_model() -> NoiseModel:",
        f'    """Preset \'{preset.name}\': {preset.label.lower()}."""',
        "    noise = NoiseModel()",
        f"    one_qubit = depolarizing_error({preset.p1}, 1)",
        f"    two_qubit = depolarizing_error({preset.p2}, 2)",
    ]
    if toffoli:
        lines.append(f"    three_qubit = depolarizing_error({toffoli_error(preset)!r}, 3)  # {TOFFOLI_CNOTS} CNOTs' worth")
    if preset.t1_us is not None and preset.t2_us is not None:
        lines += [
            f"    # thermal relaxation: T1={preset.t1_us} us, T2={preset.t2_us} us",
            f"    relax_1q = thermal_relaxation_error({preset.t1_us}, {preset.t2_us}, {preset.gate_1q_us})",
            f"    relax_2q = thermal_relaxation_error({preset.t1_us}, {preset.t2_us}, {preset.gate_2q_us})",
            "    one_qubit = one_qubit.compose(relax_1q)",
            "    two_qubit = two_qubit.compose(relax_2q.expand(relax_2q))",
        ]
        if toffoli:
            lines += [
                f"    relax_3q = thermal_relaxation_error({preset.t1_us}, {preset.t2_us}, "
                f"{TOFFOLI_CNOTS * preset.gate_2q_us!r})",
                "    three_qubit = three_qubit.compose(relax_3q.expand(relax_3q).expand(relax_3q))",
            ]
    lines += [
        f"    noise.add_all_qubit_quantum_error(one_qubit, {ONE_QUBIT_GATES!r})",
        f"    noise.add_all_qubit_quantum_error(two_qubit, {TWO_QUBIT_GATES!r})",
        *([f"    noise.add_all_qubit_quantum_error(three_qubit, {THREE_QUBIT_GATES!r})"] if toffoli else []),
        f"    p01, p10 = {preset.readout_p01}, {preset.readout_p10}  # readout flips 0->1 and 1->0",
        "    noise.add_all_qubit_readout_error(ReadoutError([[1 - p01, p01], [p10, 1 - p10]]))",
        "    return noise",
    ]
    return lines


def generate_code(
    spec: CircuitSpec,
    noise: str = "ideal",
    shots: int = DEFAULT_SHOTS,
    seed: int = DEFAULT_SEED,
) -> str:
    """Generate a standalone Qiskit script for ``spec`` under a noise preset."""
    preset = get_preset(noise)
    title = spec.metadata.title or "circuit"
    imports = [
        "import json",
        *(["from math import pi"] if _uses_pi(spec) else []),
        "",
        "from qiskit import QuantumCircuit, transpile",
        "from qiskit_aer import AerSimulator",
    ]
    if not preset.is_ideal:
        noise_imports = "NoiseModel, ReadoutError, depolarizing_error"
        if preset.t1_us is not None:
            noise_imports += ", thermal_relaxation_error"
        imports.append(f"from qiskit_aer.noise import {noise_imports}")

    body = [
        f"    qc = QuantumCircuit({spec.num_qubits}, {spec.num_clbits})",
    ]
    for i, op in enumerate(spec.operations):
        body += operation_lines(i, op)
    for m in spec.measurements:
        body.append(f"    qc.measure({m.qubit}, {m.clbit})  # measure q{m.qubit} -> c{m.clbit}")
    body.append("    return qc")

    lines = [
        f'"""{title}: generated by Inkubit from a spec (v{spec.version}).',
        "",
        "Run it with:  python this_file.py",
        "Bitstrings follow Qiskit order: the rightmost character is classical bit 0.",
        '"""',
        *imports,
        "",
        f"SHOTS = {shots}",
        f"SEED = {seed}",
        f'NOISE_PRESET = "{preset.name}"',
        "",
        "",
        "def build_circuit() -> QuantumCircuit:",
        f'    """Build the {title} circuit, one line per drawn operation."""',
        *body,
        "",
        "",
        *_noise_block(preset, toffoli=any(op.gate == "CCX" for op in spec.operations)),
        "",
        "",
        "def main() -> None:",
        "    qc = build_circuit()",
        "    simulator = AerSimulator(noise_model=build_noise_model(), seed_simulator=SEED)",
        "    compiled = transpile(qc, simulator, optimization_level=0, seed_transpiler=SEED)",
        "    counts = simulator.run(compiled, shots=SHOTS).result().get_counts()",
        "    print(qc.draw(output=\"text\"))",
        "    print(\"counts:\", dict(sorted(counts.items())))",
        f'    print("{RESULT_MARKER} " + json.dumps({{"counts": counts, "shots": SHOTS, "noise": NOISE_PRESET}}))',
        "",
        "",
        'if __name__ == "__main__":',
        "    main()",
        "",
    ]
    return "\n".join(lines)
