"""Shor's algorithm for N = 15, end to end: circuit, exact odds and the classical finish.

Three counting qubits (q0 controls a^1, q1 a^2, q2 a^4) and four work qubits
(q3 is the lowest bit) that start in |1>. Multiplying by a mod 15 permutes the
work register's values 1..14: by 2, 4 or 8 it rotates the four bits (16 = 1
mod 15), and by -1 it flips all of them (15 - x is the bitwise complement), so
every a coprime to 15 needs only controlled swaps (two CNOTs and a Toffoli
each) and CNOTs. a^4 = 1 mod 15 for every such a, so q2's multiplication is
the identity and is left out. An inverse QFT turns the period into the phase
y/8 read from the counting qubits; a continued fraction turns the phase into a
period r, and gcd(a^(r/2) +- 1, 15) gives the factors.

Everything here is exact (Statevector and density matrices); the shots are
sampled with a fixed seed. Tests check each multiplier against x -> a*x mod 15.
"""

from __future__ import annotations

import math
from fractions import Fraction
from functools import lru_cache
from typing import Any

import numpy as np
from pydantic import BaseModel

from qcanvas.sim.noise import get_preset
from qcanvas.spec import parse_spec
from qcanvas.spec.models import CircuitSpec
from qcanvas.verify.expected import Distribution, ideal_distribution, noisy_distribution

N = 15
COUNTING = 3
WORK = tuple(range(COUNTING, COUNTING + 4))
COPRIME = tuple(a for a in range(2, N) if math.gcd(a, N) == 1)  # 2, 4, 7, 8, 11, 13, 14
LAB_SHOTS = 1000

# Bit swaps that multiply the 4-bit work register by 2, 4 or 8 mod 15 (bit k is qubit WORK[k]),
# applied in this order; a negative multiplier also flips every bit.
_ROTATE = {1: [], 2: [(2, 3), (1, 2), (0, 1)], 4: [(0, 2), (1, 3)], 8: [(0, 1), (1, 2), (2, 3)]}
_SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
_IQFT = [  # inverse QFT on q0..q2, as in the phase estimation example
    {"gate": "SWAP", "targets": [0, 2]},
    {"gate": "H", "targets": [0]},
    {"gate": "CP", "targets": [1], "controls": [0], "params": [-math.pi / 2]},
    {"gate": "H", "targets": [1]},
    {"gate": "CP", "targets": [2], "controls": [0], "params": [-math.pi / 4]},
    {"gate": "CP", "targets": [2], "controls": [1], "params": [-math.pi / 2]},
    {"gate": "H", "targets": [2]},
]


def _sup(n: int) -> str:
    return str(n).translate(_SUP)


def multiply_ops(a: int, control: int) -> list[dict[str, Any]]:
    """Operations for |x> -> |a*x mod 15> on the work register, controlled by ``control``."""
    a %= N
    flip = a not in _ROTATE
    rot = (N - a) if flip else a
    if rot not in _ROTATE:
        raise ValueError(f"{a} is not coprime to {N}")
    ops: list[dict[str, Any]] = []
    for i, j in _ROTATE[rot]:  # controlled swap of bits i and j
        x, y = WORK[i], WORK[j]
        ops += [{"gate": "CX", "controls": [y], "targets": [x]},
                {"gate": "CCX", "controls": [control, x], "targets": [y]},
                {"gate": "CX", "controls": [y], "targets": [x]}]
    if flip:
        ops += [{"gate": "CX", "controls": [control], "targets": [q]} for q in WORK]
    return ops


def shor_spec(a: int = 7) -> dict[str, Any]:
    """The full period-finding circuit for base ``a`` as a spec dict."""
    if a not in COPRIME:
        raise ValueError(f"a must be one of {COPRIME}")
    ops: list[dict[str, Any]] = [{"gate": "X", "targets": [WORK[0]]},
                                 {"gate": "H", "targets": list(range(COUNTING))}]
    ops += multiply_ops(a, 0)
    a2 = a * a % N
    if a2 != 1:
        ops += multiply_ops(a2, 1)
    ops += _IQFT
    skipped = "q1's and q2's multiplications are" if a2 == 1 else "q2's multiplication is"
    return {
        "kind": "circuit", "version": "1.0", "num_qubits": COUNTING + len(WORK), "num_clbits": COUNTING,
        "operations": ops,
        "measurements": [{"qubit": q, "clbit": q} for q in range(COUNTING)],
        "metadata": {
            "title": f"Shor: factor 15 with a = {a}",
            "notes": (f"Period finding for {a}ˣ mod 15. q0-q2 count, q3-q6 hold the value (q3 lowest), starting at 1. "
                      f"q0 multiplies by {a}, q1 by {a}{_sup(2)} = {a2} mod 15; {a}{_sup(4)} = 1 mod 15, so {skipped} "
                      "the identity and left out. The inverse QFT turns the period into the phase read on q0-q2."),
            "origin": "manual",
        },
    }


