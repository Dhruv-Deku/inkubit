"""Snapshot IBM quantum computers in full: every qubit and every coupler, for the chip map and the placement advisor.

    .venv/Scripts/python scripts/device_snapshot.py [device ...]     # default: every device the account can use

For each device: the coupling map, and per qubit T1, T2, readout error each way and the one-qubit (sx) gate error;
per coupler the two-qubit gate error; the processor, the calibration time and the queue at the moment of the snapshot.
Writes backend/qcanvas/data/devices/<name>.json (a few tens of KB each). Needs IBM_QUANTUM_TOKEN in .env.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backend" / "qcanvas" / "data" / "devices"


def snapshot(backend) -> dict:
    props = backend.properties()
    target = backend.target
    two_q = next(g for g in ("cz", "ecr", "cx") if g in target.operation_names)
    qubits = []
    for q in range(backend.num_qubits):
        qp = props.qubit_property(q)
        sx = target["sx"].get((q,))
        qubits.append({
            "t1_us": round(qp["T1"][0] * 1e6, 2) if "T1" in qp else None,
            "t2_us": round(qp["T2"][0] * 1e6, 2) if "T2" in qp else None,
            "p01": qp.get("prob_meas1_prep0", (None,))[0], "p10": qp.get("prob_meas0_prep1", (None,))[0],
            "sx_error": sx.error if sx is not None else None,
        })
    edges = {}
    for (a, b), p in target[two_q].items():
        key = f"{min(a, b)}-{max(a, b)}"
        if p is not None and p.error is not None:
            edges[key] = min(edges.get(key, 1.0), p.error)  # the better direction, if both are calibrated
    st = backend.status()
    return {"device": backend.name, "processor": getattr(backend, "processor_type", None) or {},
            "num_qubits": backend.num_qubits, "two_qubit_gate": two_q,
            "two_qubit_ns": round(next(p.duration for p in target[two_q].values() if p and p.duration) * 1e9, 1),
            "sx_ns": round(next(p.duration for p in target["sx"].values() if p and p.duration) * 1e9, 1),
            "dynamic_circuits": "if_else" in target.operation_names,
            "taken_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "calibrated_utc": props.last_update_date.isoformat() if props.last_update_date else None,
            "pending_jobs": st.pending_jobs, "operational": st.operational,
            "qubits": qubits, "edges": edges}


def main() -> None:
    from dotenv import load_dotenv
    from qiskit_ibm_runtime import QiskitRuntimeService

    load_dotenv(ROOT / ".env")
    token = os.environ.get("IBM_QUANTUM_TOKEN")
    if not token:
        sys.exit("put IBM_QUANTUM_TOKEN=... in .env")
    service = QiskitRuntimeService(channel="ibm_quantum_platform", token=token,
                                   instance=os.environ.get("IBM_QUANTUM_INSTANCE") or None)
    names = sys.argv[1:] or [b.name for b in service.backends(simulator=False, operational=True)]
    OUT.mkdir(parents=True, exist_ok=True)
    for name in names:
        snap = snapshot(service.backend(name))
        (OUT / f"{name}.json").write_text(json.dumps(snap, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"{name}: {snap['num_qubits']} qubits, {len(snap['edges'])} couplers, calibrated {snap['calibrated_utc']}, "
              f"{snap['pending_jobs']} jobs queued")


if __name__ == "__main__":
    main()
