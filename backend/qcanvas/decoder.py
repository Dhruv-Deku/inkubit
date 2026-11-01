"""Error-correction decoders on the distance-3 rotated surface code: matching against a neural network.

Code: 9 data qubits on a 3 x 3 grid (row-major 0..8). X checks [0,1,3,4], [4,5,7,8], [1,2], [6,7]; Z checks
[1,2,4,5], [3,4,6,7], [0,3], [5,8] (every X and Z check overlap on an even number of qubits, a test checks it).
Logical Z is Z0 Z1 Z2 (top row), logical X is X0 X3 X6.

Memory experiment in the Z basis, phenomenological noise (the standard model for decoder studies): prepare |0>_L,
then for each of T rounds every data qubit suffers X, Y or Z with probability p/3 each and every check outcome is
flipped with probability q (= p); finally the data qubits are read out, each flipping with probability p. Detection
events are changes of a check's value between rounds (Z checks start at +1; X checks are random in the first round,
so their events start at round 2; the final readout gives one more Z-check layer). The task: from the detection
events, say whether logical Z flipped.

* Matching (MWPM): X errors from Z-check events alone, on the space-time graph (space edges are data qubits,
  weight log((1 - p_x)/p_x) with p_x = 2p/3; time edges are measurement errors, log((1 - q)/q); boundary edges for
  qubits in one check), exact minimum-weight perfect matching by dynamic programming over the events. This is the
  standard decoder; it ignores the X checks.
* Neural: a NumPy MLP that sees the events of both check types. Y errors flip both kinds of check at once, so the X
  checks carry information about where X errors sit; matching cannot use it, a network can learn it (the reason
  learned decoders such as AlphaQubit beat matching on real data).
Both are scored on the same fresh samples; the unprotected qubit (error p per round, flipping with 2p/3 for X or Y)
is the break-even line.
"""

from __future__ import annotations

import heapq
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

X_CHECKS = [[0, 1, 3, 4], [4, 5, 7, 8], [1, 2], [6, 7]]
Z_CHECKS = [[1, 2, 4, 5], [3, 4, 6, 7], [0, 3], [5, 8]]
LOGICAL_Z = [0, 1, 2]
LOGICAL_X = [0, 3, 6]
ROUNDS = 3
WEIGHTS = Path(__file__).parent / "data" / "decoder.json"
WEIGHTS_D5 = Path(__file__).parent / "data" / "decoder_d5.json"


def layout(d: int) -> tuple[list[list[int]], list[list[int]], list[int], list[int]]:
    """The rotated surface code of odd distance d on a d x d grid (row-major): X checks, Z checks, logical Z (top
    row) and logical X (left column). Plaquette (i, j), 0 <= i, j <= d, covers the grid cells around corner (i, j);
    it is an X check when i + j is even, else Z; inner plaquettes all count, the top and bottom edges carry X checks
    and the left and right edges Z checks. d = 3 gives exactly the lists above (a test checks it)."""
    def cell(i: int, j: int) -> list[int]:
        return [r * d + c for r in (i - 1, i) for c in (j - 1, j) if 0 <= r < d and 0 <= c < d]

    bulk_x = [cell(i, j) for i in range(1, d) for j in range(1, d) if (i + j) % 2 == 0]
    bulk_z = [cell(i, j) for i in range(1, d) for j in range(1, d) if (i + j) % 2 == 1]
    edge_x = [cell(i, j) for i in (0, d) for j in range(1, d) if (i + j) % 2 == 0]
    edge_z = [cell(i, j) for j in (0, d) for i in range(1, d) if (i + j) % 2 == 1]
    return bulk_x + edge_x, bulk_z + edge_z, list(range(d)), [r * d for r in range(d)]


