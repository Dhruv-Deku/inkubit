"""Bell tests: can any classical explanation reproduce this circuit's correlations?

Local hidden-variable theories (each qubit carrying a hidden instruction set)
obey Bell inequalities; entangled quantum states can break them. For every
entangled pair, Inkubit computes the CHSH value S under the best measurement
settings (Horodecki criterion: S = 2 sqrt(m1 + m2), with m1, m2 the two largest
eigenvalues of T^T T and T the pair's correlation matrix): classical <= 2,
quantum <= 2 sqrt 2. When exactly three qubits are entangled, it also computes
the Mermin value M (classical <= 2, quantum <= 4) by optimising all six
measurement directions, because a GHZ state breaks Mermin's inequality although
none of its pairs breaks CHSH, and a W state breaks neither pairwise but does as
a trio.

Each value is given for the ideal state; for the noisy state measured with the
settings chosen for the ideal one (what an experimenter would plan); and from
sampled shots with readout error, with a standard error, so the claim "beats
classical physics by N standard deviations" is the one a lab would make.
"""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel
from qiskit.quantum_info import DensityMatrix, partial_trace
from scipy.optimize import minimize

from inkubit.sim.noise import NoisePreset

BELL_SHOTS = 4000
CLASSICAL = 2.0
TSIRELSON = 2 * math.sqrt(2)
MERMIN_MAX = 4.0

_X = np.array([[0, 1], [1, 0]], dtype=complex)
_Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
_Z = np.array([[1, 0], [0, -1]], dtype=complex)
_PAULI = (_X, _Y, _Z)


class BellResult(BaseModel):
    kind: str  # "CHSH" or "Mermin"
    qubits: list[int]
    classical_bound: float
    quantum_bound: float
    ideal: float
    noisy: float | None = None  # exact, noisy state, settings planned for the ideal one
    shots_value: float | None = None
    shots_error: float | None = None  # one standard error
    shots: int = 0
    sigmas: float | None = None  # (shots_value - classical) / shots_error
    settings: list[list[list[float]]]  # per qubit: its two measurement directions [x, y, z]
    violates: bool  # in the ideal state
    verdict: str


class BellTest(BaseModel):
    tests: list[BellResult]
    summary: str


# ---------------------------------------------------------------- correlations

def _reduced(rho: DensityMatrix, keep: list[int], n: int) -> np.ndarray:
    """Reduced density matrix of ``keep`` (ascending) in Qiskit order: the last listed is the leftmost factor."""
    rest = [q for q in range(n) if q not in keep]
    return (partial_trace(rho, rest) if rest else rho).data


def _sigma(v: np.ndarray) -> np.ndarray:
    return v[0] * _X + v[1] * _Y + v[2] * _Z


def _tensor(rho: np.ndarray, k: int) -> np.ndarray:
    """T[i, j, ...] = Tr(rho sigma_i x sigma_j ...), indexed by qubit in ascending order."""
    out = np.zeros((3,) * k)
    for idx in np.ndindex(*out.shape):
        op = np.array([[1.0 + 0j]])
        for i in reversed(idx):  # Qiskit order: qubit 0 is the rightmost factor
            op = np.kron(op, _PAULI[i])
        out[idx] = float(np.trace(rho @ op).real)
    return out


