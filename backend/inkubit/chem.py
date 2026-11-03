"""The hydrogen molecule from first principles, and VQE finding its energy.

Integrals: the minimal STO-3G basis (one contracted s function per atom, exponents 3.42525, 0.623913, 0.168856 and
coefficients 0.154329, 0.535328, 0.444635), with the closed-form Gaussian integrals (overlap, kinetic, nuclear
attraction through the Boys function, electron repulsion) as in Szabo and Ostlund, Modern Quantum Chemistry, ch. 3.
By symmetry the molecular orbitals are sigma_g = (a + b)/sqrt(2(1 + S)) and sigma_u = (a - b)/sqrt(2(1 - S)).

Two electrons in a singlet ground state leave two configurations, both electrons in sigma_g or both in sigma_u, so
the exact (full CI) energy is the lower eigenvalue of a 2x2 matrix, and the problem is one qubit: |0> = sigma_g^2,
|1> = sigma_u^2, H = a I + b Z + c X. Hartree-Fock keeps only |0>, which is why it fails as the bond stretches: there
the true state is an even mix (the electrons are correlated, one on each atom). VQE prepares RY(theta)|0>, measures Z
directly and X after an H gate, and a classical optimizer tunes theta; with noise, each expectation comes from the
realistic preset's density-matrix simulation and shot noise is added from a seeded sample.

Checks in the tests: Hartree-Fock -1.1167 Ha at 1.4 bohr (Szabo and Ostlund), full CI -1.1373 Ha, and the
dissociation limit, two STO-3G hydrogen atoms, 2 x -0.46658 Ha.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import numpy as np
from pydantic import BaseModel
from scipy.special import erf

from inkubit.sim.noise import get_preset
from inkubit.spec import parse_spec
from inkubit.verify.expected import noisy_distribution

BOHR = 0.529177210903  # angstrom
HARTREE_EV = 27.211386
CHEM_ACC = 0.0016  # Ha, "chemical accuracy" (1 kcal/mol)
ALPHA = (3.42525091, 0.62391373, 0.16885540)
COEF = (0.15432897, 0.53532814, 0.44463454)
SHOTS = 4000


def _boys0(t: float) -> float:
    return 1.0 if t < 1e-10 else 0.5 * math.sqrt(math.pi / t) * erf(math.sqrt(t))


def _norm(a: float) -> float:
    return (2 * a / math.pi) ** 0.75


def _prims(center: float) -> list[tuple[float, float, float]]:
    return [(a, c * _norm(a), center) for a, c in zip(ALPHA, COEF)]


def _s(a, A, b, B):
    p = a + b
    return (math.pi / p) ** 1.5 * math.exp(-a * b / p * (A - B) ** 2)


def _t(a, A, b, B):
    p, r2 = a + b, (A - B) ** 2
    return a * b / p * (3 - 2 * a * b / p * r2) * (math.pi / p) ** 1.5 * math.exp(-a * b / p * r2)


def _v(a, A, b, B, C, Z=1.0):
    p = a + b
    P = (a * A + b * B) / p
    return -2 * math.pi / p * Z * math.exp(-a * b / p * (A - B) ** 2) * _boys0(p * (P - C) ** 2)


def _eri(a, A, b, B, c, C, d, D):
    p, q = a + b, c + d
    P, Q = (a * A + b * B) / p, (c * C + d * D) / q
    pre = 2 * math.pi ** 2.5 / (p * q * math.sqrt(p + q))
    return pre * math.exp(-a * b / p * (A - B) ** 2 - c * d / q * (C - D) ** 2) * _boys0(p * q / (p + q) * (P - Q) ** 2)


@lru_cache(maxsize=512)
def integrals(r: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Overlap S, core Hamiltonian h and electron repulsion (ij|kl) in the atomic basis, nuclei at 0 and r (bohr)."""
    basis = [_prims(0.0), _prims(r)]
    S, h = np.zeros((2, 2)), np.zeros((2, 2))
    for i in range(2):
        for j in range(2):
            for a, ca, A in basis[i]:
                for b, cb, B in basis[j]:
                    S[i, j] += ca * cb * _s(a, A, b, B)
                    h[i, j] += ca * cb * (_t(a, A, b, B) + _v(a, A, b, B, 0.0) + _v(a, A, b, B, r))
    g = np.zeros((2, 2, 2, 2))
    for i in range(2):
        for j in range(2):
            for k in range(2):
                for l in range(2):
                    g[i, j, k, l] = sum(ca * cb * cc * cd * _eri(a, A, b, B, c, C, d, D)
                                        for a, ca, A in basis[i] for b, cb, B in basis[j]
                                        for c, cc, C in basis[k] for d, cd, D in basis[l])
    return S, h, g


class Pauli(BaseModel):
    """The one-qubit Hamiltonian H = a I + b Z + c X (Hartree), nuclear repulsion included in a."""

    a: float
    b: float
    c: float


