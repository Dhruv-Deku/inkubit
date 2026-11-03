"""Circuit insights: step states, entanglement, error budget, noise sweep, readout correction, ZNE, exports."""

from __future__ import annotations

import math

import numpy as np
import pytest
from qiskit import qasm2
from qiskit import QuantumCircuit
from qiskit.quantum_info import DensityMatrix, Operator, SuperOp, concurrence, random_density_matrix

from inkubit.insights.circuit import (
    TARGET_FIDELITY,
    ZNE_SCALES,
    _concurrence,
    analyze_circuit,
    correct_readout,
    fold,
    gate_channels,
    inverse_operation,
    noisy_distribution,
    richardson,
    scaled_preset,
    step_states,
    zero_noise,
)
from inkubit.spec.models import Operation
from inkubit.verify.expected import append_operation
from inkubit.sim.noise import gate_errors, get_preset
from inkubit.spec import parse_spec
from inkubit.verify.expected import apply_readout_error, ideal_distribution
from inkubit.verify.expected import noisy_distribution as aer_noisy_distribution
from inkubit.verify.metrics import hellinger_fidelity


@pytest.mark.parametrize("name", ["bell", "phase_estimation", "toffoli_and"])
@pytest.mark.parametrize("noise", ["low_noise", "realistic"])
def test_direct_evolution_matches_the_verifiers_simulator(example, name, noise):
    spec = parse_spec(example(name))
    fast, aer = noisy_distribution(spec, get_preset(noise)), aer_noisy_distribution(spec, noise)
    assert max(abs(fast.get(k, 0) - aer.get(k, 0)) for k in set(fast) | set(aer)) < 1e-8


def test_closed_form_toffoli_channel_equals_the_generic_one():
    preset = get_preset("realistic")
    generic = SuperOp(gate_errors(preset)[3].to_quantumchannel()).data
    assert np.abs(generic - gate_channels(preset)[3].data).max() < 1e-9


def test_steps_show_superposition_then_entanglement(example):
    steps = step_states(parse_spec(example("bell")))
    assert [s.label for s in steps] == ["start: every qubit is 0", "H on q0", "CX q0→q1"]
    assert steps[0].bloch[0] == pytest.approx([0, 0, 1])
    assert steps[1].bloch[0] == pytest.approx([1, 0, 0]) and steps[1].entangled == [False, False]
    assert steps[2].bloch[0] == pytest.approx([0, 0, 0], abs=1e-9) and steps[2].entangled == [True, True]
    assert {a.basis: a.probability for a in steps[2].amplitudes} == pytest.approx({"00": 0.5, "11": 0.5})


def test_entanglement_pairs_and_ghz(example):
    bell = analyze_circuit(parse_spec(example("bell")), "realistic")
    (pair,) = bell.entanglement.pairs
    assert (pair.a, pair.b, pair.ideal) == (0, 1, pytest.approx(1.0))
    assert 0.8 < pair.noisy < 1.0 and "survives" in bell.entanglement.summary
    ghz = analyze_circuit(parse_spec(example("ghz3")), "realistic")
    assert ghz.entanglement.pairs == []  # GHZ entanglement is not pairwise
    assert ghz.entanglement.qubit_entropy == pytest.approx([1.0, 1.0, 1.0])
    assert "GHZ" in ghz.entanglement.summary
    none = analyze_circuit(parse_spec(example("superposition")), "realistic")
    assert "no entanglement" in none.entanglement.summary


def test_error_budget_names_the_biggest_source(example):
    spec = parse_spec(example("bell"))
    budget = analyze_circuit(spec, "realistic").budget
    assert budget.items[0].source == "readout"
    assert {i.source for i in budget.items} == {"gates_1q", "gates_2q", "decoherence", "readout"}
    total = 1 - hellinger_fidelity(ideal_distribution(spec), aer_noisy_distribution(spec, "realistic"))
    assert budget.total_loss == pytest.approx(total, abs=1e-6)
    assert analyze_circuit(spec, "ideal").budget is None


def test_noise_sweep_finds_the_hardware_needed(example):
    spec = parse_spec(example("bell"))
    sweep = analyze_circuit(spec, "realistic").sweep
    fids = [p.fidelity for p in sweep.points]
    assert fids[0] == pytest.approx(1.0) and all(a >= b for a, b in zip(fids, fids[1:]))
    s = sweep.scale_for_target
    assert 0 < s < 1 and "better" in sweep.summary
    ideal = ideal_distribution(spec)
    at = lambda k: hellinger_fidelity(ideal, noisy_distribution(spec, scaled_preset(get_preset("realistic"), k)))  # noqa: E731
    assert at(s) >= TARGET_FIDELITY > at(s * 1.1)


def test_readout_correction_undoes_a_known_readout_error(example):
    spec = parse_spec(example("ghz3"))
    preset = get_preset("realistic")
    ideal = ideal_distribution(spec)
    flipped = apply_readout_error(ideal, spec, preset.readout_p01, preset.readout_p10)
    fixed = correct_readout(spec, flipped, preset, ideal)
    assert fixed.corrected == pytest.approx(ideal, abs=1e-5)
    assert fixed.fidelity_raw < 0.95 and fixed.fidelity_corrected == pytest.approx(1.0)
    assert correct_readout(spec, ideal, get_preset("ideal"), ideal) is None