def _key(op: Any) -> tuple:
    return (op.gate, tuple(op.targets), tuple(op.controls), tuple(round(p, 9) for p in op.params))


@lru_cache(maxsize=None)
def _reference(a: int) -> tuple:
    spec = parse_spec(shor_spec(a))
    return tuple(_key(op) for op in spec.operations), tuple(sorted(spec.measured_pairs()))


def match_shor(spec: CircuitSpec) -> int | None:
    """The base ``a`` if ``spec`` is exactly the period-finding circuit for it, else None."""
    if spec.num_qubits != COUNTING + len(WORK):
        return None
    shape = (tuple(_key(op) for op in spec.operations), tuple(sorted(spec.measured_pairs())))
    return next((a for a in COPRIME if _reference(a) == shape), None)


# ---------------------------------------------------------------- the classical finish

def continued_fraction(x: Fraction) -> list[int]:
    """Continued fraction terms of a rational number."""
    terms = []
    while True:
        whole = x.numerator // x.denominator
        terms.append(whole)
        x -= whole
        if x == 0:
            return terms
        x = 1 / x


class ShorOutcome(BaseModel):
    bits: str  # the counting register as Qiskit prints it (q2 q1 q0)
    y: int
    phase: str  # "6/8"
    fraction: str  # "3/4"
    cf: list[int]
    r: int | None
    ok: bool
    factors: list[int] | None
    steps: list[str]
    ideal: float
    noisy: float
    measured: float | None = None