@lru_cache(maxsize=512)
def hamiltonian(r: float) -> Pauli:
    S, h, g = integrals(r)
    s = S[0, 1]
    C = np.array([[1, 1], [1, -1]], dtype=float) / np.sqrt([2 * (1 + s), 2 * (1 - s)])  # columns: sigma_g, sigma_u
    hm = C.T @ h @ C
    gm = np.einsum("pi,qj,rk,sl,pqrs->ijkl", C, C, C, C, g)
    e_g = 2 * hm[0, 0] + gm[0, 0, 0, 0]
    e_u = 2 * hm[1, 1] + gm[1, 1, 1, 1]
    k = gm[0, 1, 0, 1]
    nuc = 1.0 / r
    return Pauli(a=(e_g + e_u) / 2 + nuc, b=(e_g - e_u) / 2, c=k)


def energy_hf(r: float) -> float:
    H = hamiltonian(r)
    return H.a + H.b


def energy_exact(r: float) -> float:
    H = hamiltonian(r)
    return H.a - math.hypot(H.b, H.c)


def best_theta(r: float) -> float:
    """The angle where a + b cos(theta) + c sin(theta) is lowest."""
    H = hamiltonian(r)
    return math.atan2(-H.c, -H.b)


def vqe_spec(theta: float, basis: str = "Z") -> dict[str, Any]:
    ops: list[dict[str, Any]] = [{"gate": "RY", "targets": [0], "params": [round(theta, 6)]}]
    if basis == "X":
        ops.append({"gate": "H", "targets": [0]})
    return {"kind": "circuit", "version": "1.0", "num_qubits": 1, "num_clbits": 1, "operations": ops,
            "measurements": [{"qubit": 0, "clbit": 0}],
            "metadata": {"title": f"H₂ VQE, measuring {basis}", "origin": "manual",
                         "notes": ("|0> is both electrons in the bonding orbital, |1> both in the antibonding one. "
                                   f"RY({theta:.3f}) mixes them; this circuit measures {basis} for the energy "
                                   "a + b<Z> + c<X>.")}}


def _simulate(theta: float, basis: str, noise: str) -> float:
    d = noisy_distribution(parse_spec(vqe_spec(theta, basis)), noise)
    return d.get("0", 0.0) - d.get("1", 0.0)


@lru_cache(maxsize=16)
def _noise_map(basis: str, noise: str) -> tuple[float, float, float]:
    """A noise channel that does not depend on the angle acts on the Bloch vector (sin t, 0, cos t) as an affine map,
    so the noisy expectation is A + B cos t + C sin t: three simulations fix it (the tests check it against a direct
    simulation at other angles)."""
    e0, epi, e90 = (_simulate(t, basis, noise) for t in (0.0, math.pi, math.pi / 2))
    return (e0 + epi) / 2, (e0 - epi) / 2, e90 - (e0 + epi) / 2


def _expect(theta: float, basis: str, noise: str) -> float:
    if noise == "ideal":
        return math.cos(theta) if basis == "Z" else math.sin(theta)
    a, b, c = _noise_map(basis, noise)
    return a + b * math.cos(theta) + c * math.sin(theta)


def vqe_energy(r: float, theta: float, noise: str = "realistic", shots: int | None = SHOTS,
               rng: np.random.Generator | None = None, mitigate: bool = False) -> tuple[float, float]:
    """Energy estimate and its one-sigma shot error at ``theta`` (exact expectation when shots is None).

    ``mitigate`` undoes the calibrated noise map (what calibration circuits measure on hardware: prepare the known
    states, see how they read, invert), which rescales the shot error by the map's slope."""
    H = hamiltonian(r)
    z, x = _expect(theta, "Z", noise), _expect(theta, "X", noise)
    if shots is not None:
        rng = rng or np.random.default_rng(0)
        z = 2 * rng.binomial(shots, (1 + z) / 2) / shots - 1
        x = 2 * rng.binomial(shots, (1 + x) / 2) / shots - 1
    sz = sx = 1.0
    if mitigate and noise != "ideal":
        az, bz, _ = _noise_map("Z", noise)
        ax, _, cx = _noise_map("X", noise)
        z, x, sz, sx = (z - az) / bz, (x - ax) / cx, abs(bz), abs(cx)
    if shots is None:
        return H.a + H.b * z + H.c * x, 0.0
    var_z = max(0.0, 1 - (z * sz) ** 2) / shots / sz ** 2
    var_x = max(0.0, 1 - (x * sx) ** 2) / shots / sx ** 2
    return H.a + H.b * z + H.c * x, math.sqrt(H.b ** 2 * var_z + H.c ** 2 * var_x)


class CurvePoint(BaseModel):
    r: float  # angstrom
    hf: float
    exact: float
    vqe: float
    vqe_err: float
    mitigated: float
    mitigated_err: float
    weight_u: float  # share of the sigma_u^2 configuration in the exact state


