"""Bug hunt: one gate in a known circuit is wrong; find it from the histogram.

A round is a gallery circuit with one planted mistake of the kind people and models make: a gate on the wrong
wire, a CNOT with control and target swapped, a look-alike gate (S for T, X for Z), a sign or factor-of-two slip in
an angle, or a stray extra gate. The player sees what the circuit should give, what the broken one gave in 1,000
shots, and the broken circuit, and clicks the culprit.

Rounds are stateless: (level, seed) regenerates the same round, so the server never stores an answer and the page
never receives one before it guesses. Grading is exact and fair: the machine tries every single-gate edit
(delete, swap the gate, move it, flip control and target, change the angle) and any operation whose edit restores
the intended odds exactly counts as a correct answer, not only the planted one.
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np
from pydantic import BaseModel

from qcanvas import EXAMPLES_DIR
from qcanvas.spec import parse_spec
from qcanvas.verify.expected import Distribution, ideal_distribution
from qcanvas.verify.metrics import total_variation_distance

LEVELS = {
    1: ("Warm-up", ["bell", "ghz3", "superposition", "toffoli_and", "superdense", "deutsch_jozsa"]),
    2: ("Tricky", ["bernstein_vazirani", "grover2", "w_state", "teleportation", "bit_flip_code"]),
    3: ("Hard", ["phase_estimation", "qaoa_party"]),
}
# A round is only fair if few gates could be "the" bug: some circuits have many single edits that give the same odds
# (Bell has two gates; Shor measures 3 of 7 qubits), so rounds where too many gates count as right are re-planted.
MAX_SHARE = {1: 0.5, 2: 0.4, 3: 0.25}
SHOTS = 1000
MIN_TVD = 0.2  # a planted bug must move at least this much probability, or nobody could see it
SAME = 1e-6

PLAIN = ["H", "X", "Y", "Z", "S", "T", "SDG", "TDG", "SX"]
ROTATION = ["RX", "RY", "RZ"]
LOOKALIKE = {"X": ["Z", "Y"], "Z": ["X"], "Y": ["X"], "S": ["T", "SDG"], "T": ["S", "TDG"], "SDG": ["S"],
             "TDG": ["T"], "H": ["SX"], "SX": ["H"], "RX": ["RY"], "RY": ["RX", "RZ"], "RZ": ["RX"], "CX": ["CZ"],
             "CZ": ["CX"]}
NAMES = {"SDG": "S†", "TDG": "T†", "SX": "√X"}


def gate_name(g: str) -> str:
    return NAMES.get(g, g)


def angle(v: float) -> str:
    for num, den in ((1, 1), (1, 2), (1, 4), (1, 8), (3, 4), (3, 2), (1, 3), (2, 3)):
        for sign in (1, -1):
            if abs(v - sign * math.pi * num / den) < 1e-6:
                s = "-" if sign < 0 else ""
                return f"{s}{'' if num == 1 else num}π{'' if den == 1 else '/' + str(den)}"
    return f"{v:.3f}"


def describe(op: dict[str, Any]) -> str:
    g = gate_name(op["gate"])
    if op.get("controls"):
        p = f"({angle(op['params'][0])})" if op.get("params") else ""
        return f"{g}{p} q{','.join(map(str, op['controls']))}→q{op['targets'][0]}"
    p = f"({angle(op['params'][0])})" if op.get("params") else ""
    return f"{g}{p} on q{', q'.join(map(str, op['targets']))}"


@lru_cache(maxsize=None)
def _example(name: str) -> str:
    return (EXAMPLES_DIR / "specs" / f"{name}.json").read_text(encoding="utf-8")


def _load(name: str) -> dict[str, Any]:
    if name == "qaoa_party":  # the six-guest dinner party from the QAOA lab, one layer at its tuned angles
        from qcanvas.qaoa import qaoa_spec

        edges = [(0, 1), (0, 2), (1, 2), (1, 4), (2, 3), (3, 4), (3, 5), (4, 5)]
        d = qaoa_spec(6, edges, [0.582], [0.338])
        d["metadata"] = {"title": "QAOA: split the party (1 layer)", "origin": "manual"}
    else:
        d = json.loads(_example(name))
    for op in d["operations"]:
        op.setdefault("controls", [])
        op.setdefault("params", [])
        op.pop("source", None)
    return d


def _dist(spec: dict[str, Any]) -> Distribution | None:
    try:
        return ideal_distribution(parse_spec(spec))
    except Exception:  # noqa: BLE001 - an edit that makes the spec invalid is simply not a fix
        return None


def _same(p: Distribution, q: Distribution) -> bool:
    return total_variation_distance(p, q) < SAME


def _edit(spec: dict[str, Any], i: int, op: dict[str, Any] | None) -> dict[str, Any]:
    ops = [dict(o) for o in spec["operations"]]
    if op is None:
        del ops[i]
    else:
        ops[i] = op
    return {**spec, "operations": ops}


def _with(op: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return {**op, **kw}


# ---------------------------------------------------------------- planting a bug

@dataclass
class Bug:
    kind: str
    index: int  # in the broken circuit
    label: str
    detail: str


def _uncontrolled(op: dict[str, Any]) -> bool:
    """A one-qubit gate, possibly written once for several wires."""
    return op["gate"] in PLAIN + ROTATION and not op["controls"]


def _single(op: dict[str, Any]) -> bool:
    return _uncontrolled(op) and len(op["targets"]) == 1


def _plant(spec: dict[str, Any], rng: random.Random) -> tuple[dict[str, Any], Bug] | None:
    n = spec["num_qubits"]
    ops = spec["operations"]
    idx = [i for i, o in enumerate(ops) if o["gate"] not in ("BARRIER", "MEASURE")]
    kind = rng.choice(["wrong_qubit", "flipped", "lookalike", "angle", "extra"])
    i = rng.choice(idx)
    op = ops[i]
    if kind == "wrong_qubit" and _single(op) and n > 1:
        q = rng.choice([x for x in range(n) if x != op["targets"][0]])
        return _edit(spec, i, _with(op, targets=[q])), Bug(kind, i, "a gate on the wrong wire",
                                                           f"{describe(op)} was put on q{q}")
    if kind == "flipped" and op["gate"] in ("CX", "CCX") and op["controls"]:
        c = op["controls"][-1]
        new = _with(op, controls=op["controls"][:-1] + [op["targets"][0]], targets=[c])
        return _edit(spec, i, new), Bug(kind, i, "control and target swapped",
                                        f"{describe(op)} was wired as {describe(new)}")
    if kind == "lookalike" and op["gate"] in LOOKALIKE and (op["gate"] not in ("CX", "CZ") or len(op["controls"]) == 1):
        g = rng.choice(LOOKALIKE[op["gate"]])
        return _edit(spec, i, _with(op, gate=g)), Bug(kind, i, "a look-alike gate",
                                                      f"{gate_name(op['gate'])} was written as {gate_name(g)}")
    if kind == "angle" and op.get("params"):
        v = op["params"][0]
        new_v, how = (-v, "the sign flipped") if rng.random() < 0.5 else (2 * v, "doubled")
        new = _with(op, params=[new_v] + op["params"][1:])
        return _edit(spec, i, new), Bug(kind, i, "a slip in an angle",
                                        f"{describe(op)} had its angle {how}: {angle(new_v)}")
    if kind == "extra":
        g, q = rng.choice(["X", "H", "Z", "X"]), rng.randrange(n)
        new = {"gate": g, "targets": [q], "controls": [], "params": []}
        ops2 = [dict(o) for o in ops]
        ops2.insert(i, new)
        return {**spec, "operations": ops2}, Bug(kind, i, "a stray extra gate", f"an extra {g} on q{q} slipped in")
    return None


class BugRound(BaseModel):
    id: str
    level: int
    level_label: str
    seed: int
    title: str
    spec: dict[str, Any]  # the broken circuit (no notes: they would describe the right one)
    intended: Distribution
    observed: dict[str, int]
    shots: int
    gates: int  # operations a player can click


@lru_cache(maxsize=256)
def _round(level: int, seed: int) -> tuple[BugRound, Bug, dict[str, Any], "Search"]:
    if level not in LEVELS:
        raise ValueError("level must be 1, 2 or 3")
    rng = random.Random(level * 1_000_003 + seed)
    pool = LEVELS[level][1]
    order = pool[:]
    rng.shuffle(order)
    for attempt in range(400):
        name = order[attempt // 40 % len(order)]  # forty tries per circuit, so small circuits get their turn
        good = _load(name)
        planted = _plant(good, rng)
        if planted is None:
            continue
        bad, bug = planted
        want, got = _dist(good), _dist(bad)
        if want is None or got is None or total_variation_distance(want, got) < MIN_TVD:
            continue
        gates = sum(o["gate"] not in ("BARRIER", "MEASURE") for o in bad["operations"])
        start = time.perf_counter()
        fixes, checked = _fixes(bad, want)
        found = Search(checked=checked, seconds=time.perf_counter() - start, fixes=fixes,
                       culprits=sorted({f.index for f in fixes}))
        if len(found.culprits) > max(1, MAX_SHARE[level] * gates):
            continue
        keys = sorted(got)
        sample = np.random.default_rng(seed).multinomial(SHOTS, [got[k] for k in keys])
        observed = {k: int(c) for k, c in zip(keys, sample) if c}
        shown = {**bad, "metadata": {"title": f"{good['metadata'].get('title', name)} (one gate is wrong)",
                                     "origin": "manual"}}
        title = good["metadata"].get("title", name)
        rnd = BugRound(id=f"{level}-{seed}", level=level, level_label=LEVELS[level][0], seed=seed, title=title,
                       spec=shown, intended=want, observed=observed, shots=SHOTS, gates=gates)
        return rnd, bug, good, found
    raise RuntimeError("could not plant a visible bug")


def bug_round(level: int, seed: int) -> BugRound:
    return _round(level, seed)[0]


# ---------------------------------------------------------------- the machine's search

class Fix(BaseModel):
    index: int
    edit: str


class Search(BaseModel):
    checked: int
    seconds: float
    fixes: list[Fix]
    culprits: list[int]


def _candidates(op: dict[str, Any], n: int):
    g, t, c, p = op["gate"], op["targets"], op["controls"], op.get("params", [])
    yield None, "delete it"
    if _uncontrolled(op):
        for h in (PLAIN if g in PLAIN else ROTATION):
            if h != g:
                yield _with(op, gate=h), f"make it {gate_name(h)}"
    if _single(op):
        for q in range(n):
            if q != t[0]:
                yield _with(op, targets=[q]), f"move it to q{q}"
    if g in ("CX", "CZ") and len(c) == 1:
        yield _with(op, gate="CZ" if g == "CX" else "CX"), f"make it {'CZ' if g == 'CX' else 'CX'}"
    if g in ("CX", "CCX", "CP") and c:
        yield _with(op, controls=c[:-1] + [t[0]], targets=[c[-1]]), "swap control and target"
        for q in range(n):
            if q not in c and q != t[0]:
                yield _with(op, targets=[q]), f"target q{q}"
                yield _with(op, controls=c[:-1] + [q]), f"control from q{q}"
    if p:
        v = p[0]
        for nv, how in ((-v, "flip the angle's sign"), (2 * v, "double the angle"), (v / 2, "halve the angle")):
            if abs(nv - v) > 1e-12:
                yield _with(op, params=[nv] + p[1:]), f"{how} ({angle(nv)})"


def _fixes(spec: dict[str, Any], intended: Distribution) -> tuple[list[Fix], int]:
    """Every single-gate edit of ``spec`` that gives exactly ``intended``; also how many edits were tried."""
    spec = {**spec, "metadata": {"origin": "manual"}}
    n = spec["num_qubits"]
    checked, fixes = 0, []
    for i, op in enumerate(spec["operations"]):
        if op["gate"] in ("BARRIER", "MEASURE"):
            continue
        for new, how in _candidates(op, n):
            checked += 1
            d = _dist(_edit(spec, i, new))
            if d is not None and _same(d, intended):
                fixes.append(Fix(index=i, edit=how))
    return fixes, checked


def search(level: int, seed: int) -> Search:
    """The machine's turn: every single-gate edit of the broken circuit, kept if it restores the intended odds
    (run once when the round is planted, which also checks the round is fair)."""
    return _round(level, seed)[3]


class Verdict(BaseModel):
    correct: bool
    index: int
    planted: int
    label: str
    detail: str
    fixed: dict[str, Any]
    machine: Search


def judge(level: int, seed: int, index: int) -> Verdict:
    rnd, bug, good, found = _round(level, seed)
    return Verdict(correct=index in found.culprits, index=index, planted=bug.index, label=bug.label,
                   detail=bug.detail, fixed=good, machine=found)


def muse_facts(level: int, seed: int) -> dict[str, Any]:
    """What Muse Spark gets: the broken circuit with indices, the intended odds and the observed counts."""
    rnd = bug_round(level, seed)
    ops = [{"index": i, **{k: v for k, v in o.items() if v not in ([], None)}}
           for i, o in enumerate(rnd.spec["operations"])]
    return {"title": rnd.title, "num_qubits": rnd.spec["num_qubits"], "operations": ops,
            "measured": [[m["qubit"], m["clbit"]] for m in rnd.spec.get("measurements", [])],
            "intended_probabilities": {k: round(v, 4) for k, v in sorted(rnd.intended.items())},
            "observed_counts": dict(sorted(rnd.observed.items())), "shots": rnd.shots}
