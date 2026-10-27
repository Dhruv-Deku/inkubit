"""Distribution distances and the shot-noise bound used for thresholds."""

from __future__ import annotations

import math

Distribution = dict[str, float]


def counts_to_probs(counts: dict[str, int]) -> Distribution:
    """Normalise raw counts to probabilities."""
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in counts.items() if v > 0}


def total_variation_distance(p: Distribution, q: Distribution) -> float:
    """TVD = 1/2 * sum |p_i - q_i|, in [0, 1]."""
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys)


def hellinger_fidelity(p: Distribution, q: Distribution) -> float:
    """Hellinger fidelity (sum sqrt(p_i q_i))^2, in [0, 1]; same definition as Qiskit's."""
    bc = sum(math.sqrt(p.get(k, 0.0) * q.get(k, 0.0)) for k in set(p) & set(q))
    return min(1.0, bc * bc)


def shot_noise_tvd_bound(expected: Distribution, shots: int, sigmas: float = 3.0) -> float:
    """Conservative TVD that pure sampling noise stays under.

    Each outcome's empirical frequency has standard deviation sqrt(p(1-p)/N);
    allowing ``sigmas`` of them on every outcome at once gives
    TVD <= sigmas/2 * sum_i sqrt(p_i (1 - p_i) / N).
    """
    if shots <= 0:
        return 1.0
    return sigmas * 0.5 * sum(math.sqrt(p * (1 - p) / shots) for p in expected.values())