def _unit(v: np.ndarray, fallback: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else fallback


def chsh_settings(t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Optimal CHSH directions (a, a', b, b') for correlation matrix ``t`` (Horodecki construction)."""
    w, v = np.linalg.eigh(t.T @ t)
    order = np.argsort(w)[::-1]
    m1, m2 = max(w[order[0]], 0.0), max(w[order[1]], 0.0)
    c, c2 = v[:, order[0]], v[:, order[1]]
    theta = math.atan2(math.sqrt(m2), math.sqrt(m1))
    b, b2 = math.cos(theta) * c + math.sin(theta) * c2, math.cos(theta) * c - math.sin(theta) * c2
    a, a2 = _unit(t @ c, c), _unit(t @ c2, c2)
    return a, a2, b, b2


def chsh_value(t: np.ndarray, a: np.ndarray, a2: np.ndarray, b: np.ndarray, b2: np.ndarray) -> float:
    """S = E(a,b) + E(a,b') + E(a',b) - E(a',b'), with E(x, y) = x . T y."""
    return float(a @ t @ b + a @ t @ b2 + a2 @ t @ b - a2 @ t @ b2)


def _dir(theta: float, phi: float) -> np.ndarray:
    return np.array([math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), math.cos(theta)])


def mermin_value(t: np.ndarray, a: list[np.ndarray], b: list[np.ndarray]) -> float:
    """M = E(a1 a2 a3) - E(a1 b2 b3) - E(b1 a2 b3) - E(b1 b2 a3)."""
    e = lambda x, y, z: float(np.einsum("ijk,i,j,k->", t, x, y, z))  # noqa: E731
    return e(a[0], a[1], a[2]) - e(a[0], b[1], b[2]) - e(b[0], a[1], b[2]) - e(b[0], b[1], a[2])


def mermin_settings(t: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Directions maximising M, found by local optimisation from fixed starting points."""
    def unpack(x: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray]]:
        return ([_dir(x[4 * k], x[4 * k + 1]) for k in range(3)], [_dir(x[4 * k + 2], x[4 * k + 3]) for k in range(3)])

    rng = np.random.default_rng(7)
    starts = [np.array([math.pi / 2, 0, math.pi / 2, math.pi / 2] * 3)]  # X and Y on every qubit (GHZ)
    starts += [np.array([math.pi / 2, 0, 0, 0] * 3)]  # X and Z
    starts += [rng.uniform(0, math.pi, 12) for _ in range(14)]
    best_x, best = starts[0], -np.inf
    for x0 in starts:
        res = minimize(lambda x: -mermin_value(t, *unpack(x)), x0, method="BFGS")
        if -res.fun > best + 1e-9:
            best, best_x = -res.fun, res.x
    return unpack(best_x)


# ---------------------------------------------------------------- shots

def _outcome_probs(rho: np.ndarray, dirs: list[np.ndarray], p01: float, p10: float) -> np.ndarray:
    """P(outcome string) for measuring qubit k along dirs[k]; outcome bit 0 means +1. Readout error included."""
    k = len(dirs)
    probs = np.zeros(2 ** k)
    projs = [[(np.eye(2) + s * _sigma(d)) / 2 for s in (1, -1)] for d in dirs]
    for idx in range(2 ** k):
        bits = [(idx >> j) & 1 for j in range(k)]  # bit j belongs to qubit j (ascending)
        op = np.array([[1.0 + 0j]])
        for j in reversed(range(k)):
            op = np.kron(op, projs[j][bits[j]])
        probs[idx] = max(float(np.trace(rho @ op).real), 0.0)
    flip = np.array([[1 - p01, p01], [p10, 1 - p10]])  # flip[true][read]
    for j in range(k):  # each qubit's readout error, one at a time
        out = np.zeros_like(probs)
        for idx in range(2 ** k):
            true = (idx >> j) & 1
            for read in (0, 1):
                out[(idx & ~(1 << j)) | (read << j)] += probs[idx] * flip[true][read]
        probs = out
    return probs / probs.sum()


def _sampled_correlator(rho: np.ndarray, dirs: list[np.ndarray], preset: NoisePreset,
                        rng: np.random.Generator, shots: int) -> float:
    p = _outcome_probs(rho, dirs, preset.readout_p01, preset.readout_p10)
    counts = rng.multinomial(shots, p)
    signs = np.array([(-1) ** bin(i).count("1") for i in range(len(p))])
    return float((signs * counts).sum() / shots)


def _shots(rho: np.ndarray, terms: list[tuple[float, list[np.ndarray]]], preset: NoisePreset,
           rng: np.random.Generator, shots: int) -> tuple[float, float]:
    """Estimate sum(coef * E(dirs)) from ``shots`` shots per term, with its standard error."""
    value, var = 0.0, 0.0
    for coef, dirs in terms:
        e = _sampled_correlator(rho, dirs, preset, rng, shots)
        value += coef * e
        var += (1 - e * e) / shots
    return value, math.sqrt(var)


# ---------------------------------------------------------------- the tests

def _verdict(kind: str, ideal: float, noisy: float | None, sigmas: float | None, bound: float) -> str:
    if ideal <= CLASSICAL + 1e-6:
        return (f"Entangled, yet its best {kind} value {ideal:.3f} stays within the classical bound {CLASSICAL:g}: "
                "a hidden-variable model could fake these correlations.")
    text = f"Ideal {kind} value {ideal:.3f} > {CLASSICAL:g}: no local hidden-variable model can reproduce it"
    if noisy is not None:
        text += (f"; with realistic noise {noisy:.3f}" + (" still breaks the bound" if noisy > CLASSICAL
                                                         else ", no longer above the classical bound"))
    if sigmas is not None and noisy is not None:
        text += (f", by {sigmas:.0f} standard errors over {BELL_SHOTS:,} shots per setting" if sigmas > 3
                 else f" ({sigmas:.1f} standard errors over {BELL_SHOTS:,} shots per setting: not conclusive)")
    return text + "."


def bell_tests(psi: np.ndarray, n: int, pairs: list[tuple[int, int]], tangled: list[int],
               rho_noisy: DensityMatrix | None, preset: NoisePreset) -> BellTest | None:
    """CHSH for each entangled pair; Mermin when exactly three qubits are entangled."""
    if not pairs and len(tangled) != 3:
        return None
    ideal_rho = DensityMatrix(psi)
    rng = np.random.default_rng(2026)
    tests: list[BellResult] = []
    for a, b in pairs:
        t = _tensor(_reduced(ideal_rho, [a, b], n), 2)
        sa, sa2, sb, sb2 = chsh_settings(t)
        ideal = chsh_value(t, sa, sa2, sb, sb2)
        noisy = value = err = sig = None
        if rho_noisy is not None:
            rn = _reduced(rho_noisy, [a, b], n)
            noisy = chsh_value(_tensor(rn, 2), sa, sa2, sb, sb2)
            terms = [(1, [sa, sb]), (1, [sa, sb2]), (1, [sa2, sb]), (-1, [sa2, sb2])]
            value, err = _shots(rn, terms, preset, rng, BELL_SHOTS)
            sig = (value - CLASSICAL) / err if err > 0 else None
        tests.append(BellResult(
            kind="CHSH", qubits=[a, b], classical_bound=CLASSICAL, quantum_bound=round(TSIRELSON, 6),
            ideal=round(ideal, 6), noisy=None if noisy is None else round(noisy, 6),
            shots_value=None if value is None else round(value, 6), shots_error=None if err is None else round(err, 6),
            shots=BELL_SHOTS if value is not None else 0, sigmas=None if sig is None else round(sig, 2),
            settings=[[sa.round(4).tolist(), sa2.round(4).tolist()], [sb.round(4).tolist(), sb2.round(4).tolist()]],
            violates=ideal > CLASSICAL + 1e-6, verdict=_verdict("CHSH", ideal, noisy, sig, TSIRELSON)))
    if len(tangled) == 3:
        qs = sorted(tangled)
        t = _tensor(_reduced(ideal_rho, qs, n), 3)
        A, B = mermin_settings(t)
        ideal = mermin_value(t, A, B)
        noisy = value = err = sig = None
        if rho_noisy is not None:
            rn = _reduced(rho_noisy, qs, n)
            noisy = mermin_value(_tensor(rn, 3), A, B)
            terms = [(1, [A[0], A[1], A[2]]), (-1, [A[0], B[1], B[2]]), (-1, [B[0], A[1], B[2]]),
                     (-1, [B[0], B[1], A[2]])]
            value, err = _shots(rn, terms, preset, rng, BELL_SHOTS)
            sig = (value - CLASSICAL) / err if err > 0 else None
        tests.append(BellResult(
            kind="Mermin", qubits=qs, classical_bound=CLASSICAL, quantum_bound=MERMIN_MAX,
            ideal=round(ideal, 6), noisy=None if noisy is None else round(noisy, 6),
            shots_value=None if value is None else round(value, 6), shots_error=None if err is None else round(err, 6),
            shots=BELL_SHOTS if value is not None else 0, sigmas=None if sig is None else round(sig, 2),
            settings=[[A[k].round(4).tolist(), B[k].round(4).tolist()] for k in range(3)],
            violates=ideal > CLASSICAL + 1e-6, verdict=_verdict("Mermin", ideal, noisy, sig, MERMIN_MAX)))
    if not tests:
        return None
    return BellTest(tests=tests, summary=_summary(tests))


def _summary(tests: list[BellResult]) -> str:
    beat = [t for t in tests if t.violates]
    if not beat:
        return ("The entanglement here is real but too weak or too spread out to break a Bell inequality: "
                "a classical hidden-variable model could reproduce every correlation.")
    best = max(beat, key=lambda t: t.ideal / t.classical_bound)
    who = "q" + " and q".join(str(q) for q in best.qubits) if best.kind == "CHSH" else \
        ", ".join(f"q{q}" for q in best.qubits)
    text = (f"{who} break the {best.kind} inequality: {best.ideal:.3f} against a classical limit of "
            f"{best.classical_bound:g} (quantum maximum {best.quantum_bound:.3f}). No theory where each qubit "
            f"carries its answers in advance can explain that.")
    if best.noisy is not None and best.sigmas is not None:
        text += (f" On realistic hardware the same test gives {best.shots_value:.3f} ± {best.shots_error:.3f}"
                 + (f", {best.sigmas:.0f} standard errors above classical." if best.sigmas > 3
                    else ", too close to classical to be conclusive."))
    pair_fail = [t for t in tests if t.kind == "CHSH" and not t.violates]
    trio = next((t for t in tests if t.kind == "Mermin" and t.violates), None)
    if trio and (pair_fail or not any(t.kind == "CHSH" for t in tests)):
        text += " No pair beats classical physics on its own; only the three together do."
    return text
