"""Autonomous discovery: Muse Spark proposes, exact simulation proves, noise decides.

Goal: prepare a target state (a GHZ state on all 7 qubits of an IBM heavy-hex chip, W and Dicke states, a random
state, or your own ket) with as few CNOTs as possible, on the chip's wiring, so that more of it survives realistic
noise. Two-qubit gates cost about 15 times more error than one-qubit gates in the realistic preset, so fewer CNOTs is
what matters.

The loop:
1. Baselines: the textbook circuit (when there is one) and Qiskit's generic state preparation, both compiled by Qiskit
   at optimization level 3 onto the same wiring.
2. Ideas: Muse Spark (Muse Wonder in deep mode) proposes CNOT layouts with a reason each; spanning-tree heuristics and
   random layouts on the allowed pairs add more. Layouts are tried from the fewest CNOTs up.
3. Fit: for each layout, the single-qubit rotations between the CNOTs are optimised exactly (L-BFGS on the overlap with
   the target, NumPy statevector, restarts). A layout counts only if it reaches the target to 1e-9.
4. Proof: every winner is rebuilt as an Inkubit spec and simulated independently by Qiskit's Statevector; the overlap
   with the target must be at least 1 - 1e-8.
5. Screen: the ML verifier ranks all correct candidates and the baselines in microseconds.
6. Score: exact density-matrix simulation with the realistic preset gives each one's state fidelity with the target
   (and the outcome fidelity the ML verifier predicts, to say whether its ranking held).

"Fewest found" is what the search found within its budget, not a proof that no shorter circuit exists.
"""

from __future__ import annotations

import json
import math
import random
import threading
import time
import uuid
from typing import Any

import numpy as np
from pydantic import BaseModel, Field
from scipy.optimize import minimize

from inkubit.adapters.base import ModelCall
from inkubit.agent.events import EventBus
from inkubit.insights.circuit import FALCON_7Q

PRESETS_TITLE = "Realistic superconducting"
PROOF = 1e-8
FIT = 1e-9
MAX_QUBITS = 7
MAX_CX = 10
TIME_BUDGET_S = 100.0


class Goal(BaseModel):
    id: str
    title: str
    blurb: str
    num_qubits: int
    coupling: list[tuple[int, int]] | None = None  # undirected allowed pairs; None = all-to-all
    textbook: list[dict[str, Any]] | None = None  # spec operations of the textbook circuit, if there is one


def _dicke(n: int, k: int) -> np.ndarray:
    v = np.array([1.0 if bin(i).count("1") == k else 0.0 for i in range(2 ** n)])
    return v / np.linalg.norm(v)


def _ghz(n: int) -> np.ndarray:
    v = np.zeros(2 ** n)
    v[0] = v[-1] = 1 / math.sqrt(2)
    return v


