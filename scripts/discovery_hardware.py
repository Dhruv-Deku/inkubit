"""Run the discovery lab's proven circuits on a real IBM quantum computer, next to the circuits they beat.

    .venv/Scripts/python scripts/discovery_hardware.py           # the least busy real device (a little free QPU time)
    .venv/Scripts/python scripts/discovery_hardware.py --fake    # rehearsal on a fake device (a calibration snapshot)
    .venv/Scripts/python scripts/discovery_hardware.py --errors  # recompute the error bars of the stored real run

For three goals of the discovery lab (GHZ on all 7 qubits of a heavy-hex patch, W on 4 qubits, Dicke D(4,2)) the lab's
search runs first (Muse Spark's layouts when the live models are configured, spanning trees and random layouts
always; seeded), and its best proven circuit goes to the chip together with the baselines it beat: the textbook circuit
and Qiskit's state preparation, compiled the same way.

- GHZ-7 runs on seven physical qubits wired like IBM's 7-qubit Falcon chips (an H-shaped patch of the heavy-hex lattice,
  chosen by Qiskit's noise-aware layout for the discovered circuit), and every variant is compiled onto that same patch,
  so the textbook circuit needs the SWAPs the lab counted. Its fidelity is estimated from the Z-basis odds plus a
  parity oscillation (inkubit.hardware); above 1/2 certifies genuine 7-qubit entanglement.
- W and Dicke run wherever Qiskit's level-3 compiler puts them on the chip; the outcome odds are compared with the ideal.

Each variant is also predicted by a digital twin of the device (NoiseModel.from_backend). Raw counts, no readout
correction, the same for every variant. Writes examples/discovery_hardware.json (or ..._rehearsal.json) and
docs/DISCOVERY_HARDWARE.md.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402
from qiskit import QuantumCircuit, transpile  # noqa: E402
from qiskit.transpiler import CouplingMap  # noqa: E402
from qiskit_aer import AerSimulator  # noqa: E402
from qiskit_aer.noise import NoiseModel  # noqa: E402

from inkubit.discovery import GOALS, Discovery, _pairs, goal_target, run_discovery  # noqa: E402
from inkubit.hardware import append_parity_basis, ghz_fidelity, hellinger_se, norm, parity, parity_phases, tvd  # noqa: E402
from inkubit.notation import dirac  # noqa: E402
from inkubit.spec import parse_spec  # noqa: E402
from inkubit.verify.expected import append_operation, ideal_distribution  # noqa: E402
from inkubit.verify.metrics import hellinger_fidelity  # noqa: E402

GOAL_IDS = ["ghz7_hex", "w4", "dicke42"]
SHOTS = 4096
TWIN_SHOTS = 20_000


def device(fake: bool):
    if fake:
        from qiskit_ibm_runtime.fake_provider import FakeSherbrooke

        return FakeSherbrooke()
    from qiskit_ibm_runtime import QiskitRuntimeService

    load_dotenv(ROOT / ".env")
    token = os.environ.get("IBM_QUANTUM_TOKEN")
    if not token:
        sys.exit("put IBM_QUANTUM_TOKEN=... in .env (IBM Quantum Platform API key), or run with --fake")
    service = QiskitRuntimeService(channel="ibm_quantum_platform", token=token,
                                   instance=os.environ.get("IBM_QUANTUM_INSTANCE") or None)
    return service.least_busy(operational=True, simulator=False, min_num_qubits=7)


def discover(goal_id: str) -> dict[str, Any]:
    """The lab's own search, as in the app: live models when configured, seeded heuristics always."""
    from inkubit.adapters.registry import get_models

    models = get_models()
    live = models.settings.provider == "meta" and models.settings.has_key
    goal = GOALS[goal_id]
    d = Discovery(goal)
    run_discovery(d, goal_target(goal), models.reasoning if live else None)
    if d.status != "done" or not d.result:
        sys.exit(f"discovery failed for {goal_id}: {d.error}")
    return d.result


def pick(result: dict[str, Any]) -> list[dict[str, Any]]:
    """The best proven discovery, then the baselines it beat."""
    entries = result["entries"]  # sorted by predicted fidelity, best first
    found = [e for e in entries if e["source"] not in ("textbook", "compiler")]
    base = [e for e in entries if e["source"] in ("textbook", "compiler")]
    return found[:1] + sorted(base, key=lambda e: e["cx"])


def state_circuit(raw: dict[str, Any]) -> tuple[Any, QuantumCircuit]:
    spec = parse_spec(raw)
    qc = QuantumCircuit(spec.num_qubits, spec.num_qubits)
    for op in spec.operations:
        append_operation(qc, op)
    return spec, qc


def measured(qc: QuantumCircuit, phi: float | None = None) -> QuantumCircuit:
    out = qc.copy()
    if phi is not None:
        append_parity_basis(out, phi)
    out.measure(range(out.num_qubits), range(out.num_qubits))
    return out


