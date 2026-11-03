"""Structured pass/fail verdicts comparing measured counts with the spec."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from qcanvas.sim.noise import get_preset
from qcanvas.spec.models import CircuitSpec
from qcanvas.verify.expected import Distribution, ideal_distribution, noisy_distribution
from qcanvas.verify.metrics import (
    counts_to_probs,
    hellinger_fidelity,
    shot_noise_tvd_bound,
    total_variation_distance,
)


@dataclass(frozen=True)
class Thresholds:
    """Per-preset floors (see DECISIONS.md D8 for the reasoning)."""

    tvd_floor: float
    min_fidelity: float


THRESHOLDS: dict[str, Thresholds] = {
    "ideal": Thresholds(tvd_floor=0.02, min_fidelity=0.99),
    "low_noise": Thresholds(tvd_floor=0.03, min_fidelity=0.985),
    "realistic": Thresholds(tvd_floor=0.04, min_fidelity=0.98),
    "calibrated": Thresholds(tvd_floor=0.03, min_fidelity=0.985),  # today's chips: between low_noise and realistic
}


class Deviation(BaseModel):
    """One outcome where measured and expected differ."""

    outcome: str
    expected: float
    measured: float
    delta: float


class Metrics(BaseModel):
    """Numbers behind a verdict."""

    shots: int
    tvd: float
    fidelity: float
    tvd_threshold: float
    fidelity_threshold: float
    tvd_vs_ideal: float
    fidelity_vs_ideal: float


class Verdict(BaseModel):
    """Result of verifying one run against the spec."""

    passed: bool
    noise: str
    metrics: Metrics
    expected: Distribution  # noise-aware, exact
    ideal: Distribution
    measured: Distribution
    deviations: list[Deviation]
    reason: str


def _pct(p: float) -> str:
    return f"{round(p * 100)}%"


def describe(dist: Distribution, min_p: float = 0.05, limit: int = 4) -> str:
    """'~50% |00> and ~50% |11>' style summary of the main outcomes."""
    top = sorted(((k, v) for k, v in dist.items() if v >= min_p), key=lambda kv: -kv[1])[:limit]
    if not top:
        return "no dominant outcome"
    parts = [f"{_pct(v)} |{k}⟩" for k, v in top]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def verify_counts(spec: CircuitSpec, counts: dict[str, int], noise: str = "ideal") -> Verdict:
    """Compare measured counts with the exact noise-aware expectation for ``spec``."""
    get_preset(noise)
    shots = sum(counts.values())
    measured = counts_to_probs(counts)
    expected = noisy_distribution(spec, noise)
    ideal = ideal_distribution(spec)
    th = THRESHOLDS[noise]
    tvd = total_variation_distance(measured, expected)
    fid = hellinger_fidelity(measured, expected)
    tvd_limit = max(th.tvd_floor, shot_noise_tvd_bound(expected, shots))
    passed = shots > 0 and tvd <= tvd_limit and fid >= th.min_fidelity

    keys = set(measured) | set(expected)
    devs = sorted(
        (Deviation(outcome=k, expected=expected.get(k, 0.0), measured=measured.get(k, 0.0),
                   delta=measured.get(k, 0.0) - expected.get(k, 0.0)) for k in keys),
        key=lambda d: -abs(d.delta),
    )[:4]

    metrics = Metrics(
        shots=shots, tvd=tvd, fidelity=fid, tvd_threshold=tvd_limit, fidelity_threshold=th.min_fidelity,
        tvd_vs_ideal=total_variation_distance(measured, ideal),
        fidelity_vs_ideal=hellinger_fidelity(measured, ideal),
    )
    if shots == 0:
        reason = "The run produced no measurement counts."
    elif passed:
        reason = (f"Matches the spec: measured {describe(measured)}; distance {tvd:.3f} is within "
                  f"the {tvd_limit:.3f} allowed for {shots} shots under '{noise}' noise.")
    else:
        reason = (f"Expected ~{describe(ideal)}, got {describe(measured)} "
                  f"(distance {tvd:.3f}, allowed {tvd_limit:.3f}).")
    return Verdict(passed=passed, noise=noise, metrics=metrics, expected=expected, ideal=ideal,
                   measured=measured, deviations=devs, reason=reason)