def _random_state(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.normal(size=2 ** n) + 1j * rng.normal(size=2 ** n)
    v /= np.linalg.norm(v)
    return v * np.exp(-1j * np.angle(v[0]))


GOALS: dict[str, Goal] = {
    "ghz7_hex": Goal(id="ghz7_hex", title="GHZ on all 7 qubits of an IBM heavy-hex chip", num_qubits=7,
                     blurb="Seven qubits all 0 or all 1 at once, on a chip where each qubit talks to at most three "
                           "neighbours. The textbook chain does not fit the wiring, so the compiler adds SWAPs.",
                     coupling=list(FALCON_7Q),
                     textbook=[{"gate": "H", "targets": [0]}] + [{"gate": "CX", "controls": [q], "targets": [q + 1]}
                                                                 for q in range(6)]),
    "w4": Goal(id="w4", title="W state on 4 qubits", num_qubits=4,
               blurb="One excitation shared equally by four qubits: the state that keeps its entanglement when a "
                     "qubit is lost, used in quantum networks."),
    "dicke42": Goal(id="dicke42", title="Dicke state |D(4,2)⟩", num_qubits=4,
                    blurb="Every way of having exactly two of four qubits at 1, in equal superposition: a resource "
                          "for quantum sensing beyond the standard limit."),
    "random3": Goal(id="random3", title="A random 3-qubit state", num_qubits=3,
                    blurb="Eight complex amplitudes with no structure at all (seeded): the general case."),
}


def goal_target(goal: Goal) -> np.ndarray:
    return {"ghz7_hex": lambda: _ghz(7), "w4": lambda: _dicke(4, 1), "dicke42": lambda: _dicke(4, 2),
            "random3": lambda: _random_state(3, 2026)}[goal.id]()


def custom_goal(ket: str) -> tuple[Goal, np.ndarray]:
    from inkubit.notation import parse_ket

    v, _ = parse_ket(ket)
    v = np.asarray(v, complex)
    n = int(round(math.log2(len(v))))
    if 2 ** n != len(v) or not 1 <= n <= 5:
        raise ValueError("bring a state of 1 to 5 qubits")
    v = v / np.linalg.norm(v)
    k = int(np.argmax(np.abs(v) > 1e-9))
    v = v * np.exp(-1j * np.angle(v[k]))
    return Goal(id="custom", title=f"Your state: {ket.strip()[:60]}", num_qubits=n,
                blurb="The state you typed, read exactly by the Rosetta's parser."), v


# ---------------------------------------------------------------- statevector kernels (Qiskit order: qubit 0 rightmost)

def _rot(psi: np.ndarray, u: np.ndarray, q: int, n: int) -> np.ndarray:
    t = np.moveaxis(psi.reshape((2,) * n), n - 1 - q, 0)
    t = np.tensordot(u, t, axes=(1, 0))
    return np.moveaxis(t, 0, n - 1 - q).reshape(-1)


def _cx(psi: np.ndarray, c: int, t: int, n: int) -> np.ndarray:
    a = psi.reshape((2,) * n).copy()
    ac, at = n - 1 - c, n - 1 - t
    idx: list[Any] = [slice(None)] * n
    idx[ac] = 1
    a[tuple(idx)] = np.flip(a[tuple(idx)], axis=at if at < ac else at - 1)
    return a.reshape(-1)


def _ry(t: float) -> np.ndarray:
    c, s = math.cos(t / 2), math.sin(t / 2)
    return np.array([[c, -s], [s, c]], complex)


def _rz(t: float) -> np.ndarray:
    return np.array([[np.exp(-0.5j * t), 0], [0, np.exp(0.5j * t)]])


def _slots(skel: list[tuple[int, int]], n: int) -> list[int]:
    """Qubit of each rotation slot: one per qubit first, then both qubits after every CNOT."""
    return list(range(n)) + [q for c, t in skel for q in (c, t)]


def prepare(params: np.ndarray, skel: list[tuple[int, int]], n: int, cplx: bool) -> np.ndarray:
    psi = np.zeros(2 ** n, complex)
    psi[0] = 1
    per = 2 if cplx else 1
    slots = _slots(skel, n)
    k = 0

    def rot(q: int) -> None:
        nonlocal psi, k
        psi = _rot(psi, _ry(params[k]), q, n)
        if cplx:
            psi = _rot(psi, _rz(params[k + 1]), q, n)
        k += per

    for q in slots[:n]:
        rot(q)
    for i, (c, t) in enumerate(skel):
        psi = _cx(psi, c, t, n)
        rot(slots[n + 2 * i])
        rot(slots[n + 2 * i + 1])
    return psi


def fit(target: np.ndarray, skel: list[tuple[int, int]], n: int, cplx: bool, rng: np.random.Generator,
        restarts: int = 2) -> tuple[float, np.ndarray | None]:
    npar = len(_slots(skel, n)) * (2 if cplx else 1)
    best: tuple[float, np.ndarray | None] = (1.0, None)
    tc = np.conj(target)

    def loss(x: np.ndarray) -> float:
        return 1.0 - abs(np.dot(tc, prepare(x, skel, n, cplx))) ** 2

    for _ in range(restarts):
        res = minimize(loss, rng.uniform(-math.pi, math.pi, npar), method="L-BFGS-B", options={"maxiter": 500})
        if res.fun < best[0]:
            best = (float(res.fun), res.x)
        if best[0] < FIT:
            break
    return best


def prune(target: np.ndarray, skel: list[tuple[int, int]], n: int, cplx: bool, x: np.ndarray,
          threshold: float = 1e-3) -> np.ndarray:
    """Zero every rotation below ``threshold``, re-fit the rest exactly, and keep the result only if it still reaches
    the target. Fewer gates, less noise."""
    wrapped = (x + math.pi) % (2 * math.pi) - math.pi
    free = np.abs(wrapped) > threshold
    if free.all():
        return x
    tc = np.conj(target)

    def loss(v: np.ndarray) -> float:
        full = np.zeros_like(x)
        full[free] = v
        return 1.0 - abs(np.dot(tc, prepare(full, skel, n, cplx))) ** 2

    res = minimize(loss, wrapped[free], method="L-BFGS-B", options={"maxiter": 500})
    if res.fun >= FIT:
        return x
    out = np.zeros_like(x)
    out[free] = res.x
    return out


def to_ops(params: np.ndarray, skel: list[tuple[int, int]], n: int, cplx: bool) -> list[dict[str, Any]]:
    """Spec operations, dropping rotations that are the identity up to a global phase."""
    ops: list[dict[str, Any]] = []
    per = 2 if cplx else 1
    slots = _slots(skel, n)

    def rot(q: int, k: int) -> None:
        for gate, a in (("RY", params[k]), ("RZ", params[k + 1] if cplx else 0.0)):
            a = float((a + math.pi) % (2 * math.pi) - math.pi)
            if abs(a) > 1e-7:
                ops.append({"gate": gate, "targets": [q], "params": [round(a, 10)]})

    k = 0
    for q in slots[:n]:
        rot(q, k)
        k += per
    for i, (c, t) in enumerate(skel):
        ops.append({"gate": "CX", "controls": [c], "targets": [t]})
        for q in (slots[n + 2 * i], slots[n + 2 * i + 1]):
            rot(q, k)
            k += per
    return ops


# ---------------------------------------------------------------- layouts to try

def _pairs(goal: Goal) -> list[tuple[int, int]]:
    n = goal.num_qubits
    if goal.coupling is None:
        return [(a, b) for a in range(n) for b in range(n) if a != b]
    return [p for a, b in goal.coupling for p in ((a, b), (b, a))]


def tree_layouts(goal: Goal) -> list[list[tuple[int, int]]]:
    """CNOT fan-outs along a breadth-first spanning tree from every root (the shape of a GHZ preparation)."""
    n = goal.num_qubits
    nbr: dict[int, set[int]] = {q: set() for q in range(n)}
    for a, b in _pairs(goal):
        nbr[a].add(b)
    out = []
    for root in range(n):
        seen, order, frontier = {root}, [], [root]
        while frontier:
            nxt = []
            for p in frontier:
                for c in sorted(nbr[p]):
                    if c not in seen:
                        seen.add(c)
                        order.append((p, c))
                        nxt.append(c)
            frontier = nxt
        if len(seen) == n:
            out.append(order)
    return out


def lower_bound(target: np.ndarray, n: int) -> int:
    from inkubit.notation import blocks

    groups = blocks(target, n) or [list(range(n))]
    return sum(len(g) - 1 for g in groups)


# ---------------------------------------------------------------- scoring

def spec_of(ops: list[dict[str, Any]], n: int, title: str) -> dict[str, Any]:
    return {"kind": "circuit", "version": "1.0", "num_qubits": n, "num_clbits": n, "operations": ops,
            "measurements": [{"qubit": q, "clbit": q} for q in range(n)],
            "metadata": {"title": title[:80], "origin": "manual"}}


class Entry(BaseModel):
    label: str
    source: str  # textbook | compiler | muse | tree | search
    cx: int
    one_qubit: int
    depth: int
    proof: float  # overlap with the target by Qiskit's Statevector (baselines: their own output, up to the layout)
    noisy_fidelity: float  # exact density matrix, realistic preset: state fidelity with the ideal output
    outcome_fidelity: float  # Hellinger fidelity of outcome odds (what the ML verifier predicts)
    ml_fidelity: float | None = None
    why: str = ""
    spec: dict[str, Any]


def _measure(raw: dict[str, Any], target: np.ndarray | None) -> tuple[float, float, float, int, int, int]:
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Statevector

    from inkubit.insights.circuit import noisy_distribution, noisy_state
    from inkubit.sim.noise import get_preset
    from inkubit.spec import parse_spec
    from inkubit.verify.expected import append_operation, ideal_distribution
    from inkubit.verify.metrics import hellinger_fidelity

    spec = parse_spec(raw)
    qc = QuantumCircuit(spec.num_qubits)
    for op in spec.operations:
        append_operation(qc, op)
    psi = Statevector(qc).data
    proof = float(abs(np.vdot(target, psi)) ** 2) if target is not None else 1.0
    preset = get_preset("realistic")
    rho = noisy_state(spec, preset).data
    noisy = float(np.real(np.conj(psi) @ rho @ psi))
    outcome = hellinger_fidelity(ideal_distribution(spec), noisy_distribution(spec, preset))
    ops = qc.count_ops()
    cx = int(ops.get("cx", 0))
    return proof, noisy, outcome, cx, sum(ops.values()) - cx, qc.depth()


def _from_qiskit(qc: Any, n: int) -> list[dict[str, Any]]:
    ops = []
    for inst in qc.data:
        name = inst.operation.name
        qs = [qc.find_bit(q).index for q in inst.qubits]
        if name == "cx":
            ops.append({"gate": "CX", "controls": [qs[0]], "targets": [qs[1]]})
        elif name in ("rz", "sx", "x"):
            op: dict[str, Any] = {"gate": name.upper(), "targets": [qs[0]]}
            if name == "rz":
                op["params"] = [float(inst.operation.params[0])]
            ops.append(op)
    return ops


def baselines(goal: Goal, target: np.ndarray) -> list[tuple[str, str, list[dict[str, Any]], int]]:
    """(label, source, operations, width) compiled by Qiskit at level 3 onto the goal's wiring."""
    from qiskit import QuantumCircuit, transpile
    from qiskit.circuit.library import StatePreparation
    from qiskit.transpiler import CouplingMap

    from inkubit.spec import parse_spec
    from inkubit.verify.expected import append_operation

    n = goal.num_qubits
    cmap = CouplingMap([list(p) for p in _pairs(goal)]) if goal.coupling else None
    out = []
    circuits = []
    if goal.textbook:
        qc = QuantumCircuit(n)
        for op in parse_spec(spec_of(goal.textbook, n, "textbook")).operations:
            append_operation(qc, op)
        circuits.append(("Textbook circuit, compiled onto the wiring" if cmap else "Textbook circuit", "textbook", qc))
    qc = QuantumCircuit(n)
    qc.append(StatePreparation(target), range(n))
    circuits.append(("Qiskit state preparation, optimisation level 3", "compiler", qc))
    for label, source, qc in circuits:
        t = transpile(qc, basis_gates=["cx", "rz", "sx", "x"], coupling_map=cmap, optimization_level=3,
                      seed_transpiler=7)
        out.append((label, source, _from_qiskit(t, t.num_qubits), t.num_qubits))
    return out


# ---------------------------------------------------------------- the run

IDEA_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["ideas"], "properties": {
    "ideas": {"type": "array", "maxItems": 6, "items": {
        "type": "object", "additionalProperties": False, "required": ["cnots", "why"], "properties": {
            "cnots": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}, "minItems": 2,
                                                  "maxItems": 2},
                      "description": "Ordered [control, target] pairs."},
            "why": {"type": "string", "description": "One sentence: why this layout can make the state."}}}}}}
