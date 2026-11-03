"""Bell tests, state tomography and the error-correction lab: textbook values, exactly."""

from __future__ import annotations

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient
from qiskit.quantum_info import DensityMatrix, Statevector, random_density_matrix, random_statevector

from inkubit.api.app import app
from inkubit.insights.bell import TSIRELSON, _tensor, chsh_settings, chsh_value
from inkubit.insights.circuit import analyze_circuit
from inkubit.insights.tomography import _physical, tomography
from inkubit.qec import _logical_error, _logical_errors, repetition_lab
from inkubit.sim.noise import get_preset
from inkubit.spec import parse_spec

client = TestClient(app)


def _brute_chsh(t: np.ndarray, rng: np.random.Generator) -> float:
    best = -np.inf
    for _ in range(4000):
        v = rng.normal(size=(4, 3))
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        best = max(best, chsh_value(t, *v))
    return best


def test_horodecki_settings_reach_the_maximum_and_nothing_beats_them():
    rng = np.random.default_rng(1)
    for seed in range(5):
        rho = random_density_matrix(4, seed=seed).data
        t = _tensor(rho, 2)
        s = chsh_value(t, *chsh_settings(t))
        w = np.sort(np.linalg.eigvalsh(t.T @ t))[::-1]
        assert s == pytest.approx(2 * math.sqrt(w[0] + w[1]), abs=1e-9)
        assert _brute_chsh(t, rng) <= s + 1e-9


def test_bell_pair_reaches_tsirelson_and_survives_noise_with_shots(example):
    ins = analyze_circuit(parse_spec(example("bell")))
    (chsh,) = ins.bell.tests
    assert chsh.kind == "CHSH" and chsh.ideal == pytest.approx(TSIRELSON, abs=1e-6)
    assert 2 < chsh.shots_value < chsh.noisy < chsh.ideal  # readout error and noise each cost some
    assert chsh.sigmas > 5 and chsh.shots == 4000 and "standard errors" in ins.bell.summary


def test_ghz_breaks_mermin_but_no_pair_breaks_chsh(example):
    tests = analyze_circuit(parse_spec(example("ghz3"))).bell.tests
    assert [t.kind for t in tests] == ["Mermin"]  # GHZ pairs are not entangled at all
    assert tests[0].ideal == pytest.approx(4.0, abs=1e-6) and tests[0].noisy > 2


def test_w_state_pairs_stay_classical_while_the_trio_does_not(example):
    bt = analyze_circuit(parse_spec(example("w_state"))).bell
    pairs = [t for t in bt.tests if t.kind == "CHSH"]
    trio = next(t for t in bt.tests if t.kind == "Mermin")
    assert len(pairs) == 3 and all(t.ideal == pytest.approx(2 * math.sqrt(8 / 9), abs=1e-6) for t in pairs)
    assert not any(t.violates for t in pairs)
    assert trio.ideal == pytest.approx(3.046, abs=2e-3) and trio.violates  # the known W-state value
    assert "only the three together" in bt.summary


def test_no_bell_test_without_entanglement(example):
    assert analyze_circuit(parse_spec(example("superposition"))).bell is None


def test_physical_projection_keeps_trace_and_removes_negative_eigenvalues():
    rho = np.diag([0.6, 0.5, -0.1, 0.0]).astype(complex)
    out = _physical(rho)
    vals = np.linalg.eigvalsh(out)
    assert np.trace(out).real == pytest.approx(1.0) and vals.min() >= -1e-12
    good = random_density_matrix(4, seed=3).data
    assert _physical(good) == pytest.approx(good, abs=1e-12)  # already physical: unchanged


def test_tomography_rebuilds_the_state_from_shots(example):
    psi = random_statevector(4, seed=11).data
    ideal = tomography(psi, None, get_preset("ideal"))
    assert ideal.settings == 9 and ideal.fidelity_ideal > 0.97 and ideal.noisy_fidelity_ideal == pytest.approx(1.0)
    ins = analyze_circuit(parse_spec(example("ghz3")))
    t = ins.tomography
    assert t.n == 3 and t.settings == 27 and len(t.recon_re) == 8
    assert t.fidelity_ideal < 0.99 and abs(t.fidelity_ideal - t.noisy_fidelity_ideal) < 0.05
    rec = np.array(t.recon_re) + 1j * np.array(t.recon_im)
    assert np.trace(rec).real == pytest.approx(1.0, abs=1e-4) and np.linalg.eigvalsh(rec).min() > -1e-4
    assert analyze_circuit(parse_spec(example("phase_estimation"))).tomography is None  # 4 qubits: skipped


def test_repetition_code_matches_the_textbook_formulas():
    for p in (0.01, 0.1, 0.3):
        assert _logical_error(p, "bit", 0.0) == pytest.approx(3 * p ** 2 - 2 * p ** 3, abs=1e-12)
        odd = 3 * p * (1 - p) ** 2 + p ** 3  # an odd number of phase flips flips the logical phase
        assert _logical_error(p, "phase", 0.0) == pytest.approx(odd, abs=1e-12)
    assert _logical_errors([0.02, 0.2], "bit", 1.0) == pytest.approx([_logical_error(x, "bit", 1.0) for x in (0.02, 0.2)])


def test_better_gates_lower_the_break_even_point():
    real, better = repetition_lab(1.0), repetition_lab(0.1)
    assert 0 < better.bit.break_even < real.bit.break_even < 0.5
    assert real.phase.break_even is None and repetition_lab(4.0).bit.break_even is None
    assert repetition_lab(0.0).bit.break_even == pytest.approx(1e-4)
    i = next(k for k, p in enumerate(real.p) if p > 0.3)
    assert real.bit.realistic[i] < real.p[i]  # at high flip rates the code wins even with noisy gates
    body = client.get("/api/lab/repetition", params={"scale": 0.5}).json()
    assert body["scale"] == 0.5 and len(body["p"]) == len(body["bit"]["perfect"]) == 61
    assert client.get("/api/lab/repetition", params={"scale": 50}).status_code == 422


def test_insights_endpoint_carries_the_new_analyses(example):
    body = client.post("/api/insights", json={"spec": example("bell"), "noise": "realistic"}).json()
    assert body["bell"]["tests"][0]["kind"] == "CHSH" and body["tomography"]["n"] == 2
    assert body["zne"]["fidelity_mitigated"] > body["zne"]["fidelity_raw"]


def test_bell_pair_state_is_what_the_tests_assume():
    psi = Statevector.from_label("00").evolve(_bell_circuit()).data
    t = _tensor(DensityMatrix(psi).data, 2)
    assert np.diag(t) == pytest.approx([1, -1, 1])  # |Phi+>: XX = 1, YY = -1, ZZ = 1


def _bell_circuit():
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    return qc
