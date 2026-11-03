"""IBM Quantum from the app: the fleet's live queues, and running the circuit in the editor on a real device.

Available only when IBM_QUANTUM_TOKEN is set, qiskit-ibm-runtime is installed and the app is not in public mode (a shared
host must not spend its owner's QPU time). A run is placed by the advisor (inkubit.chip: the best-scored qubits from
the device's calibration snapshot) when the circuit's wiring embeds, compiled at optimisation level 1 onto exactly those
qubits, and sent with SamplerV2; otherwise Qiskit's level-3 compiler places it. Runs are capped per UTC day
(INKUBIT_IBM_DAILY_RUNS, default 10) and logged to backend/.inkubit_cache/ibm_runs.json, so a result survives a restart.
The comparison is honest about what it is: distance to the ideal odds, to Inkubit's calibrated preset, and the distance
shot noise alone would leave; no pass/fail, because no simulation is the chip.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from inkubit.spec import CircuitSpec

LOG = Path(__file__).resolve().parents[1] / ".inkubit_cache" / "ibm_runs.json"
MAX_SHOTS = 4096
_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def available() -> tuple[bool, str]:
    from inkubit.adapters.config import load_settings

    load_settings()  # loads .env once, never overriding the environment
    if os.environ.get("INKUBIT_PUBLIC") == "1":
        return False, "public mode: runs on IBM hardware are switched off on a shared host"
    if not os.environ.get("IBM_QUANTUM_TOKEN"):
        return False, "no IBM_QUANTUM_TOKEN in .env"
    err = _runtime_import_error()
    if err:
        return False, f"qiskit-ibm-runtime could not be imported ({err})"
    return True, "ready"


_import_lock = threading.Lock()


def _runtime_import_error() -> str | None:
    """Import qiskit-ibm-runtime once, under a lock: two request threads importing it at the same moment can see a
    half-initialised module and an ImportError (the panel and the run button ask for the status together)."""
    hit = _cache.get("runtime")
    if hit:
        return hit[1]
    with _import_lock:
        hit = _cache.get("runtime")
        if hit:
            return hit[1]
        try:
            import qiskit_ibm_runtime  # noqa: F401

            err = None
        except ImportError as exc:
            err = str(exc)[:160] or "not installed"
        _cache["runtime"] = (time.time(), err)
        return err


def _service():
    hit = _cache.get("service")
    if hit:
        return hit[1]
    from qiskit_ibm_runtime import QiskitRuntimeService

    svc = QiskitRuntimeService(channel="ibm_quantum_platform", token=os.environ["IBM_QUANTUM_TOKEN"],
                               instance=os.environ.get("IBM_QUANTUM_INSTANCE") or None)
    _cache["service"] = (time.time(), svc)
    return svc


def _cached(key: str, ttl: float, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val


def live_status() -> dict[str, Any]:
    """Queues and operational state of every device, and the account's QPU time left (cached for a minute)."""
    def fetch():
        svc = _service()
        devices = []
        for b in svc.backends(simulator=False):
            st = b.status()
            devices.append({"device": b.name, "operational": st.operational, "pending_jobs": st.pending_jobs})
        try:
            u = svc.usage()
            usage = {"used_s": u.get("usage_consumed_seconds"), "limit_s": u.get("usage_limit_seconds"),
                     "left_s": u.get("usage_remaining_seconds")}
        except Exception:  # noqa: BLE001 - usage is a nicety; the queues are what matter
            usage = None
        return {"devices": devices, "usage": usage, "checked_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    return _cached("live", 60, fetch)


def _log() -> dict[str, Any]:
    if LOG.exists():
        try:
            return json.loads(LOG.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def _save(runs: dict[str, Any]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(runs, indent=1), encoding="utf-8")


def runs_today() -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    return sum(r["submitted_utc"].startswith(today) for r in _log().values())


def submit(spec: CircuitSpec, shots: int = 2048, device: str | None = None) -> dict[str, Any]:
    from qiskit import transpile
    from qiskit_ibm_runtime import SamplerV2

    from inkubit.chip import advise, device_names
    from inkubit.proofsheet import _measured

    ok, why = available()
    if not ok:
        raise PermissionError(why)
    cap = int(os.environ.get("INKUBIT_IBM_DAILY_RUNS", "10"))
    if runs_today() >= cap:
        raise PermissionError(f"today's cap of {cap} IBM runs is reached (INKUBIT_IBM_DAILY_RUNS)")
    shots = max(100, min(int(shots), MAX_SHOTS))
    svc = _service()
    if device is None:
        live = {d["device"]: d for d in live_status()["devices"] if d["operational"]}
        device = min(live, key=lambda n: live[n]["pending_jobs"])
    backend = svc.backend(device)
    placement, how = None, "Qiskit's level-3 compiler chose the qubits"
    if device in device_names():
        adv = advise(spec, device)
        if adv.ok and adv.best:
            placement = adv.best.qubits
            how = f"placed by the advisor on qubits {', '.join(map(str, placement))} (score {adv.best.success:.3f})"
    qc = _measured(spec)
    tqc = (transpile(qc, backend, initial_layout=placement, optimization_level=1, seed_transpiler=7) if placement
           else transpile(qc, backend, optimization_level=3, seed_transpiler=7))
    job = SamplerV2(mode=backend).run([tqc], shots=shots)
    two_q = int(sum(v for k, v in tqc.count_ops().items() if k in ("cz", "ecr", "cx")))
    run = {"job_id": job.job_id(), "device": device, "shots": shots, "placement": placement, "how": how,
           "two_qubit_gates": two_q, "title": spec.metadata.title or "circuit",
           "spec": spec.model_dump(mode="json", by_alias=True, exclude_none=True),
           "submitted_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": "QUEUED", "result": None}
    with _lock:
        runs = _log()
        runs[run["job_id"]] = run
        _save(runs)
    return {k: v for k, v in run.items() if k != "spec"}


def poll(job_id: str) -> dict[str, Any]:
    from inkubit.hardware import tvd
    from inkubit.spec import parse_spec
    from inkubit.verify.expected import ideal_distribution, noisy_distribution

    runs = _log()
    if job_id not in runs:
        raise KeyError(job_id)
    run = runs[job_id]
    if run["result"] is None:
        job = _service().job(job_id)
        status = str(job.status())
        run["status"] = status
        if status == "DONE":
            res = job.result()[0]
            counts = res.join_data().get_counts()
            total = sum(counts.values())
            measured = {k: v / total for k, v in counts.items()}
            spec = parse_spec(run["spec"])
            ideal = ideal_distribution(spec)
            cal = noisy_distribution(spec, "calibrated") if spec.num_qubits <= 10 else None
            run["result"] = {
                "measured": dict(sorted(measured.items(), key=lambda kv: -kv[1])[:16]),
                "ideal": dict(sorted(ideal.items(), key=lambda kv: -kv[1])[:16]),
                "tvd_ideal": tvd(ideal, measured), "tvd_calibrated": tvd(cal, measured) if cal else None,
                "shot_noise": 0.5 * sum(math.sqrt(2 * p * (1 - p) / (math.pi * run["shots"])) for p in (cal or ideal).values()),
                "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        elif status in ("ERROR", "CANCELLED"):
            run["result"] = {"error": str(getattr(job, "error_message", lambda: "")() or status)}
        with _lock:
            fresh = _log()
            fresh[job_id] = run
            _save(fresh)
    return {k: v for k, v in run.items() if k != "spec"}