def two_qubit(qc: QuantumCircuit) -> int:
    return int(sum(v for k, v in qc.count_ops().items() if k in ("cx", "cz", "ecr")))


def used_qubits(qc: QuantumCircuit) -> set[int]:
    return {qc.find_bit(q).index for inst in qc.data if inst.operation.name not in ("barrier",) for q in inst.qubits}


def add_errors(out: dict[str, Any]) -> None:
    """Shot-noise standard errors, and for each goal the discovery's margin over its best baseline in standard errors."""
    shots = out["shots"]
    for g in out["goals"]:
        n = g["num_qubits"]
        for v in g["variants"]:
            v["outcome_se"] = hellinger_se(v["ideal"], v["measured"], shots)
            if v.get("parities"):
                v["ghz"] = ghz_fidelity(v["measured"], v["parities"], n, shots)
        found = next(v for v in g["variants"] if v["source"] not in ("textbook", "compiler"))
        key = (lambda v: (v["ghz"]["fidelity"], v["ghz"]["se"])) if found.get("ghz") else (lambda v: (v["outcome_fidelity"], v["outcome_se"]))  # noqa: E731
        rivals = [v for v in g["variants"] if v["source"] in ("textbook", "compiler") and (v.get("ghz") or not found.get("ghz"))]
        best = max(rivals, key=lambda v: key(v)[0])
        (a, sa), (b, sb) = key(found), key(best)
        g["comparison"] = {"metric": "GHZ fidelity" if found.get("ghz") else "outcome fidelity", "discovered": a,
                           "baseline": b, "baseline_label": best["label"], "margin": a - b,
                           "z": (a - b) / (sa**2 + sb**2) ** 0.5}


