"""Checking circuits against a real quantum computer: outcome odds, distances, and a GHZ fidelity estimate.

Counts in the computational basis show populations but not coherence: a GHZ state and a 50/50 classical mixture of
all-0 and all-1 give the same Z-basis histogram. The fidelity with (|0…0⟩ + |1…1⟩)/√2 needs the coherence too:

    F = (P(0…0) + P(1…1)) / 2 + |ρ(0…0, 1…1)|.

Measuring every qubit along cos φ X + sin φ Y (RZ(−φ) then H, then Z) gives a parity ⟨⊗⟩ = C cos(nφ − θ) with
C = 2|ρ(0…0, 1…1)|, the parity oscillation. Sampling φ_j = 2πj / (nK) for j = 0..K−1 covers one period of nφ, and the
discrete Fourier component gives C = (2/K) |Σ_j parity_j e^(−2πij/K)| whatever the phase θ. F > 1/2 certifies
genuine n-qubit entanglement. Raw counts are used (no readout correction), so the estimate errs low.
"""

from __future__ import annotations

import cmath
import math
from typing import Any

PHASES = 8


def norm(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    return {k.replace(" ", ""): v / total for k, v in counts.items()}


def tvd(p: dict[str, float], q: dict[str, float]) -> float:
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in set(p) | set(q))


def parity_phases(n: int, k: int = PHASES) -> list[float]:
    return [2 * math.pi * j / (n * k) for j in range(k)]


def append_parity_basis(qc: Any, phi: float) -> None:
    """Rotate every qubit so that measuring Z measures cos φ X + sin φ Y."""
    for q in range(qc.num_qubits):
        qc.rz(-phi, q)
        qc.h(q)


def parity(p: dict[str, float]) -> float:
    return sum(v * (-1) ** k.count("1") for k, v in p.items())


def ghz_fidelity(z: dict[str, float], parities: list[float], n: int, shots: int | None = None) -> dict[str, float]:
    """Populations from the Z-basis odds, coherence from the parity oscillation; see the module docstring.

    With ``shots``, also the standard error from shot noise: binomial for the populations, (1 - parity²)/shots for each
    parity, propagated through the Fourier magnitude (∂|S|/∂parity_j = cos(θ_j + arg S)); the circuits are independent.
    """
    k = len(parities)
    pop = z.get("0" * n, 0.0) + z.get("1" * n, 0.0)
    s = sum(par * cmath.exp(-2j * math.pi * j / k) for j, par in enumerate(parities))
    c = 2 / k * abs(s)
    out = {"populations": pop, "coherence": c, "fidelity": pop / 2 + c / 2}
    if shots:
        arg = cmath.phase(s) if abs(s) > 0 else 0.0
        var_c = (2 / k) ** 2 * sum((1 - par**2) / shots * math.cos(2 * math.pi * j / k + arg) ** 2
                                   for j, par in enumerate(parities))
        out["se"] = math.sqrt(pop * (1 - pop) / shots / 4 + var_c / 4)
    return out


def hellinger_se(ideal: dict[str, float], p: dict[str, float], shots: int) -> float:
    """Shot-noise standard error of the Hellinger fidelity (Σ √(p q))² by the delta method on the multinomial counts."""
    f = sum(math.sqrt(p.get(k, 0.0) * q) for k, q in ideal.items()) ** 2
    g = {k: math.sqrt(f * q / p[k]) for k, q in ideal.items() if p.get(k, 0.0) > 0}
    mean = sum(g[k] * p[k] for k in g)
    return math.sqrt(max(sum(g[k] ** 2 * p[k] for k in g) - mean**2, 0.0) / shots)
