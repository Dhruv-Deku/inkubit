"""The GHZ fidelity estimate used on real hardware, checked on states whose fidelity is known exactly."""

from __future__ import annotations

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import DensityMatrix, Statevector

from inkubit.hardware import append_parity_basis, ghz_fidelity, parity, parity_phases


def _odds(state, n: int, phi: float | None) -> dict[str, float]:
    qc = QuantumCircuit(n)
    if phi is not None:
        append_parity_basis(qc, phi)
    probs = state.evolve(qc).probabilities_dict()
    return {k: float(v) for k, v in probs.items()}


def _estimate(state, n: int) -> dict[str, float]:
    return ghz_fidelity(_odds(state, n, None), [parity(_odds(state, n, phi)) for phi in parity_phases(n)], n)


def _ghz(n: int, phase: float = 0.0) -> Statevector:
    v = np.zeros(2**n, complex)
    v[0], v[-1] = 1 / np.sqrt(2), np.exp(1j * phase) / np.sqrt(2)
    return Statevector(v)


@pytest.mark.parametrize("n", [2, 3, 5, 7])
def test_a_perfect_ghz_state_has_fidelity_one(n):
    est = _estimate(_ghz(n), n)
    assert est["populations"] == pytest.approx(1, abs=1e-9)
    assert est["coherence"] == pytest.approx(1, abs=1e-9)
    assert est["fidelity"] == pytest.approx(1, abs=1e-9)


def test_the_phase_of_the_coherence_does_not_matter():
    """Fidelity with the GHZ state up to its relative phase: the Fourier magnitude ignores θ."""
    assert _estimate(_ghz(4, 0.7), 4)["coherence"] == pytest.approx(1, abs=1e-9)


def test_a_classical_mixture_has_the_same_histogram_but_no_coherence():
    n = 3
    rho = np.zeros((8, 8))
    rho[0, 0] = rho[7, 7] = 0.5
    est = _estimate(DensityMatrix(rho), n)
    assert est["populations"] == pytest.approx(1, abs=1e-9)
    assert est["coherence"] == pytest.approx(0, abs=1e-9)
    assert est["fidelity"] == pytest.approx(0.5, abs=1e-9)  # not above 1/2: no entanglement certified


def test_matches_the_exact_fidelity_of_a_noisy_ghz_state():
    """GHZ mixed with white noise: F = (1 - p) + p / 2^n exactly; the estimate must agree."""
    n, p = 4, 0.3
    psi = _ghz(n).data
    rho = (1 - p) * np.outer(psi, psi.conj()) + p * np.eye(2**n) / 2**n
    exact = float(np.real(psi.conj() @ rho @ psi))
    assert _estimate(DensityMatrix(rho), n)["fidelity"] == pytest.approx(exact, abs=1e-9)


def test_the_error_bars_match_repeated_sampling():
    """Draw the counts many times from a known noisy GHZ state: the spread of the estimates is the stated error."""
    from inkubit.hardware import hellinger_se
    from inkubit.verify.metrics import hellinger_fidelity

    n, p, shots, reps = 4, 0.25, 4096, 400
    psi = _ghz(n).data
    rho = DensityMatrix((1 - p) * np.outer(psi, psi.conj()) + p * np.eye(2**n) / 2**n)
    rng = np.random.default_rng(3)

    def sample(probs: dict[str, float]) -> dict[str, float]:
        keys = list(probs)
        draw = rng.multinomial(shots, [probs[k] for k in keys])
        return {k: c / shots for k, c in zip(keys, draw)}

    z_exact = _odds(rho, n, None)
    par_exact = [_odds(rho, n, phi) for phi in parity_phases(n)]
    ideal = {"0" * n: 0.5, "1" * n: 0.5}
    fids, hels = [], []
    for _ in range(reps):
        z = sample(z_exact)
        fids.append(ghz_fidelity(z, [parity(sample(q)) for q in par_exact], n)["fidelity"])
        hels.append(hellinger_fidelity(ideal, z))
    stated = ghz_fidelity(z_exact, [parity(q) for q in par_exact], n, shots)["se"]
    assert np.std(fids) == pytest.approx(stated, rel=0.2)
    assert np.std(hels) == pytest.approx(hellinger_se(ideal, z_exact, shots), rel=0.2)
