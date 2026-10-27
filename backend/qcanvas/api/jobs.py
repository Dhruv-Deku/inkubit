"""In-memory job store and the workers that run circuit and network jobs."""

from __future__ import annotations

import base64
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from qcanvas.adapters.registry import Models, get_models
from qcanvas.agent import AgentOptions, EventBus, run_agent
from qcanvas.explain.diagrams import circuit_png
from qcanvas.spec.models import CircuitSpec, NetworkSpec

log = logging.getLogger("qcanvas.jobs")
MAX_JOBS = 200


class RunOptions(BaseModel):
    """Options accepted by POST /api/jobs/spec."""

    noise: str = "realistic"
    shots: int = Field(default=4096, ge=16, le=100_000)
    demo_mode: bool = False
    demo_fault: str = "auto"
    explain: bool = True
    diagram: bool = True
    pace_s: float | None = Field(default=None, ge=0, le=2)


@dataclass
class Job:
    """One run and its live log."""

    id: str
    kind: str
    spec: CircuitSpec | NetworkSpec
    options: RunOptions
    bus: EventBus = field(default_factory=EventBus)
    status: str = "queued"  # queued | running | done | failed
    result: dict[str, Any] | None = None
    error: str | None = None
    created: float = field(default_factory=time.time)

    def summary(self) -> dict[str, Any]:
        """Public JSON for GET /api/jobs/{id}."""
        return {"id": self.id, "kind": self.kind, "status": self.status, "error": self.error,
                "events": len(self.bus.events()), "result": self.result,
                "spec": self.spec.model_dump(mode="json", by_alias=True, exclude_none=True)}


class JobStore:
    """Thread-safe dict of jobs plus a small worker pool."""

    def __init__(self, workers: int = 2):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="qcanvas-job")

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def submit(self, spec: CircuitSpec | NetworkSpec, options: RunOptions, models: Models | None = None) -> Job:
        """Create a job and start it in the background."""
        job = Job(id=uuid.uuid4().hex[:12], kind=spec.kind, spec=spec, options=options)
        with self._lock:
            if len(self._jobs) >= MAX_JOBS:
                oldest = min(self._jobs.values(), key=lambda j: j.created)
                self._jobs.pop(oldest.id, None)
            self._jobs[job.id] = job
        self._pool.submit(_run_job, job, models)
        return job


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _explain(job: Job, models: Models, result: dict[str, Any]) -> dict[str, Any] | None:
    bus = job.bus
    bus.emit("explain", "running", "Writing a plain-language explanation of these results…")
    try:
        exp = models.reasoning.explain(job.spec, result)
    except Exception as err:  # noqa: BLE001 - failing soft: the verified result stands on its own
        bus.emit("explain", "warn", f"Could not write an explanation: {err}")
        return None
    tag = " (mock fallback)" if exp.call.provider == "mock-fallback" else ""
    bus.emit("explain", "ok", f"Explanation ready from {exp.call.model}{tag}.", call=exp.call.model_dump())
    return exp.model_dump(mode="json")


def _diagram(job: Job, models: Models, result: dict[str, Any]) -> dict[str, Any] | None:
    bus = job.bus
    bus.emit("diagram", "running", "Drawing a clean diagram of the final design…")
    try:
        dia = models.image.diagram(job.spec, result)
    except Exception as err:  # noqa: BLE001
        bus.emit("diagram", "warn", f"Could not draw the diagram: {err}")
        return None
    tag = " (mock fallback)" if dia.call.provider == "mock-fallback" else ""
    bus.emit("diagram", "ok", f"Diagram ready from {dia.call.model}{tag}.", call=dia.call.model_dump())
    return dia.model_dump(mode="json")


def _extras(job: Job, models: Models, result: dict[str, Any]) -> dict[str, Any]:
    """Explanation (Muse Spark) and illustration (Muse Image) in parallel, each failing soft."""
    tasks = {}
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="qcanvas-extra") as pool:
        if job.options.explain:
            tasks["explanation"] = pool.submit(_explain, job, models, result)
        if job.options.diagram:
            tasks["diagram"] = pool.submit(_diagram, job, models, result)
    return {k: f.result() for k, f in tasks.items() if f.result() is not None}


def _run_job(job: Job, models: Models | None) -> None:
    job.status = "running"
    try:
        models = models or get_models()
        payload: dict[str, Any]
        if isinstance(job.spec, CircuitSpec):
            o = job.options
            pace = o.pace_s if o.pace_s is not None else (0.35 if o.demo_mode else 0.0)
            agent = run_agent(job.spec, models.code, AgentOptions(
                noise=o.noise, shots=o.shots, demo_fault=o.demo_fault if o.demo_mode else None, pace_s=pace,
            ), job.bus)
            payload = agent.model_dump(mode="json")
            payload["exact_diagram"] = {"image_b64": _b64(circuit_png(job.spec)), "mime": "image/png",
                                        "caption": "Exact circuit, drawn by Qiskit from the spec."}
        else:
            from qcanvas.network.agent import run_network_agent

            payload = run_network_agent(job.spec, job.bus, pace_s=job.options.pace_s or 0.0).model_dump(mode="json")
        job.result = dict(payload)  # the verified result is available before the extras finish
        payload.update(_extras(job, models, payload))
        job.result = payload
        job.status = "done"
    except Exception as err:  # noqa: BLE001 - reported to the client, never swallowed silently
        log.exception("job %s failed", job.id)
        job.error = f"{type(err).__name__}: {err}"
        job.status = "failed"
        job.bus.emit("done", "fail", f"The run stopped with an internal error: {job.error}")
    finally:
        job.bus.close()
