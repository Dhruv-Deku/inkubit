"""QAOA for Max-Cut on a small graph: split the nodes into two teams so that as many edges as possible cross.

The story on the page is a dinner party: nodes are guests, edges are feuds, and the two teams are two tables. A
feud is defused when the pair sits at different tables (the edge is cut).

Everything is exact. The QAOA state is simulated directly in NumPy (|+>^n, then per layer the cost phase
exp(-i gamma C) and the mixer exp(-i beta X) on every qubit), which is what the optimizer calls hundreds of times;
the tests check it against Qiskit's Statevector of the generated circuit. The circuit uses only spec gates: H, and
per layer CX-RZ(-gamma)-CX for each edge (exp(+i gamma Z Z / 2), the cost phase up to a global phase) and RX(2 beta).
Brute force over all 2^n splits gives the true best cut, so every QAOA number is reported against it.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import numpy as np
from pydantic import BaseModel
from scipy.optimize import minimize

from qcanvas.sim.noise import get_preset
from qcanvas.spec import parse_spec
from qcanvas.verify.expected import noisy_distribution

MIN_NODES, MAX_NODES = 3, 8
MAX_EDGES = 20
MAX_DEPTH = 3
GRID_GAMMA, GRID_BETA = 48, 24  # landscape cells over the fundamental domain [0, pi] x [0, pi/2]
TOP = 8


class QaoaSplit(BaseModel):
    """One way to seat everyone, with its complement folded in (swapping the tables changes nothing)."""

    teams: list[int]  # per node, 0 or 1; node 0 always at table 0
    cut: int
    prob: float
    optimal: bool


class QaoaDepth(BaseModel):
    p: int
    gammas: list[float]
    betas: list[float]
    expected: float  # expected number of cut edges
    ratio: float  # expected / best
    p_best: float  # chance a single run reads a best split
    p_best_noisy: float | None = None
    ratio_noisy: float | None = None
    top: list[QaoaSplit]
    evals: int
    cx: int
    gates: int
    spec: dict[str, Any]


class QaoaLab(BaseModel):
    n: int
    edges: list[tuple[int, int]]
    max_cut: int
    optimal_count: int  # distinct best splits (complements folded)
    splits: int  # distinct splits checked by brute force
    random_ratio: float  # what a coin flip per node expects
    gammas: list[float]  # landscape axes (p = 1)
    betas: list[float]
    landscape: list[list[float]]  # [beta][gamma] expected cut / best
    path: list[tuple[float, float]]  # the p = 1 optimizer's (gamma, beta) steps
    depths: list[QaoaDepth]
    noise: str
    noise_label: str
    summary: str


def check_graph(n: int, edges: list[tuple[int, int]] | list[list[int]]) -> list[tuple[int, int]]:
    """Normalise and validate the graph; returns sorted unique (i, j) with i < j."""
    if not MIN_NODES <= n <= MAX_NODES:
        raise ValueError(f"use {MIN_NODES} to {MAX_NODES} nodes")
    out = set()
    for e in edges:
        if len(e) != 2:
            raise ValueError("each edge joins two nodes")
        i, j = int(e[0]), int(e[1])
        if not (0 <= i < n and 0 <= j < n):
            raise ValueError(f"edge {i}-{j} uses a node that does not exist")
        if i == j:
            raise ValueError("a node cannot feud with itself")
        out.add((min(i, j), max(i, j)))
    if not out:
        raise ValueError("add at least one edge")
    if len(out) > MAX_EDGES:
        raise ValueError(f"use at most {MAX_EDGES} edges")
    return sorted(out)


def cut_values(n: int, edges: list[tuple[int, int]]) -> np.ndarray:
    """Cut size of every basis state; bit k of the index is node k (Qiskit's qubit order)."""
    idx = np.arange(2 ** n)
    bits = [(idx >> k) & 1 for k in range(n)]
    return sum((bits[i] ^ bits[j] for i, j in edges), np.zeros(2 ** n, dtype=np.int64)).astype(float)


def _mix(psi: np.ndarray, n: int, beta: float) -> np.ndarray:
    """exp(-i beta X) on every qubit."""
    c, s = math.cos(beta), -1j * math.sin(beta)
    t = psi.reshape([2] * n)
    for ax in range(n):
        a0, a1 = np.take(t, 0, axis=ax), np.take(t, 1, axis=ax)
        t = np.stack([c * a0 + s * a1, s * a0 + c * a1], axis=ax)
    return t.reshape(-1)


def qaoa_state(n: int, cuts: np.ndarray, gammas: list[float] | np.ndarray, betas: list[float] | np.ndarray) -> np.ndarray:
    psi = np.full(2 ** n, 2 ** (-n / 2), dtype=complex)
    for g, b in zip(gammas, betas):
        psi = _mix(psi * np.exp(-1j * g * cuts), n, b)
    return psi


def _landscape(n: int, cuts: np.ndarray, gs: np.ndarray, bs: np.ndarray) -> np.ndarray:
    """Depth-1 expected cut over the whole grid at once: rows are betas, columns gammas."""
    phased = np.exp(-1j * np.outer(gs, cuts)) * 2 ** (-n / 2)  # (gammas, 2^n)
    rows = []
    for b in bs:
        c, s = math.cos(b), -1j * math.sin(b)
        t = phased.reshape([len(gs)] + [2] * n)
        for ax in range(1, n + 1):
            a0, a1 = np.take(t, 0, axis=ax), np.take(t, 1, axis=ax)
            t = np.stack([c * a0 + s * a1, s * a0 + c * a1], axis=ax)
        rows.append((np.abs(t.reshape(len(gs), -1)) ** 2) @ cuts)
    return np.array(rows)


def _expected(n: int, cuts: np.ndarray, x: np.ndarray) -> float:
    p = len(x) // 2
    psi = qaoa_state(n, cuts, x[:p], x[p:])
    return float(np.dot(np.abs(psi) ** 2, cuts))


def qaoa_spec(n: int, edges: list[tuple[int, int]], gammas: list[float], betas: list[float],
              labels: list[str] | None = None) -> dict[str, Any]:
    """The QAOA circuit as a spec: H on all, then per layer the cost phase on every edge and RX(2 beta) on all."""
    ops: list[dict[str, Any]] = [{"gate": "H", "targets": list(range(n))}]
    for g, b in zip(gammas, betas):
        for i, j in edges:
            ops += [{"gate": "CX", "controls": [i], "targets": [j]},
                    {"gate": "RZ", "targets": [j], "params": [round(-g, 6)]},
                    {"gate": "CX", "controls": [i], "targets": [j]}]
        ops += [{"gate": "RX", "targets": [q], "params": [round(2 * b, 6)]} for q in range(n)]
    who = ", ".join(f"q{k} = {name}" for k, name in enumerate(labels)) if labels else ""
    return {
        "kind": "circuit", "version": "1.0", "num_qubits": n, "num_clbits": n, "operations": ops,
        "measurements": [{"qubit": q, "clbit": q} for q in range(n)],
        "metadata": {
            "title": f"QAOA Max-Cut, {len(edges)} edges, depth {len(gammas)}",
            "notes": (f"Each qubit is a node{f' ({who})' if who else ''}; reading 0 or 1 puts it on one side. "
                      f"Per layer: CX-RZ(-γ)-CX on every edge (the cost phase), then RX(2β) on every qubit. "
                      f"Angles found by exact optimization: γ = {', '.join(f'{v:.3f}' for v in gammas)}, "
                      f"β = {', '.join(f'{v:.3f}' for v in betas)}."),
            "origin": "manual",
        },
    }


def _fold(n: int, probs: dict[int, float], cuts: np.ndarray, best: int) -> list[QaoaSplit]:
    """Fold each basis state with its complement, keeping node 0 at table 0."""
    full = 2 ** n - 1
    merged: dict[int, float] = {}
    for idx, pr in probs.items():
        key = idx if not idx & 1 else idx ^ full
        merged[key] = merged.get(key, 0.0) + pr
    ranked = sorted(merged.items(), key=lambda kv: (-kv[1], -cuts[kv[0]], kv[0]))
    return [QaoaSplit(teams=[(k >> q) & 1 for q in range(n)], cut=int(cuts[k]), prob=pr, optimal=int(cuts[k]) == best)
            for k, pr in ranked[:TOP]]


def _interp(prev: np.ndarray) -> np.ndarray:
    """INTERP start for depth p+1 from the depth-p optimum (Zhou et al., PRX 10, 021067)."""
    p = len(prev) // 2
    out = []
    for angles in (prev[:p], prev[p:]):
        a = np.concatenate([[0.0], angles, [0.0]])
        out.append([(i / p) * a[i] + ((p - i) / p) * a[i + 1] for i in range(p + 1)])
    return np.array(out[0] + out[1])


def _optimise(n: int, cuts: np.ndarray, starts: list[np.ndarray], path: list | None = None) -> tuple[np.ndarray, int]:
    count = [0]

    def f(x: np.ndarray) -> float:
        count[0] += 1
        return -_expected(n, cuts, x)

    best_x, best_v = None, math.inf
    for k, x0 in enumerate(starts):
        cb = (lambda xk: path.append((float(xk[0]), float(xk[1])))) if (path is not None and k == 0) else None
        res = minimize(f, x0, method="BFGS", callback=cb, options={"gtol": 1e-7, "maxiter": 400})
        if res.fun < best_v:
            best_x, best_v = res.x, res.fun
    return best_x, count[0]


def _canonical_p1(g: float, b: float) -> tuple[float, float]:
    """Map a depth-1 angle pair into [0, pi] x [0, pi/2] using E(g, b) = E(-g, -b), 2 pi in g and pi/2 in b."""
    g, b = g % (2 * math.pi), b % (math.pi / 2)
    if g > math.pi:
        g, b = 2 * math.pi - g, (math.pi / 2 - b) % (math.pi / 2)
    return g, b


@lru_cache(maxsize=64)
def _lab(n: int, edges: tuple[tuple[int, int], ...], noise: str) -> QaoaLab:
    edges_l = list(edges)
    cuts = cut_values(n, edges_l)
    best = int(cuts.max())
    full = 2 ** n - 1
    optimal = {i if not i & 1 else i ^ full for i in np.flatnonzero(cuts == best)}

    gs = np.linspace(0, math.pi, GRID_GAMMA + 1)[:-1] + math.pi / GRID_GAMMA / 2
    bs = np.linspace(0, math.pi / 2, GRID_BETA + 1)[:-1] + math.pi / 4 / GRID_BETA
    grid = _landscape(n, cuts, gs, bs)
    bi, gi = np.unravel_index(int(np.argmax(grid)), grid.shape)

    path: list[tuple[float, float]] = [(float(gs[gi]), float(bs[bi]))]
    x, evals = _optimise(n, cuts, [np.array([gs[gi], bs[bi]])], path)
    x[0], x[1] = _canonical_p1(x[0], x[1])
    path.append((float(x[0]), float(x[1])))
    preset = get_preset(noise)
    depths: list[QaoaDepth] = []
    for p in range(1, MAX_DEPTH + 1):
        if p > 1:
            prev = x
            pad = np.concatenate([prev[:p - 1], [0.0], prev[p - 1:], [0.0]])
            x, evals = _optimise(n, cuts, [_interp(prev), pad])
        gam, bet = [float(v) for v in x[:p]], [float(v) for v in x[p:]]
        psi = qaoa_state(n, cuts, gam, bet)
        probs = np.abs(psi) ** 2
        exp_cut = float(np.dot(probs, cuts))
        spec = qaoa_spec(n, edges_l, gam, bet)
        noisy = noisy_distribution(parse_spec(spec), noise) if noise != "ideal" else None
        p_noisy = r_noisy = None
        if noisy is not None:
            nd = {int(k, 2): v for k, v in noisy.items()}  # clbit k is node k, Qiskit keys are big-endian
            p_noisy = float(sum(v for k, v in nd.items() if cuts[k] == best))
            r_noisy = float(sum(v * cuts[k] for k, v in nd.items()) / best)
        depths.append(QaoaDepth(
            p=p, gammas=gam, betas=bet, expected=exp_cut, ratio=exp_cut / best,
            p_best=float(probs[cuts == best].sum()), p_best_noisy=p_noisy, ratio_noisy=r_noisy,
            top=_fold(n, {i: float(v) for i, v in enumerate(probs) if v > 1e-12}, cuts, best),
            evals=evals, cx=2 * len(edges_l) * p, gates=len(spec["operations"]) - 1 + n, spec=spec))
    lab = QaoaLab(
        n=n, edges=edges_l, max_cut=best, optimal_count=len(optimal), splits=2 ** (n - 1),
        random_ratio=len(edges_l) / 2 / best, gammas=[float(g) for g in gs], betas=[float(b) for b in bs],
        landscape=[[round(float(v) / best, 4) for v in row] for row in grid], path=path, depths=depths,
        noise=noise, noise_label=preset.label, summary="")
    lab.summary = _summary(lab)
    return lab


def qaoa_lab(n: int, edges: list[tuple[int, int]] | list[list[int]], noise: str = "realistic",
             labels: list[str] | None = None) -> QaoaLab:
    """The whole lab for one graph: brute-force answer, landscape, and QAOA at depths 1 to 3."""
    edges_n = check_graph(n, edges)
    lab = _lab(n, tuple(edges_n), noise)
    if labels:
        lab = lab.model_copy(deep=True)
        for d in lab.depths:
            d.spec = qaoa_spec(n, edges_n, d.gammas, d.betas, labels[:n])
    return lab


def _pct(p: float) -> str:
    return f"{p * 100:.0f}%"


def _summary(lab: QaoaLab) -> str:
    d1, dl = lab.depths[0], lab.depths[-1]
    m = len(lab.edges)
    ways = "one best split" if lab.optimal_count == 1 else f"{lab.optimal_count} best splits"
    text = (f"The best split cuts {lab.max_cut} of {m} edges ({ways}, found by checking all {lab.splits} splits). "
            f"A coin flip per node expects {_pct(lab.random_ratio)} of that. QAOA with one layer expects "
            f"{_pct(d1.ratio)} and reads a best split {_pct(d1.p_best)} of the time; with {dl.p} layers, "
            f"{_pct(dl.ratio)} and {_pct(dl.p_best)}")
    if dl.p_best_noisy is not None:
        text += f", or {_pct(dl.p_best_noisy)} with {lab.noise_label.lower()} noise on {dl.cx} CNOTs"
    return text + (". With this few nodes a laptop checks every split at once: this shows how QAOA works, not a "
                   "speedup, which for Max-Cut is still an open question.")
