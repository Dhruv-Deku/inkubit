"""Two experiments on a real IBM quantum computer: does noise-aware placement matter, and does teleportation work
with real mid-circuit measurement and feed-forward?

    .venv/Scripts/python scripts/ibm_experiments.py [device]     # default ibm_fez; a little free QPU time
    .venv/Scripts/python scripts/ibm_experiments.py --fake       # rehearsal on Aer with a fake device's noise

1. Placement. The advisor (inkubit.chip) scores every way of putting a 5-qubit GHZ chain on the chip from the
   device's own calibration snapshot (scripts/device_snapshot.py, taken just before). The best-, median- and
   worst-scored placements run on exactly those physical qubits (initial layout, no re-layout), and each one's GHZ
   fidelity is measured from Z-basis odds plus a parity oscillation over 8 phases (inkubit.hardware), with error bars.
2. Teleportation with dynamic circuits. A qubit is teleported: Bell measurement in the middle of the circuit, then X and
   Z on the receiver only when the measured bits say so (if_test, decided on the chip in real time). The six axis states
   |0⟩, |1⟩, |±⟩, |±i⟩ are sent and the receiver's Bloch vector is measured in X, Y and Z; for a qubit channel the
   average fidelity over these six equals the average over all pure states, so it compares directly with 2/3, the best
   any classical scheme (measure, send bits, prepare) can do. A control run applies no corrections.

Raw counts, no readout correction. The digital twin (Aer with NoiseModel.from_backend) predicts both. Writes
examples/ibm_experiments.json (or ..._rehearsal.json) and docs/IBM_EXPERIMENTS.md.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, transpile  # noqa: E402
from qiskit_aer import AerSimulator  # noqa: E402
from qiskit_aer.noise import NoiseModel  # noqa: E402

from inkubit.chip import advise, load  # noqa: E402
from inkubit.hardware import append_parity_basis, ghz_fidelity, norm, parity, parity_phases  # noqa: E402
from inkubit.spec import parse_spec  # noqa: E402

GHZ_N = 5
SHOTS_GHZ = 4096
SHOTS_TELE = 2048
AXIS = {"|0⟩": (0, 0, 1), "|1⟩": (0, 0, -1), "|+⟩": (1, 0, 0), "|−⟩": (-1, 0, 0), "|+i⟩": (0, 1, 0), "|−i⟩": (0, -1, 0)}


def device(name: str, fake: bool):
    if fake:
        from qiskit_ibm_runtime import fake_provider

        return getattr(fake_provider, "FakeFez", fake_provider.FakeSherbrooke)()
    from dotenv import load_dotenv
    from qiskit_ibm_runtime import QiskitRuntimeService

    load_dotenv(ROOT / ".env")
    token = os.environ.get("IBM_QUANTUM_TOKEN")
    if not token:
        sys.exit("put IBM_QUANTUM_TOKEN=... in .env, or run with --fake")
    return QiskitRuntimeService(channel="ibm_quantum_platform", token=token,
                                instance=os.environ.get("IBM_QUANTUM_INSTANCE") or None).backend(name)


def ghz_spec() -> Any:
    ops = [{"gate": "H", "targets": [0]}] + [{"gate": "CX", "controls": [i], "targets": [i + 1]} for i in range(GHZ_N - 1)]
    return parse_spec({"kind": "circuit", "num_qubits": GHZ_N, "num_clbits": GHZ_N, "operations": ops,
                       "measurements": [{"qubit": q, "clbit": q} for q in range(GHZ_N)]})


def ghz_circuit(phi: float | None) -> QuantumCircuit:
    qc = QuantumCircuit(GHZ_N, GHZ_N)
    qc.h(0)
    for i in range(GHZ_N - 1):
        qc.cx(i, i + 1)
    if phi is not None:
        append_parity_basis(qc, phi)
    qc.measure(range(GHZ_N), range(GHZ_N))
    return qc


def prepare(qc: QuantumCircuit, q: int, label: str) -> None:
    """Prepare one of the six axis states on qubit q."""
    if label == "|1⟩":
        qc.x(q)
    elif label in ("|+⟩", "|−⟩", "|+i⟩", "|−i⟩"):
        if label in ("|−⟩", "|−i⟩"):
            qc.x(q)
        qc.h(q)
        if label in ("|+i⟩", "|−i⟩"):
            qc.s(q)


def teleport(label: str, basis: str, feed_forward: bool) -> QuantumCircuit:
    q = QuantumRegister(3, "q")
    alice, bob = ClassicalRegister(2, "alice"), ClassicalRegister(1, "bob")
    qc = QuantumCircuit(q, alice, bob)
    prepare(qc, 0, label)
    qc.h(1)
    qc.cx(1, 2)
    qc.cx(0, 1)
    qc.h(0)
    qc.measure(0, alice[0])
    qc.measure(1, alice[1])
    if feed_forward:
        with qc.if_test((alice[1], 1)):
            qc.x(2)
        with qc.if_test((alice[0], 1)):
            qc.z(2)
    if basis == "X":
        qc.h(2)
    elif basis == "Y":
        qc.sdg(2)
        qc.h(2)
    qc.measure(2, bob[0])
    return qc


def bob_odds(counts: dict[str, int]) -> dict[str, float]:
    """Keep the receiver's bit: Qiskit writes registers right to left, so 'bob alice' and bob is the leftmost."""
    out: dict[str, float] = {}
    total = sum(counts.values())
    for key, c in counts.items():
        b = key.split(" ")[0] if " " in key else key[0]
        out[b] = out.get(b, 0.0) + c / total
    return out


