"""Distributed quantum computer: one circuit, two small chips, a quantum link between them.

1. The circuit is compiled to CX and one-qubit gates (Qiskit, level 1).
2. Every way to place the qubits on chip A and chip B (within their sizes) is tried; the split with the fewest CNOTs
   that cross between the chips wins, against the naive split (first half on A).
3. A crossing CNOT is done by gate teleportation (Eisert et al., 2000): one shared Bell pair, a local CNOT on each
   chip, two measurements and one classical message each way. With a Werner pair of fidelity F the result is the
   ideal CNOT followed by exactly one of X on the target, Z on the control, or both, each with probability (1 - F)/3;
   a flipped ancilla readout adds X on the target or Z on the control. The two local CNOTs are charged as two-qubit
   depolarizing noise at twice the preset's rate on the pair. While the messages travel (twice the distance at the
   speed of light in the medium) every data qubit idles under T1/T2 relaxation.
4. F and the pair rate come from the network planner's model (D12) for the link. All of it is evolved as an exact
   density matrix. The score is the process fidelity: how faithfully the chips carry out the whole circuit for
   every possible input, computed exactly by running it on one half of n maximally entangled pairs (so up to 5
   qubits). Scoring one output state would mislead: a qubit that relaxes to 0 mid-circuit can be steered back near
   the right answer by the gates that follow. The same circuit on one big chip is the reference; 1/4^n is chance.
Assumptions are spelled out on the page: pairs are generated just in time, so the pair rate sets the time per run.
"""

from __future__ import annotations

import itertools
import math
from functools import lru_cache
from typing import Any

import numpy as np
from pydantic import BaseModel
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import DensityMatrix, Kraus, Operator, SuperOp
from qiskit_aer.noise import thermal_relaxation_error

from qcanvas.insights.circuit import gate_channels
from qcanvas.network.model import simulate
from qcanvas.sim.noise import get_preset
from qcanvas.spec.models import CircuitSpec, NetworkSpec
from qcanvas.verify.expected import append_operation

MAX_QUBITS = 5
FIBER_KM_S, AIR_KM_S = 2.0e5, 3.0e5
SWEEP_KM = [0.01, 0.1, 0.3, 1, 3, 10, 100]
MEMORY_T_US = 1e6  # long-lived memory qubits for the comparison curve: T1 = T2 = 1 s (trapped-ion class)


class Link(BaseModel):
    label: str
    medium: str
    distance_km: float
    pair_rate_hz: float
    fidelity: float
    latency_us: float  # waiting per remote CNOT: a message each way


class Option(BaseModel):
    link: Link
    fidelity: float | None  # state fidelity; None when the link gives no usable entanglement
    fidelity_memory: float | None
    seconds_per_run: float | None
    note: str = ""


class Split(BaseModel):
    chip_a: list[int]
    chip_b: list[int]
    remote: int
    remote_ops: list[int]  # indices into the compiled circuit's operations


class DistributedResult(BaseModel):
    title: str
    num_qubits: int
    capacity: int
    compiled_ops: list[dict[str, Any]]
    local_cx: int
    best: Split
    naive: Split
    monolithic_fidelity: float
    floor: float  # process fidelity of a channel that ignores its input, 1/4^n
    options: list[Option]
    sweep: list[tuple[float, float | None, float | None]]
    finding: str


def compile_ops(spec: CircuitSpec) -> tuple[QuantumCircuit, list[dict[str, Any]]]:
    qc = QuantumCircuit(spec.num_qubits)
    for op in spec.operations:
        if op.gate not in ("MEASURE", "BARRIER"):
            append_operation(qc, op)
    t = transpile(qc, basis_gates=["cx", "rz", "sx", "x"], optimization_level=1, seed_transpiler=7)
    ops = []
    for inst in t.data:
        qs = [t.find_bit(q).index for q in inst.qubits]
        name = inst.operation.name
        if name == "cx":
            ops.append({"gate": "CX", "controls": [qs[0]], "targets": [qs[1]]})
        else:
            op: dict[str, Any] = {"gate": name.upper(), "targets": qs}
            if name == "rz":
                op["params"] = [float(inst.operation.params[0])]
            ops.append(op)
    return t, ops


def _remote(ops: list[dict[str, Any]], side: dict[int, int]) -> list[int]:
    return [i for i, o in enumerate(ops) if o["gate"] == "CX" and side[o["controls"][0]] != side[o["targets"][0]]]


