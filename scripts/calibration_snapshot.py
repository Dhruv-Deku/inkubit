"""Take a calibration snapshot of a real IBM quantum computer for Inkubit's calibrated noise preset.

    .venv/Scripts/python scripts/calibration_snapshot.py [device]      # default: the device of the last hardware run

Reads the device's reported calibration (IBM Quantum Platform, needs IBM_QUANTUM_TOKEN in .env) and keeps the median
over its working qubits and couplers: one-qubit (sx) and two-qubit gate error and duration, readout error each way,
T1 and T2. Writes backend/inkubit/data/calibration.json; inkubit.sim.noise turns it into the "calibrated" preset.
Medians describe a typical qubit, not the best patch a compiler would pick, which the file says.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    from dotenv import load_dotenv
    from qiskit_ibm_runtime import QiskitRuntimeService

    load_dotenv(ROOT / ".env")
    token = os.environ.get("IBM_QUANTUM_TOKEN")
    if not token:
        sys.exit("put IBM_QUANTUM_TOKEN=... in .env")
    name = sys.argv[1] if len(sys.argv) > 1 else json.loads((ROOT / "examples" / "hardware_runs.json").read_text())["device"]
    service = QiskitRuntimeService(channel="ibm_quantum_platform", token=token,
                                   instance=os.environ.get("IBM_QUANTUM_INSTANCE") or None)
    backend = service.backend(name)
    props = backend.properties()
    target = backend.target
    two_q = next(g for g in ("cz", "ecr", "cx") if g in target.operation_names)
    med = lambda xs: float(statistics.median([x for x in xs if x is not None and x == x]))  # noqa: E731

    sx = [p for p in target["sx"].values() if p is not None and p.error is not None and p.error < 0.5]
    tq = [p for p in target[two_q].values() if p is not None and p.error is not None and p.error < 0.5]
    qubits = range(backend.num_qubits)
    p01 = [props.qubit_property(q).get("prob_meas1_prep0", (None,))[0] for q in qubits]
    p10 = [props.qubit_property(q).get("prob_meas0_prep1", (None,))[0] for q in qubits]
    t1 = [backend.qubit_properties(q).t1 for q in qubits]
    t2 = [backend.qubit_properties(q).t2 for q in qubits]
    snap = {
        "device": backend.name, "processor": getattr(backend, "processor_type", None) or {},
        "taken_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "calibrated_utc": props.last_update_date.isoformat() if props.last_update_date else None,
        "qubits": backend.num_qubits, "two_qubit_gate": two_q,
        "sx_error": med([p.error for p in sx]), "sx_ns": med([p.duration for p in sx]) * 1e9,
        "two_qubit_error": med([p.error for p in tq]), "two_qubit_ns": med([p.duration for p in tq]) * 1e9,
        "readout_p01": med(p01), "readout_p10": med(p10),
        "t1_us": med(t1) * 1e6, "t2_us": med(t2) * 1e6,
        "note": "Medians over the device's qubits and couplers: a typical qubit, not the best patch a compiler picks.",
    }
    path = ROOT / "backend" / "inkubit" / "data" / "calibration.json"
    path.write_text(json.dumps(snap, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(snap, indent=1))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