IDEA_SYSTEM = (
    "You design quantum circuits. Propose CNOT layouts: ordered [control, target] pairs that, with free single-qubit "
    "rotations before and after every CNOT, can prepare the target state exactly with as few CNOTs as possible. Use "
    "only the allowed pairs. Qubit 0 is the rightmost character of a ket. Return up to 6 layouts, fewest CNOTs first, "
    "each with a one-sentence reason. Do not compute amplitudes; an exact optimiser fits the angles and checks.")


class Discovery:
    def __init__(self, goal: Goal):
        self.id = uuid.uuid4().hex[:12]
        self.goal = goal
        self.bus = EventBus()
        self.status = "running"
        self.error: str | None = None
        self.result: dict[str, Any] | None = None

    def log(self, text: str, **extra: Any) -> None:
        self.bus.emit("discovery", "info", text, kind="log", text=text, **extra)


def _ideas(goal: Goal, target: np.ndarray, base_cx: int, k0: int, reasoning: Any, model: str | None
           ) -> tuple[list[tuple[list[tuple[int, int]], str]], ModelCall | None]:
    from inkubit.notation import dirac

    allowed = sorted({tuple(sorted(p)) for p in _pairs(goal)})
    user = json.dumps({"target_state": dirac(target, goal.num_qubits).text, "num_qubits": goal.num_qubits,
                       "allowed_pairs_either_direction": allowed, "compiler_uses_cnots": base_cx,
                       "at_least_cnots": k0}, ensure_ascii=False)
    data, call = reasoning.structured(IDEA_SYSTEM, user, IDEA_SCHEMA, "circuit_ideas", effort="medium",
                                      max_tokens=12000, model=model)
    ok = set(_pairs(goal))
    out = []
    for idea in data.get("ideas") or []:
        skel = [(int(p[0]), int(p[1])) for p in idea.get("cnots") or [] if len(p) == 2]
        if skel and len(skel) <= MAX_CX and all(p in ok for p in skel):
            out.append((skel, str(idea.get("why", ""))[:200]))
    return out, call