def best_split(ops: list[dict[str, Any]], n: int, capacity: int) -> tuple[Split, Split]:
    """Exhaustive search over placements (n <= 8: at most 256), fewest crossing CNOTs, first such split."""
    def split(a: tuple[int, ...]) -> Split:
        side = {q: 0 if q in a else 1 for q in range(n)}
        r = _remote(ops, side)
        return Split(chip_a=sorted(a), chip_b=[q for q in range(n) if q not in a], remote=len(r), remote_ops=r)

    lo = max(1, n - capacity)
    candidates = [split(a) for size in range(lo, min(capacity, n - 1) + 1)
                  for a in itertools.combinations(range(n), size) if 0 in a]
    best = min(candidates, key=lambda s: (s.remote, abs(len(s.chip_a) - len(s.chip_b))))
    naive = split(tuple(range(min(capacity, math.ceil(n / 2)))))
    return best, naive


def _network(medium: str, km: float) -> dict[str, Any]:
    if medium == "satellite":
        from qcanvas.observatory import _satellite

        spec = _satellite(km)
        if spec is None:
            raise ValueError("the satellite is below 15 degrees for both stations at that distance")
        return spec
    return {"nodes": [{"id": "a", "type": "ground_station", "label": "Chip A"},
                      {"id": "b", "type": "ground_station", "label": "Chip B"}],
            "links": [{"from": "a", "to": "b", "medium": "fiber", "length_km": max(km, 0.001)}],
            "source": "a", "destination": "b"}


def link_for(medium: str, km: float) -> Link:
    end = simulate(NetworkSpec.model_validate(_network(medium, km))).end_to_end
    if medium == "satellite":
        from qcanvas.observatory import satellite_geometry

        slant, _ = satellite_geometry(km)
        latency = 2 * 2 * slant / AIR_KM_S * 1e6  # up to the satellite and down, each way
    else:
        latency = 2 * km / FIBER_KM_S * 1e6
    label = f"{km:g} km of fiber" if medium == "fiber" else f"satellite, stations {km:,.0f} km apart"
    return Link(label=label, medium=medium, distance_km=km, pair_rate_hz=float(f"{end.pair_rate_hz:.4g}"),
                fidelity=round(end.fidelity, 6), latency_us=round(latency, 3))


def _remote_channel(f: float, readout_flip: float, p2: float) -> SuperOp:
    e = (1 - f) / 3
    px, pz, pxz = e + readout_flip, e + readout_flip, e
    pi = max(0.0, 1 - px - pz - pxz)
    ops = [math.sqrt(pi) * Operator.from_label("II").data, math.sqrt(px) * Operator.from_label("XI").data,
           math.sqrt(pz) * Operator.from_label("IZ").data, math.sqrt(pxz) * Operator.from_label("XZ").data]
    pauli = SuperOp(Kraus(ops))
    from qcanvas.insights.circuit import _depolarizing

    return pauli.compose(_depolarizing(min(2 * p2, 0.9), 2))


def _bells(n: int) -> QuantumCircuit:
    """Data qubit q maximally entangled with reference qubit n + q."""
    qc = QuantumCircuit(2 * n)
    for q in range(n):
        qc.h(n + q)
        qc.cx(n + q, q)
    return qc


def ideal_state(n: int, ops: list[dict[str, Any]]) -> np.ndarray:
    """(U x I)|Phi>: the circuit applied to the data half of n Bell pairs."""
    from qiskit.quantum_info import Statevector

    from qcanvas.spec.models import Operation

    qc = _bells(n)
    for o in ops:
        append_operation(qc, Operation.model_validate(o))
    return Statevector(qc).data


def run_distributed(spec: CircuitSpec, ops: list[dict[str, Any]], remote: set[int], link: Link | None,
                    memory: bool = False) -> float:
    """Process fidelity of the circuit with the given crossing CNOTs over ``link`` (None: everything on one chip)."""
    from qiskit.quantum_info import Statevector

    preset = get_preset("realistic")
    channels = gate_channels(preset)
    n = spec.num_qubits
    rho = DensityMatrix(Statevector(_bells(n)))
    qc = QuantumCircuit(n)
    from qcanvas.spec.models import Operation

    for o in ops:
        append_operation(qc, Operation.model_validate(o))
    t1 = MEMORY_T_US if memory else preset.t1_us
    t2 = MEMORY_T_US if memory else preset.t2_us
    idle = None
    remote_ch = None
    if link is not None and remote:
        readout = (preset.readout_p01 + preset.readout_p10) / 2
        remote_ch = _remote_channel(link.fidelity, readout, preset.p2)
        if t1 and t2 and link.latency_us > 0:
            idle = SuperOp(thermal_relaxation_error(t1, min(t2, 2 * t1), link.latency_us).to_quantumchannel())
    for i, inst in enumerate(qc.data):
        qargs = [qc.find_bit(q).index for q in inst.qubits]
        rho = rho.evolve(inst.operation, qargs=qargs)
        if i in remote and remote_ch is not None:
            rho = rho.evolve(remote_ch, qargs=qargs)
            if idle is not None:
                for q in range(n):
                    rho = rho.evolve(idle, qargs=[q])
        elif len(qargs) in channels:
            rho = rho.evolve(channels[len(qargs)], qargs=qargs)
    psi = ideal_state(n, ops)
    return float(np.real(np.conj(psi) @ rho.data @ psi))