def test_qasm_exports_round_trip(example):
    spec = parse_spec(example("phase_estimation"))
    ins = analyze_circuit(spec, "low_noise")
    assert ins.exports.qasm3.startswith("OPENQASM 3.0;")
    back = qasm2.loads(ins.exports.qasm2, custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS)
    assert back.num_qubits == 4 and back.count_ops()["measure"] == 3 and back.count_ops()["cp"] == 6


def test_chip_layouts_count_routing_swaps(example):
    ins = analyze_circuit(parse_spec(example("phase_estimation")), "realistic")
    by = {lay.layout: lay for lay in ins.layouts}
    assert set(by) == {"all-to-all", "line", "heavy-hex"} and by["all-to-all"].swaps_added == 0
    assert by["line"].swaps_added > 0 and by["line"].estimated_success < by["all-to-all"].estimated_success
    bell = analyze_circuit(parse_spec(example("bell")), "realistic")
    assert all(lay.swaps_added == 0 for lay in bell.layouts) and "no layout needs extra SWAPs" in bell.layout_summary


def test_analysis_is_fast_enough_for_every_example(example):
    import time

    for name in ["ghz3", "grover2", "bernstein_vazirani", "toffoli_and"]:
        start = time.perf_counter()
        analyze_circuit(parse_spec(example(name)), "realistic")
        assert time.perf_counter() - start < 5, name
    assert math.isfinite(start)


def test_concurrence_matches_qiskit():
    for seed in range(20):
        rho = random_density_matrix(4, seed=seed)
        assert _concurrence(rho.data) == pytest.approx(float(concurrence(rho)), abs=1e-9)
    bell = DensityMatrix.from_label("00").evolve(QuantumCircuit(2).compose(_bell_qc()))
    assert _concurrence(bell.data) == pytest.approx(1.0)


def _bell_qc():
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    return qc


def test_entanglement_web_tells_pairs_from_group_entanglement(example):
    bell = step_states(parse_spec(example("bell")))
    assert bell[0].links == [] and bell[-1].links == [[0, 1, pytest.approx(1.0)]]
    assert bell[-1].entropy == pytest.approx([1.0, 1.0])
    ghz = step_states(parse_spec(example("ghz3")))[-1]
    assert ghz.links == [] and ghz.entropy == pytest.approx([1.0, 1.0, 1.0])  # the whole group, no pair alone
    w = step_states(parse_spec(example("w_state")))[-1]
    assert [c for _, _, c in w.links] == pytest.approx([2 / 3] * 3, abs=1e-4)  # W keeps pairwise entanglement


@pytest.mark.parametrize("gate,params,qs", [
    ("H", [], ([0], [])), ("S", [], ([0], [])), ("T", [], ([0], [])), ("SX", [], ([0], [])),
    ("RX", [0.3], ([0], [])), ("RZ", [1.1], ([0], [])), ("CP", [0.7], ([1], [0])), ("CX", [], ([1], [0])),
    ("SWAP", [], ([0, 1], [])), ("CCX", [], ([2], [0, 1])),
])
def test_every_gate_has_an_inverse(gate, params, qs):
    op = Operation(gate=gate, targets=qs[0], controls=qs[1], params=params)
    qc = QuantumCircuit(3)
    append_operation(qc, op)
    append_operation(qc, inverse_operation(op))
    u = Operator(qc).data
    assert abs(np.trace(u)) / 8 == pytest.approx(1.0)  # identity up to a global phase


def test_folding_keeps_the_ideal_result_and_multiplies_the_gates(example):
    spec = parse_spec(example("ghz3"))
    for s in ZNE_SCALES:
        folded = fold(spec, s)
        gates = [op for op in folded.operations if op.gate != "MEASURE"]
        assert len(gates) == s * 3
        assert ideal_distribution(folded) == pytest.approx(ideal_distribution(spec))
    assert richardson((1, 3, 5)) == pytest.approx([15 / 8, -5 / 4, 3 / 8])
    assert sum(richardson((1, 2, 4, 8))) == pytest.approx(1.0)


def test_zero_noise_extrapolation_recovers_most_of_the_ideal(example):
    spec = parse_spec(example("phase_estimation"))
    ideal = ideal_distribution(spec)
    z = zero_noise(spec, get_preset("realistic"), ideal)
    assert z is not None
    assert z.fidelity_raw < z.fidelity_readout < z.fidelity_mitigated
    assert z.fidelity_mitigated > 0.99 and z.fidelity_at[0] > z.fidelity_at[1] > z.fidelity_at[2]
    assert z.shot_overhead == pytest.approx(sum(c * c for c in richardson(ZNE_SCALES)), abs=1e-4)
    assert z.shots == 4000 and "shot" in z.summary
    assert zero_noise(spec, get_preset("ideal"), ideal) is None
    assert analyze_circuit(spec).zne is not None