@lru_cache(maxsize=4)
def code(d: int = 3) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Parity-check matrices (Z checks, X checks) and the logical-Z row for distance d."""
    xs, zs, lz, _ = layout(d)
    hz = np.zeros((len(zs), d * d), np.uint8)
    hx = np.zeros((len(xs), d * d), np.uint8)
    for i, c in enumerate(zs):
        hz[i, c] = 1
    for i, c in enumerate(xs):
        hx[i, c] = 1
    lzv = np.zeros(d * d, np.uint8)
    lzv[lz] = 1
    return hz, hx, lzv


def sample(n: int, p: float, rounds: int = ROUNDS, q: float | None = None, seed: int = 0,
           keep_errors: bool = False, d: int = 3) -> dict[str, np.ndarray]:
    """Detection events and the logical flip for ``n`` memory experiments (vectorised, exact sampling)."""
    q = p if q is None else q
    hz, hx, lzv = code(d)
    nq, nz, nx = d * d, len(hz), len(hx)
    rng = np.random.default_rng(seed)
    xf = np.zeros((n, nq), np.uint8)
    zf = np.zeros((n, nq), np.uint8)
    sz = np.zeros((n, rounds + 2, nz), np.uint8)  # layer 0 is the +1 start
    sx = np.zeros((n, rounds + 1, nx), np.uint8)
    errs = []
    for t in range(1, rounds + 1):
        r = rng.random((n, nq))
        kind = np.where(r < p / 3, 1, np.where(r < 2 * p / 3, 2, np.where(r < p, 3, 0)))
        xf ^= ((kind == 1) | (kind == 2)).astype(np.uint8)
        zf ^= ((kind == 3) | (kind == 2)).astype(np.uint8)
        if keep_errors:
            errs.append(kind)
        sz[:, t] = ((xf @ hz.T) % 2) ^ (rng.random((n, nz)) < q)
        sx[:, t] = ((zf @ hx.T) % 2) ^ (rng.random((n, nx)) < q)
    final = xf ^ (rng.random((n, nq)) < p).astype(np.uint8)
    sz[:, rounds + 1] = (final @ hz.T) % 2
    dz = sz[:, 1:] ^ sz[:, :-1]  # (n, rounds + 1, nz)
    dx = sx[:, 2:] ^ sx[:, 1:-1]  # (n, rounds - 1, nx)
    out = {"dz": dz, "dx": dx, "flip": ((final @ lzv) % 2).astype(np.uint8)}
    if keep_errors:
        out["errors"] = np.stack(errs, axis=1)
        out["final_flips"] = (final ^ xf)
    return out


def features(s: dict[str, np.ndarray]) -> np.ndarray:
    n = len(s["flip"])
    return np.concatenate([s["dz"].reshape(n, -1), s["dx"].reshape(n, -1)], axis=1).astype(np.float32)


# ---------------------------------------------------------------- minimum-weight perfect matching

@lru_cache(maxsize=16)
def _graph(p: float, q: float, rounds: int) -> tuple[dict[tuple[int, int], tuple[float, int]], int]:
    """All-pairs shortest paths (weight, logical parity) over Z-check nodes (check, layer) plus the boundary."""
    px = 2 * p / 3
    ws, wt = math.log((1 - px) / px), math.log((1 - q) / q)
    layers = rounds + 1
    node = lambda c, t: t * 4 + c  # noqa: E731
    boundary = layers * 4
    adj: dict[int, list[tuple[int, float, int]]] = {i: [] for i in range(boundary + 1)}

    def edge(a: int, b: int, w: float, logical: int) -> None:
        adj[a].append((b, w, logical))
        adj[b].append((a, w, logical))

    for t in range(layers):
        for qb in range(9):
            checks = [i for i, c in enumerate(Z_CHECKS) if qb in c]
            lg = int(qb in LOGICAL_Z)
            if len(checks) == 2:
                edge(node(checks[0], t), node(checks[1], t), ws, lg)
            elif len(checks) == 1:
                edge(node(checks[0], t), boundary, ws, lg)
        if t + 1 < layers:
            for c in range(4):
                edge(node(c, t), node(c, t + 1), wt, 0)
    dist: dict[tuple[int, int], tuple[float, int]] = {}
    for src in range(boundary + 1):
        best = {src: (0.0, 0)}
        heap = [(0.0, src, 0)]
        while heap:
            d, u, lg = heapq.heappop(heap)
            if d > best[u][0] + 1e-12:
                continue
            for v, w, l2 in adj[u]:
                nd = d + w
                if v not in best or nd < best[v][0] - 1e-12:
                    best[v] = (nd, lg ^ l2)
                    heapq.heappush(heap, (nd, v, lg ^ l2))
        for v, val in best.items():
            dist[(src, v)] = val
    return dist, boundary


def mwpm(dz: np.ndarray, p: float, q: float | None = None, cache: dict | None = None) -> int:
    """Predicted logical flip for one shot's Z-check events (shape (rounds + 1, 4))."""
    q = p if q is None else q
    key = dz.tobytes()
    if cache is not None and key in cache:
        return cache[key]
    rounds = dz.shape[0] - 1
    dist, boundary = _graph(round(p, 6), round(q, 6), rounds)
    events = [t * 4 + c for t, c in zip(*np.nonzero(dz))]

    @lru_cache(maxsize=None)
    def solve(mask: int) -> tuple[float, int]:
        if mask == 0:
            return 0.0, 0
        i = (mask & -mask).bit_length() - 1
        rest = mask & ~(1 << i)
        a = events[i]
        w, lg = dist[(a, boundary)]
        sub = solve(rest)
        best = (w + sub[0], lg ^ sub[1])
        m = rest
        while m:
            j = (m & -m).bit_length() - 1
            m &= m - 1
            w2, l2 = dist[(a, events[j])]
            sub = solve(rest & ~(1 << j))
            if w2 + sub[0] < best[0]:
                best = (w2 + sub[0], l2 ^ sub[1])
        return best

    out = solve((1 << len(events)) - 1)[1] if len(events) <= 16 else 0
    if cache is not None:
        cache[key] = out
    return out


