"""Run a few circuits on a real IBM quantum computer and compare the counts with Q-Canvas's predictions.

    pip install qiskit-ibm-runtime
    put IBM_QUANTUM_TOKEN=... in .env (and IBM_QUANTUM_INSTANCE=crn:... if your account has several instances)
    .venv/Scripts/python scripts/hardware_check.py           # the least busy real device (uses a little free QPU time)
    .venv/Scripts/python scripts/hardware_check.py --fake    # rehearsal on a fake device (a real calibration snapshot)

For each circuit (Bell pair, GHZ-3, Bernstein-Vazirani with secret 101, 2-qubit Grover): transpile for the device at
optimisation level 3, run 4096 shots with SamplerV2, and compare the measured odds with
  (a) the ideal odds,
  (b) Q-Canvas's generic "realistic" preset (the one the whole app uses), and
  (c) a digital twin: Qiskit Aer's noise model built from that device's own calibration (NoiseModel.from_backend),
      simulated on the same transpiled circuit.
Hellinger fidelity and total variation distance for each. A rehearsal is labelled as one everywhere: there the
"device" is itself a simulation, so it only checks the pipeline. Writes examples/hardware_runs.json and
docs/HARDWARE.md.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402
from qiskit import transpile  # noqa: E402
from qiskit_aer import AerSimulator  # noqa: E402
from qiskit_aer.noise import NoiseModel  # noqa: E402

from qcanvas.spec import parse_spec  # noqa: E402
from qcanvas.verify.expected import build_reference_circuit, ideal_distribution, noisy_distribution  # noqa: E402
from qcanvas.verify.metrics import hellinger_fidelity  # noqa: E402

CIRCUITS = ["bell", "ghz3", "bernstein_vazirani", "grover2"]
SHOTS = 4096


def tvd(p: dict[str, float], q: dict[str, float]) -> float:
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in set(p) | set(q))


def norm(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    return {k.replace(" ", ""): v / total for k, v in counts.items()}


def measured_circuit(spec):
    """The spec's gates plus its measurements (the reference circuit is the gate part only)."""
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(spec.num_qubits, spec.num_clbits)
    qc.compose(build_reference_circuit(spec), inplace=True)
    for q, c in spec.measured_pairs():
        qc.measure(q, c)
    return qc


def device(fake: bool):
    if fake:
        from qiskit_ibm_runtime.fake_provider import FakeSherbrooke

        return FakeSherbrooke(), None
    from qiskit_ibm_runtime import QiskitRuntimeService

    load_dotenv(ROOT / ".env")
    token = os.environ.get("IBM_QUANTUM_TOKEN")
    if not token:
        sys.exit("put IBM_QUANTUM_TOKEN=... in .env (IBM Quantum Platform API key), or run with --fake")
    service = QiskitRuntimeService(channel="ibm_quantum_platform", token=token,
                                   instance=os.environ.get("IBM_QUANTUM_INSTANCE") or None)
    backend = service.least_busy(operational=True, simulator=False, min_num_qubits=5)
    return backend, service


def main() -> None:
    fake = "--fake" in sys.argv
    backend, _ = device(fake)
    print(f"device: {backend.name} ({'rehearsal on a fake device' if fake else 'real hardware'})", flush=True)
    twin = AerSimulator(noise_model=NoiseModel.from_backend(backend))
    runs, transpiled = [], []
    for name in CIRCUITS:
        spec = parse_spec(json.loads((ROOT / "examples" / "specs" / f"{name}.json").read_text(encoding="utf-8")))
        tqc = transpile(measured_circuit(spec), backend, optimization_level=3, seed_transpiler=7)
        transpiled.append((name, spec, tqc))
    if fake:
        sim = AerSimulator.from_backend(backend)
        measured = [norm(sim.run(t, shots=SHOTS, seed_simulator=11).result().get_counts()) for _, _, t in transpiled]
        job_id = "rehearsal"
    else:
        from qiskit_ibm_runtime import SamplerV2

        job = SamplerV2(mode=backend).run([t for _, _, t in transpiled], shots=SHOTS)
        job_id = job.job_id()
        print(f"job {job_id} submitted; waiting in the queue...", flush=True)
        t0 = time.time()
        result = job.result()
        print(f"done after {time.time() - t0:.0f} s", flush=True)
        measured = [norm(r.join_data().get_counts()) for r in result]
    for (name, spec, tqc), meas in zip(transpiled, measured):
        ideal = ideal_distribution(spec)
        generic = noisy_distribution(spec, "realistic")
        tw = norm(twin.run(tqc, shots=200_000, seed_simulator=5).result().get_counts())
        ops = tqc.count_ops()
        row = {
            "circuit": spec.metadata.title or name, "id": name,
            "two_qubit_gates": int(sum(v for k, v in ops.items() if k in ("cx", "ecr", "cz"))),
            "depth": tqc.depth(), "measured": dict(sorted(meas.items(), key=lambda kv: -kv[1])[:8]),
            "ideal": ideal, "generic": {k: generic.get(k, 0.0) for k in sorted(meas, key=lambda k: -meas[k])[:8]},
            "twin": {k: tw.get(k, 0.0) for k in sorted(meas, key=lambda k: -meas[k])[:8]},
            "fidelity_to_ideal": hellinger_fidelity(ideal, meas), "fidelity_generic_prediction": hellinger_fidelity(generic, meas),
            "fidelity_twin_prediction": hellinger_fidelity(tw, meas),
            "tvd_ideal": tvd(ideal, meas), "tvd_generic": tvd(generic, meas), "tvd_twin": tvd(tw, meas),
        }
        runs.append(row)
        print(f"{name:20s} 2q {row['two_qubit_gates']:3d}  measured vs ideal TVD {row['tvd_ideal']:.3f} | "
              f"generic preset TVD {row['tvd_generic']:.3f} | digital twin TVD {row['tvd_twin']:.3f}", flush=True)
    out = {"device": backend.name, "rehearsal": fake, "job_id": job_id, "shots": SHOTS,
           "date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "runs": runs}
    path = ROOT / "examples" / ("hardware_rehearsal.json" if fake else "hardware_runs.json")
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    if not fake:
        write_doc(out)
    print(f"wrote {path}")


def write_doc(out: dict) -> None:
    lines = ["# Real hardware check", "",
             f"{len(out['runs'])} circuits run on **{out['device']}** (IBM Quantum, job `{out['job_id']}`, {out['shots']} shots, "
             f"{out['date_utc']}) with `scripts/hardware_check.py`, compared with the ideal odds, Q-Canvas's generic "
             "realistic preset and a digital twin built from the device's own calibration (Qiskit Aer, "
             "NoiseModel.from_backend). Lower total variation distance (TVD) is closer to what the chip did.", "",
             "| Circuit | Two-qubit gates on the chip | TVD to ideal | TVD to generic preset | TVD to digital twin |",
             "| --- | --- | --- | --- | --- |"]
    for r in out["runs"]:
        lines.append(f"| {r['circuit']} | {r['two_qubit_gates']} | {r['tvd_ideal']:.3f} | {r['tvd_generic']:.3f} | {r['tvd_twin']:.3f} |")
    (ROOT / "docs" / "HARDWARE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
