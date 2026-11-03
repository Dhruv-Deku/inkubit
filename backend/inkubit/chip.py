"""Real IBM chips from their calibration: the heavy-hex map, and where on a chip a circuit should run.

The snapshots (scripts/device_snapshot.py, data/devices/<name>.json) hold every qubit's T1, T2, readout errors and
one-qubit gate error and every coupler's two-qubit gate error, as the device reported them.

Placement advisor: the qubits a circuit's two-qubit gates connect form a small graph; every way of embedding it in the
chip's coupling graph (VF2 subgraph isomorphism, rustworkx) is a candidate patch, and each is scored by the chance that
no gate or readout fails: the product of (1 - error) over every two-qubit gate on its coupler (a CX is one native CZ,
a CP two, a SWAP three), every one-qubit gate on its qubit and every measured qubit's readout. Decoherence while a qubit
idles is not included; the score ranks patches, it is not a fidelity prediction. Qubits used only by one-qubit gates
take the best free qubits next to the patch. Circuits whose graph does not embed (a Toffoli's triangle; heavy-hex has
no triangles) need routing, and the advisor says so instead of guessing.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from inkubit.spec import CircuitSpec

DEVICES = Path(__file__).resolve().parent / "data" / "devices"
TWO_Q_COST = {"CX": 1, "CZ": 1, "CP": 2, "SWAP": 3}
UNUSABLE = 0.5  # IBM reports a broken coupler or qubit with an error near 1
MAX_EMBEDDINGS = 200_000
TIME_LIMIT_S = 2.0


def device_names() -> list[str]:
    return sorted(p.stem for p in DEVICES.glob("*.json"))


@lru_cache(maxsize=8)
def load(name: str) -> dict[str, Any]:
    path = DEVICES / f"{name}.json"
    if not path.exists() or path.parent != DEVICES:
        raise KeyError(name)
    d = json.loads(path.read_text(encoding="utf-8"))
    d["coords"] = coordinates(d["num_qubits"], [tuple(map(int, k.split("-"))) for k in d["edges"]])
    return d


def coordinates(n: int, edges: list[tuple[int, int]]) -> list[tuple[float, float]]:
    """Heavy-hex drawing: runs of consecutive qubits joined by couplers are rows; a lone qubit is a bridge, drawn
    between the row qubits it couples."""
    adj: dict[int, set[int]] = {q: set() for q in range(n)}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    pos: dict[int, tuple[float, float]] = {}
    row, start = 0, 0
    for q in range(1, n + 1):
        if q == n or q - 1 not in adj[q]:
            if q - start > 1:
                for i, r in enumerate(range(start, q)):
                    pos[r] = (float(i), 2.0 * row)
                row += 1
            start = q
    for q in range(n):
        if q not in pos:
            near = [pos[m] for m in adj[q] if m in pos]
            pos[q] = (sum(x for x, _ in near) / len(near), sum(y for _, y in near) / len(near)) if near else (0.0, -2.0)
    return [pos[q] for q in range(n)]


def summary(d: dict[str, Any]) -> dict[str, Any]:
    """Medians of the device, the shape of the fleet table."""
    def med(xs):
        xs = [x for x in xs if x is not None and x < UNUSABLE]
        return statistics.median(xs) if xs else None

    qs = d["qubits"]
    return {"device": d["device"], "processor": d["processor"], "num_qubits": d["num_qubits"],
            "couplers": len(d["edges"]), "taken_utc": d["taken_utc"], "calibrated_utc": d["calibrated_utc"],
            "pending_jobs": d["pending_jobs"], "dynamic_circuits": d["dynamic_circuits"],
            "two_qubit_error": med(d["edges"].values()), "sx_error": med(q["sx_error"] for q in qs),
            "readout_error": med([(q["p01"] + q["p10"]) / 2 for q in qs if q["p01"] is not None and q["p10"] is not None]),
            "t1_us": statistics.median(q["t1_us"] for q in qs if q["t1_us"]),
            "t2_us": statistics.median(q["t2_us"] for q in qs if q["t2_us"]),
            "unusable_couplers": sum(e >= UNUSABLE for e in d["edges"].values())}


class Patch(BaseModel):
    qubits: list[int]  # physical qubit for circuit qubit 0, 1, ...
    success: float  # chance that no gate or readout fails (decoherence while idle not included)


class Advice(BaseModel):
    device: str
    ok: bool
    note: str
    candidates: int = 0
    best: Patch | None = None
    median: Patch | None = None
    worst: Patch | None = None
    seconds: float = 0.0


def _readout(q: dict[str, Any]) -> float:
    if q["p01"] is None or q["p10"] is None:
        return 1.0
    return (q["p01"] + q["p10"]) / 2


def advise(spec: CircuitSpec, name: str) -> Advice:
    import rustworkx as rx

    t0 = time.perf_counter()
    d = load(name)
    n = spec.num_qubits
    two: dict[tuple[int, int], int] = {}
    one = [0] * n
    for op in spec.operations:
        qs = [*op.controls, *op.targets]
        if op.gate in TWO_Q_COST:
            key = (min(qs), max(qs))
            two[key] = two.get(key, 0) + TWO_Q_COST[op.gate]
        elif op.gate == "CCX":
            return Advice(device=name, ok=False, note="A Toffoli couples three qubits in a triangle, which heavy-hex "
                          "wiring does not have: it needs routing, so there is no direct placement to advise.")
        elif op.gate not in ("BARRIER", "MEASURE"):
            for q in op.targets:
                one[q] += 1
    measured = {q for q, _ in spec.measured_pairs()}
    linked = sorted({q for pair in two for q in pair})

    qinfo = d["qubits"]
    edge_err = {tuple(map(int, k.split("-"))): e for k, e in d["edges"].items()}
    chip = rx.PyGraph()
    chip.add_nodes_from(range(d["num_qubits"]))
    chip.add_edges_from_no_data([e for e, err in edge_err.items() if err < UNUSABLE])

    def single_cost(phys: int, q: int) -> float:
        info = qinfo[phys]
        sx, ro = info["sx_error"] or 1.0, _readout(info)
        if sx >= UNUSABLE or ro >= UNUSABLE:
            return -math.inf
        return one[q] * math.log1p(-sx) + (math.log1p(-ro) if q in measured else 0.0)

    def score(phys_of: dict[int, int]) -> float:
        s = sum(cnt * math.log1p(-edge_err[(min(phys_of[a], phys_of[b]), max(phys_of[a], phys_of[b]))])
                for (a, b), cnt in two.items())
        return s + sum(single_cost(p, q) for q, p in phys_of.items())

    patches: list[tuple[float, dict[int, int]]] = []
    if linked:
        pattern = rx.PyGraph()
        index = {q: i for i, q in enumerate(linked)}
        pattern.add_nodes_from(linked)
        pattern.add_edges_from_no_data([(index[a], index[b]) for a, b in two])
        seen: set[tuple[int, ...]] = set()
        for k, mapping in enumerate(rx.vf2_mapping(chip, pattern, subgraph=True, induced=False, id_order=False)):
            phys_of = {linked[pat]: phys for phys, pat in mapping.items()}
            key = tuple(phys_of[q] for q in linked)
            if key not in seen:
                seen.add(key)
                patches.append((score(phys_of), phys_of))
            if k >= MAX_EMBEDDINGS or time.perf_counter() - t0 > TIME_LIMIT_S:
                break
        if not patches:
            return Advice(device=name, ok=False, seconds=round(time.perf_counter() - t0, 2),
                          note="The circuit's two-qubit gates form a graph the chip's wiring does not contain (a "
                               "qubit with more than three partners, or a cycle): it needs routing.")
    else:
        patches = [(0.0, {})]
    lonely = [q for q in range(n) if q not in linked]

    def complete(phys_of: dict[int, int]) -> tuple[float, dict[int, int]]:
        """Give each qubit with no two-qubit gate the best free qubit (it needs no coupler)."""
        used = set(phys_of.values())
        out = dict(phys_of)
        for q in lonely:
            best = max((p for p in range(d["num_qubits"]) if p not in used), key=lambda p: single_cost(p, q))
            out[q] = best
            used.add(best)
        return score(out), out

    patches = [complete(p) for _, p in patches]
    patches = [(s, p) for s, p in patches if s > -math.inf]
    patches.sort(key=lambda sp: -sp[0])
    pick = lambda sp: Patch(qubits=[sp[1][q] for q in range(n)], success=round(math.exp(sp[0]), 6))  # noqa: E731
    return Advice(device=name, ok=True, candidates=len(patches), best=pick(patches[0]),
                  median=pick(patches[len(patches) // 2]), worst=pick(patches[-1]),
                  seconds=round(time.perf_counter() - t0, 2),
                  note=(f"{len(patches):,} placements on {name}'s working couplers; scored by the chance that no gate or "
                        "readout fails (idle decoherence not included)"))