@lru_cache(maxsize=32)
def _matcher(p: float, q: float, d: int, layers: int, checks: str = "z", logical: bool = True):
    """PyMatching on the space-time graph of one check type: Z checks (they see X errors) or X checks (Z errors);
    with ``logical`` it returns the logical-Z flip, else the correction on each data qubit."""
    import pymatching

    hz, hx, lzv = code(d)
    h = hz if checks == "z" else hx
    px = 2 * p / 3
    return pymatching.Matching.from_check_matrix(
        h, weights=np.full(h.shape[1], math.log((1 - px) / px)), repetitions=layers,
        timelike_weights=np.full(h.shape[0], math.log((1 - q) / q)), faults_matrix=lzv[None, :] if logical else None)


def corrections(s: dict[str, np.ndarray], p: float, d: int) -> tuple[np.ndarray, np.ndarray]:
    """Where matching puts X corrections (from the Z checks) and Z corrections (from the X checks), per data qubit.
    A qubit in both is the signature of a Y error, which matching on one check type alone cannot see."""
    n = len(s["flip"])
    cx = _matcher(round(p, 6), round(p, 6), d, s["dz"].shape[1], "z", False).decode_batch(s["dz"].reshape(n, -1))
    cz = _matcher(round(p, 6), round(p, 6), d, s["dx"].shape[1], "x", False).decode_batch(s["dx"].reshape(n, -1))
    return cx.astype(np.uint8), cz.astype(np.uint8)


def inputs_d5(s: dict[str, np.ndarray], mw: np.ndarray, p: float) -> np.ndarray:
    """The distance-5 network's input: every event of both check types, both matchings' corrections, matching's
    logical verdict and log p."""
    cx, cz = corrections(s, p, 5)
    n = len(mw)
    return np.concatenate([features(s), cx.astype(np.float32), cz.astype(np.float32),
                           (2.0 * mw - 1.0)[:, None].astype(np.float32), np.full((n, 1), math.log(p) / 5, np.float32)], axis=1)


