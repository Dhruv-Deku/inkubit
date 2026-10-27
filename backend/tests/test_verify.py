"""P3: independent expected distributions, metrics and verdicts."""

from __future__ import annotations

import pytest
from qiskit import ClassicalRegister, transpile
from qiskit_aer import AerSimulator

from qcanvas.codegen.template import generate_code
from qcanvas.sim.noise import build_noise_model, get_preset
from qcanvas.sim.runner import run_code
from qcanvas.spec import parse_spec
from qcanvas.verify import ideal_distribution, noisy_distribution, verify_counts
from qcanvas.verify.expected import apply_readout_error, build_reference_circuit
from qcanvas.verify.metrics import hellinger_fidelity, shot_noise_tvd_bound, total_variation_distance


def sample_counts(spec, noise: str, shots: int = 4096, seed: int = 99) -> dict[str, int]:
    """Sample counts in-process from a circuit built from ``spec`` (fast test helper)."""
    qc = build_reference_circuit(spec)
    qc.add_register(ClassicalRegister(spec.num_clbits))
    for q, c in spec.measured_pairs():
        qc.measure(q, c)
    sim = AerSimulator(noise_model=build_noise_model(get_preset(noise)), seed_simulator=seed)
    return sim.run(transpile(qc, sim, optimization_level=0), shots=shots).result().get_counts()


def test_ideal_bell():
    spec = parse_spec({"kind": "circuit", "num_qubits": 2, "num_clbits": 2,
                       "operations": [{"gate": "H", "targets": [0]},
                                      {"gate": "CX", "controls": [0], "targets": [1]}],
                       "measurements": [{"qubit": 0, "clbit": 0}, {"qubit": 1, "clbit": 1}]})
    dist = ideal_distribution(spec)
    assert dist.keys() == {"00", "11"}
    assert dist["00"] == pytest.approx(0.5) and dist["11"] == pytest.approx(0.5)


def test_bit_order_matches_qiskit():
    # X on qubit 0, measured into classical bit 1 of 2 -> key "10" (rightmost char is c0)
    spec = parse_spec({"kind": "circuit", "num_qubits": 2, "num_clbits": 2,
                       "operations": [{"gate": "X", "targets": [0]}],
                       "measurements": [{"qubit": 0, "clbit": 1}, {"qubit": 1, "clbit": 0}]})
    assert ideal_distribution(spec) == pytest.approx({"10": 1.0})
    assert sample_counts(spec, "ideal") == {"10": 4096}


def test_readout_error_is_exact():
    spec = parse_spec({"kind": "circuit", "num_qubits": 1, "num_clbits": 1, "operations": [],
                       "measurements": [{"qubit": 0, "clbit": 0}]})
    assert apply_readout_error({"0": 1.0}, spec, 0.1, 0.2) == pytest.approx({"0": 0.9, "1": 0.1})
    assert apply_readout_error({"1": 1.0}, spec, 0.1, 0.2) == pytest.approx({"0": 0.2, "1": 0.8})


def test_noisy_distribution_sums_to_one_and_spreads(example):
    spec = parse_spec(example("ghz3"))
    dist = noisy_distribution(spec, "realistic")
    assert sum(dist.values()) == pytest.approx(1.0)
    assert len(dist) == 8  # noise reaches every outcome
    assert dist["000"] + dist["111"] > 0.85


def test_metrics():
    p, q = {"0": 0.5, "1": 0.5}, {"0": 1.0}
    assert total_variation_distance(p, q) == pytest.approx(0.5)
    assert hellinger_fidelity(p, p) == pytest.approx(1.0)
    assert hellinger_fidelity(p, q) == pytest.approx(0.5)
    assert shot_noise_tvd_bound({"0": 0.5, "1": 0.5}, 4096) == pytest.approx(3 * 0.5 * 2 * 0.5 / 64)


@pytest.mark.parametrize("name", ["bell", "ghz3", "superposition"])
@pytest.mark.parametrize("noise", ["ideal", "low_noise", "realistic"])
def test_correct_circuits_pass(example, name, noise):
    spec = parse_spec(example(name))
    verdict = verify_counts(spec, sample_counts(spec, noise), noise)
    assert verdict.passed, verdict.reason
    assert verdict.metrics.tvd <= verdict.metrics.tvd_threshold


@pytest.mark.parametrize("noise", ["ideal", "realistic"])
def test_bell_without_cnot_fails(example, noise):
    bell = parse_spec(example("bell"))
    broken = bell.model_copy(update={"operations": bell.operations[:1]})
    verdict = verify_counts(bell, sample_counts(broken, noise), noise)
    assert not verdict.passed
    assert verdict.metrics.tvd > 0.4
    assert "Expected ~50% |00⟩ and 50% |11⟩" in verdict.reason
    assert {d.outcome for d in verdict.deviations[:2]} & {"01", "11"}


def test_empty_counts_fail(example):
    verdict = verify_counts(parse_spec(example("bell")), {}, "ideal")
    assert not verdict.passed and "no measurement counts" in verdict.reason


@pytest.mark.slow
def test_generated_code_verifies_end_to_end(example):
    spec = parse_spec(example("ghz3"))
    result = run_code(generate_code(spec, noise="realistic"))
    verdict = verify_counts(spec, result.counts, "realistic")
    assert verdict.passed, verdict.reason
    assert verdict.metrics.fidelity_vs_ideal < 0.999  # noise visibly cost something
