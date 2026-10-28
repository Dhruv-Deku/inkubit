"""Circuit insights: step states, entanglement, error budget, noise sweep, readout correction, exports."""

from __future__ import annotations

import math

import numpy as np
import pytest
from qiskit import qasm2
from qiskit.quantum_info import SuperOp

from qcanvas.insights.circuit import (
    TARGET_FIDELITY,
    analyze_circuit,
    correct_readout,
    gate_channels,
    noisy_distribution,
    scaled_preset,
    step_states,
)
from qcanvas.sim.noise import gate_errors, get_preset
from qcanvas.spec import parse_spec
from qcanvas.verify.expected import apply_readout_error, ideal_distribution
from qcanvas.verify.expected import noisy_distribution as aer_noisy_distribution
from qcanvas.verify.metrics import hellinger_fidelity


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


def test_analysis_is_fast_enough_for_every_example(example):
    import time

    for name in ["ghz3", "grover2", "bernstein_vazirani", "toffoli_and"]:
        start = time.perf_counter()
        analyze_circuit(parse_spec(example(name)), "realistic")
        assert time.perf_counter() - start < 5, name
    assert math.isfinite(start)