class ScanPoint(BaseModel):
    theta: float
    exact: float  # energy at theta, perfect qubits
    noisy: float  # with the noise preset, exact expectation
    shots: float | None = None
    err: float | None = None


class ChemLab(BaseModel):
    r: float
    hamiltonian: Pauli
    hf: float
    exact: float
    vqe: float
    vqe_err: float
    mitigated: float
    mitigated_err: float
    theta: float
    weight_u: float
    correlation: float  # exact - hf
    curve: list[CurvePoint]
    scan: list[ScanPoint]
    atoms: float  # dissociation limit
    noise: str
    noise_label: str
    shots: int
    spec: dict[str, Any]
    summary: str


def _weight_u(theta: float) -> float:
    return math.sin(theta / 2) ** 2


@lru_cache(maxsize=4)
def _curve(noise: str) -> list[CurvePoint]:
    rng = np.random.default_rng(2026)
    out = []
    for ang in np.round(np.arange(0.3, 3.01, 0.1), 2):
        r = float(ang) / BOHR
        th = best_theta(r)
        e, err = vqe_energy(r, th, noise, SHOTS, rng)
        m, merr = vqe_energy(r, th, noise, SHOTS, rng, mitigate=True)
        out.append(CurvePoint(r=float(ang), hf=energy_hf(r), exact=energy_exact(r), vqe=e, vqe_err=err,
                              mitigated=m, mitigated_err=merr, weight_u=_weight_u(th)))
    return out


@lru_cache(maxsize=64)
def chem_lab(r_angstrom: float, noise: str = "realistic") -> ChemLab:
    if not 0.25 <= r_angstrom <= 3.5:
        raise ValueError("bond length must be between 0.25 and 3.5 angstrom")
    r = r_angstrom / BOHR
    th = best_theta(r)
    rng = np.random.default_rng(int(r_angstrom * 1000))
    e, err = vqe_energy(r, th, noise, SHOTS, rng)
    m, merr = vqe_energy(r, th, noise, SHOTS, rng, mitigate=True)
    scan = []
    for t in np.linspace(-math.pi, math.pi, 41):
        ex, _ = vqe_energy(r, float(t), "ideal", None)
        nz, _ = vqe_energy(r, float(t), noise, None)
        scan.append(ScanPoint(theta=float(t), exact=ex, noisy=nz))
    for t in np.linspace(-math.pi, math.pi, 9)[:-1]:  # what a few real runs would read
        s, se = vqe_energy(r, float(t), noise, SHOTS, rng)
        scan.append(ScanPoint(theta=float(t), exact=vqe_energy(r, float(t), "ideal", None)[0],
                              noisy=vqe_energy(r, float(t), noise, None)[0], shots=s, err=se))
    preset = get_preset(noise)
    lab = ChemLab(r=r_angstrom, hamiltonian=hamiltonian(r), hf=energy_hf(r), exact=energy_exact(r), vqe=e, vqe_err=err,
                  mitigated=m, mitigated_err=merr, theta=th, weight_u=_weight_u(th), correlation=energy_exact(r) - energy_hf(r), curve=_curve(noise),
                  scan=sorted(scan, key=lambda p: p.theta), atoms=energy_exact(40.0), noise=noise,
                  noise_label=preset.label, shots=SHOTS, spec=vqe_spec(th, "X"), summary="")
    lab.summary = _summary(lab)
    return lab


def _summary(lab: ChemLab) -> str:
    miss = (lab.hf - lab.exact)
    err = abs(lab.vqe - lab.exact)
    text = (f"At {lab.r:.2f} Å the exact energy is {lab.exact:.4f} Ha. Hartree-Fock, which keeps both electrons in "
            f"the bonding orbital, gives {lab.hf:.4f} Ha, {miss * 1000:.1f} mHa too high "
            f"({miss * HARTREE_EV:.2f} eV). The true state is {100 * (1 - lab.weight_u):.0f}% bonding and "
            f"{100 * lab.weight_u:.0f}% antibonding")
    text += (": stretched this far the electrons sit one on each atom, which a single configuration cannot say. "
             if lab.weight_u > 0.25 else ". ")
    merr = abs(lab.mitigated - lab.exact)
    worse = " (worse than Hartree-Fock: the noise ate the gain)" if lab.vqe > lab.hf else ""
    text += (f"VQE with {lab.noise_label.lower()} noise and {lab.shots:,} shots per term reads {lab.vqe:.4f} ± "
             f"{lab.vqe_err:.4f} Ha, {err * 1000:.1f} mHa off{worse}; undoing the calibrated noise brings it to "
             f"{lab.mitigated:.4f} ± {lab.mitigated_err:.4f} Ha, {merr * 1000:.1f} mHa off. Chemical accuracy is "
             "1.6 mHa. ")
    return text + ("For H₂ in a minimal basis a laptop solves this exactly; the point is the method, which scales to "
                   "molecules a laptop cannot.")