def main() -> None:
    if "--errors" in sys.argv:
        path = ROOT / "examples" / "discovery_hardware.json"
        out = json.loads(path.read_text(encoding="utf-8"))
        add_errors(out)
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        write_doc(out)
        for g in out["goals"]:
            c = g["comparison"]
            print(f"{g['id']}: {c['metric']} {c['discovered']:.3f} vs {c['baseline']:.3f} ({c['baseline_label']}), z = {c['z']:.1f}")
        return
    fake = "--fake" in sys.argv
    backend = device(fake)
    print(f"device: {backend.name} ({'rehearsal on a fake device' if fake else 'real hardware'})", flush=True)
    basis2q = next(g for g in ("cz", "ecr", "cx") if g in backend.operation_names)
    basis = [basis2q, "rz", "sx", "x"]

    plan: list[dict[str, Any]] = []  # one entry per circuit sent to the chip
    goals_out: list[dict[str, Any]] = []
    for gid in GOAL_IDS:
        t0 = time.time()
        result = discover(gid)
        goal = GOALS[gid]
        print(f"{gid}: {result['finding']} ({time.time() - t0:.0f} s)", flush=True)
        variants = pick(result)
        g_out = {"id": gid, "title": goal.title, "target": result["target"], "finding": result["finding"],
                 "num_qubits": goal.num_qubits, "variants": []}
        patch = None
        if goal.coupling:  # GHZ-7: one H-shaped patch of the chip, the same for every variant
            cmap = CouplingMap([list(p) for p in _pairs(goal)])
            logical = lambda qc: transpile(qc, basis_gates=basis, coupling_map=cmap, optimization_level=3,  # noqa: E731
                                           seed_transpiler=7)
            first = transpile(logical(measured(state_circuit(variants[0]["spec"])[1])), backend,
                              optimization_level=3, seed_transpiler=7)
            patch = first.layout.initial_index_layout(filter_ancillas=True)[: goal.num_qubits]
            g_out["patch"] = patch
            print(f"  patch of the chip: physical qubits {patch}", flush=True)
            on_chip = lambda qc: transpile(logical(qc), backend, initial_layout=patch, optimization_level=1,  # noqa: E731
                                           seed_transpiler=7)
        else:
            on_chip = lambda qc: transpile(qc, backend, optimization_level=3, seed_transpiler=7)  # noqa: E731
        for vi, e in enumerate(variants):
            spec, qc = state_circuit(e["spec"])
            z = on_chip(measured(qc))
            if patch is not None and not used_qubits(z) <= set(patch):
                sys.exit(f"{e['label']}: compiled outside the patch {patch}")
            v = {"label": e["label"], "source": e["source"], "cx_logical": e["cx"], "two_qubit_gates": two_qubit(z),
                 "depth": z.depth(), "predicted_state_fidelity": e["noisy_fidelity"],
                 "predicted_outcome_fidelity": e["outcome_fidelity"], "ideal": ideal_distribution(spec)}
            g_out["variants"].append(v)
            plan.append({"goal": len(goals_out), "variant": vi, "phi": None, "circuit": z})
            ghz_parity = gid.startswith("ghz") and e["source"] != "compiler"  # 197 CNOTs: the Z basis says enough
            if ghz_parity:
                for phi in parity_phases(goal.num_qubits):
                    plan.append({"goal": len(goals_out), "variant": vi, "phi": phi, "circuit": on_chip(measured(qc, phi))})
            print(f"  {e['label']}: {e['cx']} CNOTs in the lab, {v['two_qubit_gates']} two-qubit gates on the chip"
                  f"{' + parity circuits' if ghz_parity else ''}", flush=True)
        goals_out.append(g_out)

    circuits = [p["circuit"] for p in plan]
    print(f"{len(circuits)} circuits, {SHOTS} shots each", flush=True)
    if fake:
        sim = AerSimulator.from_backend(backend)
        counts = [norm(sim.run(c, shots=SHOTS, seed_simulator=11).result().get_counts()) for c in circuits]
        job_id = "rehearsal"
    else:
        from qiskit_ibm_runtime import SamplerV2

        job = SamplerV2(mode=backend).run(circuits, shots=SHOTS)
        job_id = job.job_id()
        print(f"job {job_id} submitted; waiting in the queue...", flush=True)
        t0 = time.time()
        res = job.result()
        print(f"done after {time.time() - t0:.0f} s", flush=True)
        counts = [norm(r.join_data().get_counts()) for r in res]
    twin = AerSimulator(noise_model=NoiseModel.from_backend(backend))
    twin_counts = [norm(twin.run(c, shots=TWIN_SHOTS, seed_simulator=5).result().get_counts()) for c in circuits]

    for gi, g in enumerate(goals_out):
        n = g["num_qubits"]
        for vi, v in enumerate(g["variants"]):
            mine = [(p, c, t) for p, c, t in zip(plan, counts, twin_counts) if p["goal"] == gi and p["variant"] == vi]
            (_, z, zt), par = mine[0], mine[1:]
            v["measured"] = dict(sorted(z.items(), key=lambda kv: -kv[1])[:8])
            v["outcome_fidelity"] = hellinger_fidelity(v["ideal"], z)
            v["twin_outcome_fidelity"] = hellinger_fidelity(v["ideal"], zt)
            v["tvd"] = tvd(v["ideal"], z)
            if par:
                v["ghz"] = ghz_fidelity(z, [parity(c) for _, c, _ in par], n)
                v["twin_ghz"] = ghz_fidelity(zt, [parity(t) for _, _, t in par], n)
                v["parities"] = [round(parity(c), 4) for _, c, _ in par]
            extra = f", GHZ fidelity {v['ghz']['fidelity']:.3f} (twin {v['twin_ghz']['fidelity']:.3f})" if par else ""
            print(f"{g['id']:9s} {v['label'][:44]:44s} 2q {v['two_qubit_gates']:4d}  outcome fidelity "
                  f"{v['outcome_fidelity']:.3f} (twin {v['twin_outcome_fidelity']:.3f}){extra}", flush=True)
    out = {"device": backend.name, "rehearsal": fake, "job_id": job_id, "shots": SHOTS,
           "date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "circuits": len(circuits),
           "goals": goals_out}
    add_errors(out)
    path = ROOT / "examples" / ("discovery_hardware_rehearsal.json" if fake else "discovery_hardware.json")
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    if not fake:
        write_doc(out)
    print(f"wrote {path}")


def write_doc(out: dict[str, Any]) -> None:
    lines = ["# AI-discovered circuits on a real quantum computer", "",
             f"The discovery lab's best proven circuit for each goal ran on **{out['device']}** (IBM Quantum, job "
             f"`{out['job_id']}`, {out['shots']} shots per circuit, {out['circuits']} circuits, {out['date_utc']}) next to the "
             "baselines it beat, with `scripts/discovery_hardware.py`. Raw counts, no readout correction. The digital twin "
             "is Qiskit Aer's noise model built from the device's calibration.", ""]
    for g in out["goals"]:
        lines += [f"## {g['title']}", "", f"Target {g['target']}." + (f" Physical qubits {g['patch']}, wired like a 7-qubit Falcon chip; every variant compiled onto them." if g.get("patch") else ""), "",
                  "| Circuit | CNOTs in the lab | Two-qubit gates on the chip | Outcome fidelity (chip) | (twin) | GHZ fidelity (chip) | (twin) |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for v in g["variants"]:
            gf = f"{v['ghz']['fidelity']:.3f}" if v.get("ghz") else "–"
            gt = f"{v['twin_ghz']['fidelity']:.3f}" if v.get("twin_ghz") else "–"
            lines.append(f"| {v['label']} | {v['cx_logical']} | {v['two_qubit_gates']} | {v['outcome_fidelity']:.3f} | "
                         f"{v['twin_outcome_fidelity']:.3f} | {gf} | {gt} |")
        lines.append("")
    (ROOT / "docs" / "DISCOVERY_HARDWARE.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