def bloch_fidelity(z: dict[str, dict[str, float]], ideal: tuple[int, int, int], shots: int) -> tuple[float, float, list[float]]:
    r, var = [], []
    for basis in ("X", "Y", "Z"):
        e = z[basis].get("0", 0.0) - z[basis].get("1", 0.0)
        r.append(e)
        var.append((1 - e * e) / shots)
    f = (1 + sum(a * b for a, b in zip(r, ideal))) / 2
    se = 0.5 * math.sqrt(sum((b * b) * v for b, v in zip(ideal, var)))
    return f, se, r


def main() -> None:
    fake = "--fake" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    name = args[0] if args else "ibm_fez"
    backend = device(name, fake)
    print(f"device: {backend.name} ({'rehearsal' if fake else 'real hardware'}); advisor uses the {name} snapshot "
          f"taken {load(name)['taken_utc']}", flush=True)

    advice = advise(ghz_spec(), name)
    patches = {"best": advice.best, "median": advice.median, "worst": advice.worst}
    plan: list[dict[str, Any]] = []
    for which, patch in patches.items():
        for phi in [None, *parity_phases(GHZ_N)]:
            t = transpile(ghz_circuit(phi), backend, initial_layout=patch.qubits, optimization_level=1, seed_transpiler=7)
            used = {t.find_bit(qb).index for inst in t.data for qb in inst.qubits if inst.operation.name != "barrier"}
            assert used <= set(patch.qubits), f"{which}: compiled outside its qubits"
            plan.append({"exp": "ghz", "which": which, "phi": phi, "circuit": t, "shots": SHOTS_GHZ})
        print(f"  GHZ-5 {which:6s} placement {patch.qubits}: advisor score {patch.success:.3f}", flush=True)

    chain = advise(parse_spec({"kind": "circuit", "num_qubits": 3, "num_clbits": 3, "operations": [
        {"gate": "H", "targets": [1]}, {"gate": "CX", "controls": [1], "targets": [2]},
        {"gate": "CX", "controls": [0], "targets": [1]}, {"gate": "H", "targets": [0]}],
        "measurements": [{"qubit": q, "clbit": q} for q in range(3)]}), name).best
    for ff in (True, False):
        for label in AXIS:
            for basis in ("X", "Y", "Z"):
                t = transpile(teleport(label, basis, ff), backend, initial_layout=chain.qubits, optimization_level=1,
                              seed_transpiler=7)
                plan.append({"exp": "teleport", "ff": ff, "state": label, "basis": basis, "circuit": t, "shots": SHOTS_TELE})
    print(f"  teleportation on qubits {chain.qubits} (the advisor's best 3-qubit chain), 6 states x 3 bases, "
          "with and without feed-forward", flush=True)

    circuits = [p["circuit"] for p in plan]
    print(f"{len(circuits)} circuits", flush=True)
    t0 = time.time()
    if fake:
        sim = AerSimulator.from_backend(backend)
        raw = [sim.run(p["circuit"], shots=p["shots"], seed_simulator=11).result().get_counts() for p in plan]
        job_id = "rehearsal"
    else:
        from qiskit_ibm_runtime import SamplerV2

        job = SamplerV2(mode=backend).run([(p["circuit"], None, p["shots"]) for p in plan])
        job_id = job.job_id()
        print(f"job {job_id} submitted; waiting in the queue...", flush=True)
        res = job.result()
        raw = []
        for p, r in zip(plan, res):
            raw.append(r.data.c.get_counts() if p["exp"] == "ghz" else
                       {f"{b} 00": c for b, c in r.data.bob.get_counts().items()})
        print(f"done after {time.time() - t0:.0f} s", flush=True)
    twin = AerSimulator(noise_model=NoiseModel.from_backend(backend))
    twin_raw = [twin.run(p["circuit"], shots=20_000, seed_simulator=5).result().get_counts() for p in plan]

    out: dict[str, Any] = {"device": backend.name, "rehearsal": fake, "job_id": job_id,
                           "date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "snapshot_utc": load(name)["taken_utc"], "circuits": len(plan)}
    ghz_rows = []
    for which, patch in patches.items():
        mine = [(p, c, t) for p, c, t in zip(plan, raw, twin_raw) if p["exp"] == "ghz" and p["which"] == which]
        z, zt = norm(mine[0][1]), norm(mine[0][2])
        par = [parity(norm(c)) for _, c, _ in mine[1:]]
        part = [parity(norm(t)) for _, _, t in mine[1:]]
        est = ghz_fidelity(z, par, GHZ_N, SHOTS_GHZ)
        tw = ghz_fidelity(zt, part, GHZ_N)
        ghz_rows.append({"placement": which, "qubits": patch.qubits, "advisor_score": patch.success,
                         "fidelity": est["fidelity"], "se": est["se"], "populations": est["populations"],
                         "coherence": est["coherence"], "twin_fidelity": tw["fidelity"]})
        print(f"GHZ-5 {which:6s} {patch.qubits}: fidelity {est['fidelity']:.3f} ± {est['se']:.3f} "
              f"(advisor {patch.success:.3f}, twin {tw['fidelity']:.3f})", flush=True)
    out["ghz"] = {"n": GHZ_N, "shots": SHOTS_GHZ, "candidates": advice.candidates, "rows": ghz_rows}

    tele = {}
    for ff in (True, False):
        rows = []
        for label, ideal in AXIS.items():
            mine = {p["basis"]: (c, t) for p, c, t in zip(plan, raw, twin_raw)
                    if p["exp"] == "teleport" and p["ff"] == ff and p["state"] == label}
            f, se, r = bloch_fidelity({b: bob_odds(c) for b, (c, _) in mine.items()}, ideal, SHOTS_TELE)
            ft, _, _ = bloch_fidelity({b: bob_odds(t) for b, (_, t) in mine.items()}, ideal, SHOTS_TELE)
            rows.append({"state": label, "fidelity": f, "se": se, "bloch": r, "twin_fidelity": ft})
        avg = sum(r["fidelity"] for r in rows) / len(rows)
        avg_se = math.sqrt(sum(r["se"] ** 2 for r in rows)) / len(rows)
        tele["feed_forward" if ff else "no_corrections"] = {"rows": rows, "average": avg, "se": avg_se,
                                                            "twin_average": sum(r["twin_fidelity"] for r in rows) / len(rows)}
        print(f"teleportation {'with feed-forward' if ff else 'without corrections'}: average fidelity {avg:.3f} ± "
              f"{avg_se:.3f} (classical limit 0.667)", flush=True)
    out["teleport"] = {"qubits": chain.qubits, "shots": SHOTS_TELE, "classical_limit": 2 / 3, **tele}
    path = ROOT / "examples" / ("ibm_experiments_rehearsal.json" if fake else "ibm_experiments.json")
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    if not fake:
        write_doc(out)
    print(f"wrote {path}")


def write_doc(out: dict[str, Any]) -> None:
    g, t = out["ghz"], out["teleport"]
    lines = ["# Experiments on a real IBM quantum computer", "",
             f"`scripts/ibm_experiments.py` on **{out['device']}** (job `{out['job_id']}`, {out['circuits']} circuits, "
             f"{out['date_utc']}; calibration snapshot {out['snapshot_utc']}). Raw counts, no readout correction.", "",
             f"## Placement: GHZ-{g['n']} on the advisor's best, median and worst qubits", "",
             f"The advisor scored {g['candidates']:,} placements from the calibration snapshot.", "",
             "| Placement | Physical qubits | Advisor score | Measured GHZ fidelity | Twin |", "| --- | --- | --- | --- | --- |"]
    for r in g["rows"]:
        lines.append(f"| {r['placement']} | {', '.join(map(str, r['qubits']))} | {r['advisor_score']:.3f} | "
                     f"{r['fidelity']:.3f} ± {r['se']:.3f} | {r['twin_fidelity']:.3f} |")
    lines += ["", f"## Teleportation with mid-circuit measurement and feed-forward (qubits {', '.join(map(str, t['qubits']))})", "",
              "| State | Fidelity with feed-forward | Without corrections |", "| --- | --- | --- |"]
    for a, b in zip(t["feed_forward"]["rows"], t["no_corrections"]["rows"]):
        lines.append(f"| {a['state']} | {a['fidelity']:.3f} ± {a['se']:.3f} | {b['fidelity']:.3f} ± {b['se']:.3f} |")
    ff, nc = t["feed_forward"], t["no_corrections"]
    lines += ["", f"Average over the six axis states (equal to the average over all states): **{ff['average']:.3f} ± "
              f"{ff['se']:.3f}** with feed-forward, {nc['average']:.3f} ± {nc['se']:.3f} without; the best classical scheme "
              "reaches 0.667."]
    (ROOT / "docs" / "IBM_EXPERIMENTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
