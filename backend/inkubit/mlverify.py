"""ML verifier: a neural network that predicts, in well under a millisecond, how much of a circuit's answer survives
realistic noise, with a conformal error bar, and is then checked against exact simulation.

What it predicts: the Hellinger fidelity between the ideal outcome distribution and the one the realistic preset gives
(gate errors, relaxation and readout error), the same number the verifier and the hardware sweep report.

Inputs (all cheap): circuit structure (qubits, gates of each size, depth, two-qubit depth, busiest qubit), the ideal
distribution (entropy, largest outcome, how many outcomes matter; one statevector run), the noise scale, the rule of
thumb people use (the product of every gate's and readout's success probability), and two physics-informed inputs
computed on the ideal distribution alone: the fidelity left after the exact readout errors, and after a global
depolarizing model (the ideal odds mixed with uniform by one minus the gates' product, then readout). The last two
see what structure alone cannot: a Bell pair's outcomes 00 and 11 are two flips apart, so every readout error
leaves the answer, while for outcomes 00 and 01 half of them land back inside it.

Model: an ensemble of five small MLPs in NumPy (scripts/train_ml_verifier.py, fixed seeds), trained on random
circuits of 1 to 7 qubits (gate soup, layered, mirror circuits, reversible logic) labelled by exact density-matrix
simulation. The interval is adaptive split conformal: errors on a calibration set nobody trained on are divided by
the ensemble's spread (plus 0.01) and the 90th percentile q of those scores sets the interval +- q (spread + 0.01),
so it widens where the networks disagree, and on circuits like the training ones at least 90% of exact answers fall
inside it. That guarantee does not extend to circuits unlike the training set, which is
why every prediction up to 10 qubits is checked against the exact answer and the page says whether it held.
"""

from __future__ import annotations

import json
import math
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
from pydantic import BaseModel
from qiskit import QuantumCircuit

from inkubit.insights.circuit import MAX_NOISY_QUBITS, noisy_distribution, scaled_preset
from inkubit.sim.noise import get_preset, toffoli_error
from inkubit.spec.models import CircuitSpec
from inkubit.verify.expected import append_operation, ideal_distribution
from inkubit.verify.metrics import hellinger_fidelity

WEIGHTS = Path(__file__).parent / "data" / "ml_verifier.json"
TRAINED_QUBITS = 7

FEATURES = ["qubits", "measured", "gates_1q", "gates_2q", "gates_3q", "depth", "depth_2q", "busiest_qubit",
            "entropy_bits", "largest_outcome", "outcomes_that_matter", "noise_scale_log", "baseline", "baseline_log",
            "readout_only", "depolarizing_model"]


def _circuit(spec: CircuitSpec) -> QuantumCircuit:
    qc = QuantumCircuit(spec.num_qubits)
    for op in spec.operations:
        if op.gate != "MEASURE":
            append_operation(qc, op)
    return qc


def _readout(p: np.ndarray, m: int, p01: float, p10: float) -> np.ndarray:
    """Apply independent readout flips to a distribution over m bits (index bit k = bit k of the outcome)."""
    t = p.reshape((2,) * m) if m else p
    for axis in range(m):
        zero, one = np.take(t, 0, axis=axis), np.take(t, 1, axis=axis)
        t = np.stack([zero * (1 - p01) + one * p10, zero * p01 + one * (1 - p10)], axis=axis)
    return t.reshape(-1)


def _bhatt(p: np.ndarray, q: np.ndarray) -> float:
    return float(np.sqrt(p * q).sum() ** 2)


def features(spec: CircuitSpec, scale: float, ideal: dict[str, float] | None = None) -> np.ndarray:
    """The 16 inputs above, as a vector in FEATURES order."""
    qc = _circuit(spec)
    arity = [len(inst.qubits) for inst in qc.data]
    n1, n2, n3 = arity.count(1), arity.count(2), sum(1 for a in arity if a >= 3)
    load = [0] * spec.num_qubits
    for inst in qc.data:
        for q in inst.qubits:
            load[qc.find_bit(q).index] += 1
    depth = qc.depth()
    depth2 = qc.depth(filter_function=lambda inst: len(inst.qubits) >= 2)
    ideal = ideal if ideal is not None else ideal_distribution(spec)
    p = np.array([v for v in ideal.values() if v > 0])
    entropy = float(-(p * np.log2(p)).sum()) if p.size else 0.0
    preset = scaled_preset(get_preset("realistic"), scale)
    measured = len(spec.measured_pairs())
    readout = 1 - (preset.readout_p01 + preset.readout_p10) / 2
    gates = (1 - preset.p1) ** n1 * (1 - preset.p2) ** n2 * (1 - toffoli_error(preset)) ** n3
    baseline = gates * readout ** measured
    m = len(next(iter(ideal), ""))
    full = np.zeros(2 ** m)
    for key, v in ideal.items():
        full[int(key, 2) if key else 0] += v
    read = _readout(full, m, preset.readout_p01, preset.readout_p10)
    mixed = _readout(gates * full + (1 - gates) / full.size, m, preset.readout_p01, preset.readout_p10)
    return np.array([spec.num_qubits, measured, n1, n2, n3, depth, depth2, max(load, default=0), entropy,
                     float(p.max()) if p.size else 1.0, int((p > 1e-3).sum()), math.log(scale), baseline,
                     math.log(max(baseline, 1e-12)), _bhatt(full, read), _bhatt(full, mixed)], float)