def _option(spec: CircuitSpec, ops: list[dict[str, Any]], best: Split, med: str, d: float) -> Option:
    try:
        link = link_for(med, d)
    except ValueError as err:
        return Option(link=Link(label=f"{med} {d:g} km", medium=med, distance_km=d, pair_rate_hz=0, fidelity=0,
                                latency_us=0), fidelity=None, fidelity_memory=None, seconds_per_run=None, note=str(err))
    if link.fidelity <= 0.5 or link.pair_rate_hz <= 0:
        return Option(link=link, fidelity=None, fidelity_memory=None, seconds_per_run=None,
                      note="the link's pairs are too noisy to carry a gate (fidelity at most 1/2)")
    remote = set(best.remote_ops)
    return Option(link=link, fidelity=round(run_distributed(spec, ops, remote, link), 6),
                  fidelity_memory=round(run_distributed(spec, ops, remote, link, memory=True), 6),
                  seconds_per_run=best.remote / link.pair_rate_hz if best.remote else 0.0)


def _parse(spec_json: str) -> CircuitSpec:
    import json

    from qcanvas.spec import parse_spec

    spec = parse_spec(json.loads(spec_json))
    if spec.kind != "circuit":
        raise ValueError("the distributed computer takes circuits")
    return spec


@lru_cache(maxsize=32)
def _plan(spec_json: str, capacity: int | None) -> tuple[list[dict[str, Any]], Split, Split, float, list[Option], int]:
    """Split, one-chip reference and the fiber sweep, once per circuit (the sweep runs on a thread pool)."""
    from concurrent.futures import ThreadPoolExecutor

    spec = _parse(spec_json)
    n = spec.num_qubits
    if not 2 <= n <= MAX_QUBITS:
        raise ValueError(f"the distributed computer takes circuits of 2 to {MAX_QUBITS} qubits")
    capacity = capacity or math.ceil(n / 2)
    if not 1 <= capacity < n or 2 * capacity < n:
        raise ValueError("each chip must be smaller than the circuit, and the two together big enough")
    _, ops = compile_ops(spec)
    best, naive = best_split(ops, n, capacity)
    with ThreadPoolExecutor(max_workers=4) as pool:
        mono_f = pool.submit(run_distributed, spec, ops, set(), None)
        sweep = list(pool.map(lambda d: _option(spec, ops, best, "fiber", d), SWEEP_KM))
        mono = mono_f.result()
    return ops, best, naive, mono, sweep, capacity


@lru_cache(maxsize=128)
def _chosen(spec_json: str, capacity: int | None, medium: str, km: float) -> Option:
    ops, best, _, _, _, _ = _plan(spec_json, capacity)
    return _option(_parse(spec_json), ops, best, medium, km)


def distribute(spec: CircuitSpec, capacity: int | None = None, medium: str = "fiber", km: float = 10.0
               ) -> DistributedResult:
    import json

    key = json.dumps(spec.model_dump(mode="json", by_alias=True, exclude_none=True), sort_keys=True)
    ops, best, naive, mono, sweep_opts, capacity = _plan(key, capacity)
    chosen = _chosen(key, capacity, medium, float(km))
    n = spec.num_qubits
    sweep = [(o.link.distance_km, o.fidelity, o.fidelity_memory) for o in sweep_opts]
    near, km1, km100 = sweep_opts[0], sweep_opts[SWEEP_KM.index(1)], sweep_opts[-1]
    finding = (f"The best split puts qubits {best.chip_a} on chip A and {best.chip_b} on chip B: {best.remote} CNOT"
               f"{'s' if best.remote != 1 else ''} cross the link, against {naive.remote} for the naive split. ")
    if best.remote and near.fidelity is not None:
        finding += (f"Even 10 m apart the remote gates cost process fidelity ({near.fidelity:.3f} against "
                    f"{mono:.3f} on one chip). Waiting for messages costs more with distance: at 1 km today's qubits "
                    f"keep {km1.fidelity:.3f} and long-lived memory qubits {km1.fidelity_memory:.3f}; at 100 km, "
                    f"{km100.fidelity:.3f} and {km100.fidelity_memory:.3f}.")
    elif not best.remote:
        finding += "No CNOT crosses the link, so the two chips work as one."
    return DistributedResult(title=spec.metadata.title or "Circuit", num_qubits=n, capacity=capacity,
                             compiled_ops=ops, local_cx=sum(1 for o in ops if o["gate"] == "CX") - best.remote,
                             best=best, naive=naive, monolithic_fidelity=round(mono, 6), floor=round(1 / 4 ** n, 6),
                             options=[chosen], sweep=sweep, finding=finding)