def run_discovery(d: Discovery, target: np.ndarray, reasoning: Any = None, model: str | None = None,
                  seed: int = 2026, budget_s: float = TIME_BUDGET_S) -> None:
    """Search, prove, screen and score; every step is published on ``d.bus``. Never raises."""
    from inkubit.mlverify import predict
    from inkubit.spec import parse_spec

    t0 = time.perf_counter()
    goal = d.goal
    n = goal.num_qubits
    cplx = bool(np.max(np.abs(np.imag(target))) > 1e-12 or np.any(np.real(target) < -1e-12))
    rng = np.random.default_rng(seed)
    pick = random.Random(seed)
    calls: list[ModelCall] = []
    try:
        from inkubit.notation import dirac

        d.log(f"Target: {dirac(target, n).text}")
        entries: list[Entry] = []
        for label, source, ops, width in baselines(goal, target):
            raw = spec_of(ops, width, label)
            proof, noisy, outcome, cx, oneq, depth = _measure(raw, None)
            entries.append(Entry(label=label, source=source, cx=cx, one_qubit=oneq, depth=depth, proof=proof,
                                 noisy_fidelity=noisy, outcome_fidelity=outcome, spec=raw))
            d.log(f"Baseline, {label}: {cx} CNOTs, {oneq} one-qubit gates, keeps {noisy:.3f} of the state under "
                  "realistic noise", kind_entry="baseline")
        base_cx = min(e.cx for e in entries)
        k0 = lower_bound(target, n)
        ideas: list[tuple[list[tuple[int, int]], str, str]] = []
        if reasoning is not None:
            try:
                got, call = _ideas(goal, target, base_cx, k0, reasoning, model)
                if call:
                    calls.append(call)
                ideas = [(s, why, "muse") for s, why in got]
                d.log(f"{call.model if call else 'model'} proposed {len(got)} CNOT layouts: "
                      + "; ".join(f"{len(s)} CNOTs" for s, _ in got))
            except Exception as err:  # noqa: BLE001 - the search goes on without ideas, and says so
                d.log(f"The model's ideas were not available ({str(err)[:120]}); searching on heuristics alone")
        trees = [(s, "CNOT fan-out along a spanning tree of the wiring", "tree") for s in tree_layouts(goal)]
        pairs = _pairs(goal)
        per_k = 50 if n <= 4 else 24
        found: list[tuple[list[tuple[int, int]], np.ndarray, str, str]] = []
        tried = 0
        seen: set[tuple[tuple[int, int], ...]] = set()
        best_k = None
        for k in range(max(k0, 1), min(base_cx, MAX_CX) + 1):
            queue = [(s, w, src) for s, w, src in ideas + trees if len(s) == k]
            queue += [([pick.choice(pairs) for _ in range(k)], "random layout", "search") for _ in range(per_k)]
            hits = 0
            for skel, why, src in queue:
                key = tuple(skel)
                if key in seen:
                    continue
                seen.add(key)
                tried += 1
                err, x = fit(target, skel, n, cplx, rng, restarts=3 if src != "search" else 2)
                if err < FIT and x is not None:
                    found.append((skel, prune(target, skel, n, cplx, x), why, src))
                    hits += 1
                    d.log(f"Found: {k} CNOTs ({'Muse idea' if src == 'muse' else src}), infidelity {err:.1e}",
                          kind_entry="found", cnots=k)
                    if hits >= 4:
                        break
                if time.perf_counter() - t0 > budget_s:
                    break
            d.log(f"{k} CNOTs: {hits} of the layouts tried reach the target" if hits else
                  f"{k} CNOTs: none of the layouts tried reach the target", kind_entry="layer", cnots=k)
            if hits:
                best_k = k
                break
            if time.perf_counter() - t0 > budget_s:
                d.log("Time budget reached")
                break
        for i, (skel, x, why, src) in enumerate(found):
            raw = spec_of(to_ops(x, skel, n, cplx), n, f"Discovered: {len(skel)} CNOTs")
            proof, noisy, outcome, cx, oneq, depth = _measure(raw, target)
            if proof < 1 - PROOF:
                d.log(f"A candidate failed the independent Qiskit check (overlap {proof:.9f}); dropped")
                continue
            label = {"muse": "Muse Spark's layout", "tree": "Spanning-tree fan-out", "search": "Search"}[src]
            entries.append(Entry(label=f"{label} #{i + 1}", source=src, cx=cx, one_qubit=oneq, depth=depth,
                                 proof=proof, noisy_fidelity=noisy, outcome_fidelity=outcome, why=why, spec=raw))
        # ML screening of everything, then compare with the exact ranking
        start = time.perf_counter()
        for e in entries:
            e.ml_fidelity = predict(parse_spec(e.spec), 1.0).fidelity
        ml_ms = (time.perf_counter() - start) * 1e3
        found_e = [e for e in entries if e.source not in ("textbook", "compiler")]
        base_e = [e for e in entries if e.source in ("textbook", "compiler")]
        ml_agrees = None
        if found_e:  # the decision that matters: does the ML verifier also put the discovered circuit first?
            exact_says = max(e.outcome_fidelity for e in found_e) > max(e.outcome_fidelity for e in base_e)
            ml_says = max(e.ml_fidelity or 0 for e in found_e) > max(e.ml_fidelity or 0 for e in base_e)
            ml_agrees = exact_says == ml_says
        rank = None
        if len(entries) >= 3:
            from scipy.stats import spearmanr

            rank = float(spearmanr([e.ml_fidelity for e in entries], [e.outcome_fidelity for e in entries]).statistic)
        entries.sort(key=lambda e: -e.noisy_fidelity)
        winners = [e for e in entries if e.source not in ("textbook", "compiler")]
        best_base = max((e for e in entries if e.source in ("textbook", "compiler")), key=lambda e: e.noisy_fidelity)
        if winners:
            w = winners[0]
            finding = (f"Found a circuit with {w.cx} CNOTs where the best baseline needs {best_base.cx}; proven to make "
                       f"the state (overlap {w.proof:.9f}), it keeps {w.noisy_fidelity:.3f} of it under realistic "
                       f"noise against {best_base.noisy_fidelity:.3f}.")
        else:
            finding = (f"No layout with fewer CNOTs than the baseline ({base_cx}) reached the target within the "
                       "budget; the baseline stands.")
        d.result = {
            "goal": goal.model_dump(), "target": dirac(target, n).text, "num_qubits": n, "complex": cplx,
            "entries": [e.model_dump(mode="json") for e in entries], "tried": tried,
            "fewest_cnots": best_k, "baseline_cnots": base_cx, "lower_bound": k0,
            "ml_agrees": ml_agrees, "ml_rank_correlation": None if rank is None or math.isnan(rank) else round(rank, 3),
            "ml_milliseconds": round(ml_ms, 1), "finding": finding,
            "calls": [c.model_dump(mode="json") for c in calls], "seconds": round(time.perf_counter() - t0, 1),
        }
        d.status = "done"
        d.bus.emit("discovery", "ok", finding, kind="result", result=d.result)
    except Exception as err:  # noqa: BLE001 - shown on the page, never a made-up result
        d.status, d.error = "failed", str(err)[:400]
        d.bus.emit("discovery", "fail", d.error, kind="error")
    finally:
        d.bus.close()


def launch(d: Discovery, target: np.ndarray, models: Any, deep: bool) -> None:
    s = models.settings
    live = s.provider == "meta" and s.has_key
    threading.Thread(target=run_discovery, name=f"discovery-{d.id}", daemon=True,
                     args=(d, target, models.reasoning if live else None, s.deep_model if deep and live else None)).start()


class Store:
    def __init__(self, keep: int = 20):
        self._items: dict[str, Discovery] = {}
        self._keep = keep

    def add(self, d: Discovery) -> None:
        self._items[d.id] = d
        while len(self._items) > self._keep:
            self._items.pop(next(iter(self._items)))

    def get(self, key: str) -> Discovery | None:
        return self._items.get(key)


discoveries = Store()


class GoalInfo(BaseModel):
    id: str
    title: str
    blurb: str
    num_qubits: int
    chip: bool = Field(default=False)


def goal_list() -> list[GoalInfo]:
    return [GoalInfo(id=g.id, title=g.title, blurb=g.blurb, num_qubits=g.num_qubits, chip=g.coupling is not None)
            for g in GOALS.values()]
