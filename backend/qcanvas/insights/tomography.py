"""State tomography: rebuild the quantum state from measurements alone, as a lab has to.

A quantum state cannot be read out: every shot gives one bitstring. Tomography
measures each qubit along X, Y or Z in all 3^n combinations, undoes the known
readout error on each setting's counts, estimates every Pauli expectation, and
inverts them into a density matrix. Shot noise can leave that matrix slightly
unphysical (a negative eigenvalue), so it is projected onto the closest physical
state with the fast maximum-likelihood method of Smolin, Gambetta and Smith
(Phys. Rev. Lett. 108, 070502, 2012). Up to three qubits (27 settings).

The state measured is the noisy state just before the final measurement, from
the same channels as everything else; the settings' basis rotations are taken
as perfect (single-qubit gates are the cheapest by far).
"""

from __future__ import annotations

import itertools

import numpy as np
from pydantic import BaseModel
from qiskit.quantum_info import DensityMatrix, state_fidelity

from qcanvas.insights.bell import _outcome_probs
from qcanvas.sim.noise import NoisePreset

MAX_TOMO_QUBITS = 3
TOMO_SHOTS = 1000  # per setting

_AXES = {"X": np.array([1.0, 0, 0]), "Y": np.array([0, 1.0, 0]), "Z": np.array([0, 0, 1.0])}
_MATS = {"I": np.eye(2, dtype=complex), "X": np.array([[0, 1], [1, 0]], dtype=complex),
         "Y": np.array([[0, -1j], [1j, 0]], dtype=complex), "Z": np.array([[1, 0], [0, -1]], dtype=complex)}


class Tomography(BaseModel):
    n: int
    settings: int
    shots_per_setting: int
    ideal_re: list[list[float]]
    ideal_im: list[list[float]]
    recon_re: list[list[float]]
    recon_im: list[list[float]]
    fidelity_ideal: float  # <psi| rho_reconstructed |psi>
    fidelity_noisy: float  # Uhlmann fidelity with the exact noisy state
    noisy_fidelity_ideal: float  # <psi| rho_noisy |psi>: what perfect tomography would find
    purity: float  # Tr(rho^2) of the reconstruction; 1 for a pure state
    summary: str


def _uncorrect_readout(freq: np.ndarray, k: int, p01: float, p10: float) -> np.ndarray:
    """Invert each qubit's readout confusion on an outcome-frequency vector (bit j = qubit j, 0 means +1)."""
    if not (p01 or p10):
        return freq
    det = (1 - p01) * (1 - p10) - p01 * p10
    inv = [[(1 - p10) / det, -p10 / det], [-p01 / det, (1 - p01) / det]]  # inv[true][read]
    out = freq.astype(float)
    for j in range(k):
        nxt = np.zeros_like(out)
        for idx in range(2 ** k):
            read = (idx >> j) & 1
            for true in (0, 1):
                nxt[(idx & ~(1 << j)) | (true << j)] += out[idx] * inv[true][read]
        out = nxt
    return out


def _physical(rho: np.ndarray) -> np.ndarray:
    """Closest density matrix with non-negative eigenvalues (Smolin-Gambetta-Smith)."""
    vals, vecs = np.linalg.eigh((rho + rho.conj().T) / 2)
    vals, vecs = vals[::-1].copy(), vecs[:, ::-1]
    acc, i = 0.0, len(vals)
    while i > 0 and vals[i - 1] + acc / i < 0:
        acc += vals[i - 1]
        vals[i - 1] = 0.0
        i -= 1
    vals[:i] += acc / i
    return (vecs * vals) @ vecs.conj().T


def _rows(m: np.ndarray) -> list[list[float]]:
    return [[round(float(v), 5) for v in row] for row in m]


def tomography(psi: np.ndarray, rho_noisy: DensityMatrix | None, preset: NoisePreset,
               seed: int = 99) -> Tomography | None:
    """Simulated state tomography of the circuit's state before measurement (n <= 3)."""
    n = int(round(np.log2(len(psi))))
    if n > MAX_TOMO_QUBITS:
        return None
    rho_true = rho_noisy.data if rho_noisy is not None else np.outer(psi, psi.conj())
    rng = np.random.default_rng(seed)
    freqs: dict[tuple[str, ...], np.ndarray] = {}
    for setting in itertools.product("XYZ", repeat=n):  # setting[j] is qubit j's axis
        p = _outcome_probs(rho_true, [_AXES[a] for a in setting], preset.readout_p01, preset.readout_p10)
        counts = rng.multinomial(TOMO_SHOTS, p)
        freqs[setting] = _uncorrect_readout(counts / TOMO_SHOTS, n, preset.readout_p01, preset.readout_p10)
    dim = 2 ** n
    rho = np.zeros((dim, dim), dtype=complex)
    for pauli in itertools.product("IXYZ", repeat=n):  # pauli[j] acts on qubit j
        support = [j for j in range(n) if pauli[j] != "I"]
        matches = [s for s in freqs if all(s[j] == pauli[j] for j in support)]
        signs = np.array([(-1) ** sum((idx >> j) & 1 for j in support) for idx in range(dim)])
        expect = float(np.mean([signs @ freqs[s] for s in matches]))
        op = np.array([[1.0 + 0j]])
        for j in reversed(range(n)):  # Qiskit order: qubit 0 is the rightmost factor
            op = np.kron(op, _MATS[pauli[j]])
        rho += expect * op / dim
    rec = _physical(rho)
    ideal = np.outer(psi, psi.conj())
    f_ideal = float(np.real(psi.conj() @ rec @ psi))
    f_noisy = float(state_fidelity(DensityMatrix(rec), DensityMatrix(rho_true), validate=False))
    f_perfect = float(np.real(psi.conj() @ rho_true @ psi))
    purity = float(np.real(np.trace(rec @ rec)))
    settings = 3 ** n
    summary = (f"Rebuilt from {settings * TOMO_SHOTS:,} shots in {settings} measurement settings, the way a lab "
               f"must (a state can't be read directly): fidelity {f_ideal:.3f} with the intended state. Perfect "
               f"tomography of the noisy state would find {f_perfect:.3f}: {1 - f_perfect:.3f} is lost to hardware "
               f"noise and the remaining {abs(f_perfect - f_ideal):.3f} is the uncertainty of finite shots. "
               f"Purity {purity:.3f} (1 means pure; noise mixes the state).")
    return Tomography(n=n, settings=settings, shots_per_setting=TOMO_SHOTS,
                      ideal_re=_rows(ideal.real), ideal_im=_rows(ideal.imag),
                      recon_re=_rows(rec.real), recon_im=_rows(rec.imag),
                      fidelity_ideal=round(f_ideal, 6), fidelity_noisy=round(f_noisy, 6),
                      noisy_fidelity_ideal=round(f_perfect, 6), purity=round(purity, 6), summary=summary)