def finish(y: int, a: int) -> tuple[int | None, list[int] | None, list[str], list[int], Fraction]:
    """From a counting-register reading to factors, step by step (period guess r, factors, steps)."""
    size = 2 ** COUNTING
    frac = Fraction(y, size).limit_denominator(N - 1)
    cf = continued_fraction(frac)
    steps = [f"read y = {y}: phase {y}/{size}" + (f" = {frac}" if frac.denominator != size else "")]
    if y == 0:
        return None, None, steps + ["phase 0 says nothing about the period: run again"], cf, frac
    r = frac.denominator
    steps.append(f"continued fraction [{cf[0]}; {', '.join(map(str, cf[1:]))}] → period guess r = {r}")
    ar = pow(a, r, N)
    if ar != 1:
        return r, None, steps + [f"{a}{_sup(r)} mod 15 = {ar}, not 1: not the period"], cf, frac
    steps.append(f"{a}{_sup(r)} mod 15 = 1 ✓")
    if r % 2:
        return r, None, steps + ["r is odd: no square root to split, run again"], cf, frac
    half = pow(a, r // 2, N)
    if half == N - 1:
        return r, None, steps + [f"{a}{_sup(r // 2)} mod 15 = 14 = −1: the split is trivial, pick another a"], cf, frac
    p, q = math.gcd(half - 1, N), math.gcd(half + 1, N)
    steps.append(f"{a}{_sup(r // 2)} mod 15 = {half}: gcd({half - 1}, 15) = {p}, gcd({half + 1}, 15) = {q}")
    if 1 < p < N and p * q == N:
        return r, sorted([p, q]), steps + [f"15 = {min(p, q)} × {max(p, q)}"], cf, frac
    return r, None, steps + ["only the trivial factors 1 and 15: run again"], cf, frac


def order(a: int) -> int:
    """The true period of a^x mod 15, by brute force (the reference the circuit must reveal)."""
    return next(r for r in range(1, N) if pow(a, r, N) == 1)


class ShorLab(BaseModel):
    N: int = N
    a: int
    coprime: bool
    shortcut: int | None = None  # gcd(a, 15) when a shares a factor with 15
    period: int | None = None
    outcomes: list[ShorOutcome] = []
    success_ideal: float = 0.0
    success_noisy: float = 0.0
    success_measured: float | None = None
    shots: int | None = None
    noise: str = "realistic"
    noise_label: str = ""
    spec: dict[str, Any] | None = None
    summary: str


def _pct(p: float) -> str:
    return f"{p * 100:.0f}%"


def analyse(a: int, ideal: Distribution, noisy: Distribution, measured: Distribution | None,
            noise: str, shots: int | None) -> ShorLab:
    """Score every counting-register reading against the classical finish."""
    outcomes = []
    for y in range(2 ** COUNTING):
        bits = format(y, f"0{COUNTING}b")
        r, factors, steps, cf, frac = finish(y, a)
        outcomes.append(ShorOutcome(
            bits=bits, y=y, phase=f"{y}/{2 ** COUNTING}", fraction=str(frac), cf=cf, r=r, ok=factors is not None,
            factors=factors, steps=steps, ideal=ideal.get(bits, 0.0), noisy=noisy.get(bits, 0.0),
            measured=None if measured is None else measured.get(bits, 0.0)))
    win = [o for o in outcomes if o.ok]
    s_ideal = sum(o.ideal for o in win)
    s_noisy = sum(o.noisy for o in win)
    s_meas = None if measured is None else sum(o.measured or 0.0 for o in win)
    preset = get_preset(noise)
    lab = ShorLab(a=a, coprime=True, period=order(a), outcomes=outcomes, success_ideal=s_ideal, success_noisy=s_noisy,
                  success_measured=s_meas, shots=shots, noise=noise, noise_label=preset.label, spec=shor_spec(a),
                  summary="")
    lab.summary = _summary(lab)
    return lab


def _summary(lab: ShorLab) -> str:
    a, r = lab.a, lab.period
    good = [o for o in lab.outcomes if o.ok]
    peaks = [o for o in lab.outcomes if o.ideal > 1e-9]
    if not good:
        return (f"The period of {a}ˣ mod 15 is {r}, and the circuit finds it, but {a}{_sup(r // 2)} = 14 = −1 mod 15, "
                "so the gcds only give 1 and 15. Shor's recipe says: pick another a. (Factoring 15 classically is "
                "instant; this shows the mechanism, not a speedup.)")
    reads = " or ".join(o.bits for o in good)
    dead = [o.bits for o in peaks if not o.ok]
    text = (f"The period of {a}ˣ mod 15 is {r}. A perfect run reads {reads} with probability {_pct(lab.success_ideal)}, "
            f"and {'either' if len(good) > 1 else 'it'} gives 15 = 3 × 5 after a continued fraction and two gcds"
            + (f"; {' and '.join(dead)} carr{'y' if len(dead) > 1 else 'ies'} no usable period" if dead else "") + ". ")
    if lab.noise != "ideal":
        runs = 1 / lab.success_noisy if lab.success_noisy > 0 else float("inf")
        text += f"With {lab.noise_label.lower()} noise a run succeeds {_pct(lab.success_noisy)} of the time"
        text += f" (about {runs:.1f} runs on average)" if runs < 100 else ""
        if lab.success_measured is not None and lab.shots:
            text += f"; in these {lab.shots:,} shots, {_pct(lab.success_measured)} did"
        text += ". "
    return text + "Factoring 15 classically is instant: this shows the mechanism, not a speedup."


@lru_cache(maxsize=32)
def shor_lab(a: int, noise: str = "realistic") -> ShorLab:
    """The lab for base ``a``: exact odds, seeded shots and the classical finish."""
    if not 2 <= a < N:
        raise ValueError("a must be between 2 and 14")
    g = math.gcd(a, N)
    if g != 1:
        return ShorLab(a=a, coprime=False, shortcut=g,
                       summary=(f"gcd({a}, 15) = {g}: a lucky guess already splits 15 = {g} × {N // g}, with no quantum "
                                "step. Shor's algorithm is only needed when a shares no factor with N."))
    spec = parse_spec(shor_spec(a))
    ideal = ideal_distribution(spec)
    noisy = noisy_distribution(spec, noise)
    keys = sorted(noisy)
    rng = np.random.default_rng(1500 + a)
    probs = np.array([noisy[k] for k in keys])
    counts = rng.multinomial(LAB_SHOTS, probs / probs.sum())
    measured = {k: c / LAB_SHOTS for k, c in zip(keys, counts) if c}
    return analyse(a, ideal, noisy, measured, noise, LAB_SHOTS)


def shor_readout(spec: CircuitSpec, noise: str, measured: Distribution | None, shots: int | None) -> ShorLab | None:
    """For a run of an exact Shor circuit: the same analysis with the run's own measured counts."""
    a = match_shor(spec)
    if a is None:
        return None
    return analyse(a, ideal_distribution(spec), noisy_distribution(spec, noise), measured, noise, shots)