def matching(dz: np.ndarray, p: float, d: int, q: float | None = None) -> np.ndarray:
    """Minimum-weight perfect matching for a batch of shots at any distance, with PyMatching (sparse blossom) on the
    same space-time graph and weights as ``mwpm``; dz has shape (shots, rounds + 1, Z checks)."""
    q = p if q is None else q
    m = _matcher(round(p, 6), round(q, 6), d, dz.shape[1])
    return m.decode_batch(dz.reshape(len(dz), -1))[:, 0].astype(np.uint8)  # detectors time-major: layer * checks + check


def per_round(logical: float, rounds: int) -> float:
    """Logical error per round from the error over ``rounds`` rounds: 1 - 2 P = (1 - 2 e)^rounds."""
    return 0.5 * (1 - max(0.0, 1 - 2 * logical) ** (1 / rounds))


# ---------------------------------------------------------------- the neural decoder

def mlp_forward(x: np.ndarray, layers: list[tuple[np.ndarray, np.ndarray]]) -> np.ndarray:
    h = x
    for w, b in layers[:-1]:
        h = np.maximum(h @ w + b, 0)
    w, b = layers[-1]
    return 1 / (1 + np.exp(-(h @ w + b)[:, 0]))


class Curve(BaseModel):
    p: list[float]
    unprotected: list[float]
    mwpm: list[float]
    neural: list[float]
    shots: int


@lru_cache(maxsize=1)
def model() -> dict[str, Any]:
    return json.loads(WEIGHTS.read_text(encoding="utf-8"))


def neural(x: np.ndarray, p: float) -> np.ndarray:
    """The trained network's verdict; it also gets log p, as a decoder calibrated to its device would."""
    m = model()
    layers = [(np.array(w, np.float32), np.array(b, np.float32)) for w, b in m["layers"]]
    xin = np.concatenate([x, np.full((len(x), 1), math.log(p) / 5, np.float32)], axis=1)
    return (mlp_forward(xin, layers) > 0.5).astype(np.uint8)


@lru_cache(maxsize=1)
def model_d5() -> dict[str, Any] | None:
    return json.loads(WEIGHTS_D5.read_text(encoding="utf-8")) if WEIGHTS_D5.exists() else None


def neural_d5(s: dict[str, np.ndarray], mw: np.ndarray, p: float) -> np.ndarray:
    """The distance-5 network's verdict (scripts/train_decoder_d5.py)."""
    m = model_d5()
    layers = [(np.array(w, np.float32), np.array(b, np.float32)) for w, b in m["layers"]]
    return (mlp_forward(inputs_d5(s, mw, p), layers) > 0.5).astype(np.uint8)


def unprotected(p: float, rounds: int = ROUNDS) -> float:
    """A bare qubit over the same rounds plus readout: odd number of X-type flips (each 2p/3 per round, p at readout)."""
    px = 2 * p / 3
    even = 0.5 * (1 + (1 - 2 * px) ** rounds * (1 - 2 * p))
    return 1 - even


def example(p: float, seed: int, d: int = 3) -> dict[str, Any]:
    """One shot with at least one error (the next seed that has one): errors, events, the layout and both decoders'
    answers, at distance 3 (3 rounds) or, once its network is trained, distance 5 (5 rounds)."""
    rounds = 3 if d == 3 else 5
    for k in range(200):
        s = sample(1, p, rounds=rounds, d=d, seed=seed * 1000 + k, keep_errors=True)
        if s["errors"].any():
            break
    if d == 3:
        mw, nn = mwpm(s["dz"][0], p), int(neural(features(s), p)[0])
    else:
        mwv = matching(s["dz"], p, d)
        mw, nn = int(mwv[0]), int(neural_d5(s, mwv, p)[0])
    xs, zs, _, _ = layout(d)
    return {"p": p, "d": d, "x_checks": xs, "z_checks": zs, "errors": s["errors"][0].tolist(),
            "final_flips": s["final_flips"][0].tolist(), "dz": s["dz"][0].tolist(), "dx": s["dx"][0].tolist(),
            "flip": int(s["flip"][0]), "mwpm": mw, "neural": nn}