def exact_fidelity(spec: CircuitSpec, scale: float, ideal: dict[str, float] | None = None) -> float:
    """The label: Hellinger fidelity of the realistic preset (times ``scale``) against the ideal distribution."""
    ideal = ideal if ideal is not None else ideal_distribution(spec)
    return hellinger_fidelity(ideal, noisy_distribution(spec, scaled_preset(get_preset("realistic"), scale)))


# ---------------------------------------------------------------- the network

def mlp_forward(x: np.ndarray, layers: list[tuple[np.ndarray, np.ndarray]]) -> np.ndarray:
    """tanh hidden layers, sigmoid output (a fidelity is between 0 and 1)."""
    h = x
    for w, b in layers[:-1]:
        h = np.tanh(h @ w + b)
    w, b = layers[-1]
    return 1 / (1 + np.exp(-(h @ w + b)[..., 0]))


class Model(BaseModel):
    features: list[str]
    mean: list[float]
    std: list[float]
    ensemble: list[list[tuple[list[list[float]], list[float]]]]
    q90: float  # conformal quantile of |error| / (spread + beta) for 90% coverage
    beta: float = 0.01
    metrics: dict[str, float | int | str]
    scatter: list[tuple[float, float, float]]  # held-out test circuits: exact, ML, baseline
    gallery: list[dict[str, float | str]]  # textbook circuits never seen in training


@lru_cache(maxsize=1)
def load_model() -> Model:
    return Model.model_validate(json.loads(WEIGHTS.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def _layers() -> list[list[tuple[np.ndarray, np.ndarray]]]:
    return [[(np.array(w), np.array(b)) for w, b in net] for net in load_model().ensemble]


def predict_raw(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Ensemble mean and interval half-width for a batch (or one row) of raw feature vectors."""
    m = load_model()
    z = (np.atleast_2d(x) - np.array(m.mean)) / np.array(m.std)
    outs = np.array([mlp_forward(z, net) for net in _layers()])
    return outs.mean(axis=0), m.q90 * (outs.std(axis=0) + m.beta)


class Prediction(BaseModel):
    fidelity: float
    low: float
    high: float
    baseline: float
    microseconds: float
    in_training_range: bool


class Check(BaseModel):
    prediction: Prediction
    exact: float | None  # None above MAX_NOISY_QUBITS, where exact density matrices are too big
    exact_ms: float | None
    inside: bool | None  # did the exact answer fall inside the conformal interval?
    error: float | None
    verdict: str


def predict(spec: CircuitSpec, scale: float = 1.0, ideal: dict[str, float] | None = None) -> Prediction:
    x = features(spec, scale, ideal)
    _layers()  # load the weights before timing
    start = time.perf_counter()
    mean, half = predict_raw(x)
    us = (time.perf_counter() - start) * 1e6
    y, q = float(mean[0]), float(half[0])
    return Prediction(fidelity=round(y, 4), low=round(max(0.0, y - q), 4), high=round(min(1.0, y + q), 4),
                      baseline=round(float(x[FEATURES.index("baseline")]), 4), microseconds=round(us, 1),
                      in_training_range=spec.num_qubits <= TRAINED_QUBITS)


def check(spec: CircuitSpec, scale: float = 1.0) -> Check:
    """Predict, then (up to 10 qubits) compute the exact answer and say whether the interval held."""
    ideal = ideal_distribution(spec)
    pred = predict(spec, scale, ideal)
    if spec.num_qubits > MAX_NOISY_QUBITS:
        return Check(prediction=pred, exact=None, exact_ms=None, inside=None, error=None,
                     verdict=f"no exact check above {MAX_NOISY_QUBITS} qubits: the prediction is an extrapolation")
    start = time.perf_counter()
    exact = exact_fidelity(spec, scale, ideal)
    ms = (time.perf_counter() - start) * 1e3
    inside = pred.low - 1e-9 <= exact <= pred.high + 1e-9
    err = abs(pred.fidelity - exact)
    verdict = (f"exact {exact:.4f} is inside the ML interval {pred.low:.3f} to {pred.high:.3f}" if inside else
               f"exact {exact:.4f} is outside the ML interval {pred.low:.3f} to {pred.high:.3f}: flagged, the exact "
               "answer is used")
    return Check(prediction=pred, exact=round(exact, 4), exact_ms=round(ms, 2), inside=inside, error=round(err, 4),
                 verdict=verdict)
