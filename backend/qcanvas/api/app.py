"""FastAPI app: sketch analysis, agent jobs with a live SSE log, examples, health.

Run:  cd backend && ../.venv/Scripts/python -m uvicorn qcanvas.api.app:app --port 8000
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from qcanvas import EXAMPLES_DIR, PROJECT_DIR, __version__
from qcanvas.adapters.config import load_settings
from qcanvas.adapters.mock_vision import UnknownImageError
from qcanvas.adapters.registry import ModelUnavailable, get_models
from qcanvas.agent.faults import FAULTS
from qcanvas.api.jobs import JobStore, RunOptions
from qcanvas.sim.noise import PRESETS
from qcanvas.sketch import analyze_image
from qcanvas.spec.validation import SpecError, parse_spec

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
MAX_UPLOAD = 15 * 1024 * 1024

app = FastAPI(title="Q-Canvas", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"],
    allow_methods=["*"], allow_headers=["*"],
)
store = JobStore()


class SpecRequest(BaseModel):
    """Body of POST /api/jobs/spec and /api/spec/validate."""

    spec: dict[str, Any]
    options: RunOptions = RunOptions()


def _issues(err: SpecError) -> list[dict[str, str]]:
    return [i.model_dump() for i in err.issues]


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Liveness plus the model provider mode (meta or mock), never the key."""
    s = load_settings()
    live = s.provider == "meta" and s.has_key
    return {"status": "ok", "version": __version__, "mode": "meta" if live else "mock",
            "mode_label": "Meta live" if live else ("Meta (no key: mock fallback)" if s.provider == "meta" else "Mock"),
            **s.public()}


ALGORITHMS = {"grover2", "bernstein_vazirani", "deutsch_jozsa", "phase_estimation", "superdense", "toffoli_and"}


@app.get("/api/examples")
def examples() -> dict[str, Any]:
    """Example specs and sample sketch images."""
    specs = []
    for path in sorted((EXAMPLES_DIR / "specs").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = data.get("metadata", {})
        group = ("Networks" if data.get("kind") == "network" else "Algorithms" if path.stem in ALGORITHMS
                 else "Check the validator" if path.stem == "invalid_circuit" else "Basics")
        specs.append({"id": path.stem, "title": meta.get("title") or path.stem, "kind": data.get("kind"),
                      "notes": meta.get("notes", ""), "valid": path.stem != "invalid_circuit", "group": group,
                      "spec": data})
    order = ["Basics", "Algorithms", "Networks", "Check the validator"]
    specs.sort(key=lambda s: (order.index(s["group"]), s["title"]))
    images = []
    for path in sorted((EXAMPLES_DIR / "images").glob("*.json")):
        fx = json.loads(path.read_text(encoding="utf-8"))
        images.append({"id": fx["name"], "title": fx["spec"]["metadata"]["title"], "kind": fx["kind"],
                       "url": f"/api/examples/images/{fx['name']}.png"})
    return {"specs": specs, "images": images,
            "noise_presets": [p.as_dict() for p in PRESETS.values()],
            "faults": [{"name": f.name, "label": f.label, "description": f.description} for f in FAULTS.values()]}


@app.get("/api/examples/images/{name}")
def example_image(name: str) -> FileResponse:
    """Serve a bundled sample sketch."""
    path = (EXAMPLES_DIR / "images" / name).resolve()
    if path.parent != (EXAMPLES_DIR / "images").resolve() or path.suffix != ".png" or not path.exists():
        raise HTTPException(404, "no such example image")
    return FileResponse(path, media_type="image/png")


@app.post("/api/spec/validate")
def validate(body: SpecRequest) -> dict[str, Any]:
    """Validate a spec and return readable issues."""
    try:
        spec = parse_spec(body.spec)
    except SpecError as err:
        return {"valid": False, "issues": _issues(err)}
    return {"valid": True, "issues": [], "spec": spec.model_dump(mode="json", by_alias=True, exclude_none=True)}


class InsightsRequest(BaseModel):
    spec: dict[str, Any]
    noise: str = "realistic"


@app.post("/api/insights")
def insights(body: InsightsRequest) -> dict[str, Any]:
    """Exact analyses of a circuit spec without running it (step-through, entanglement, noise budget)."""
    from qcanvas.insights.circuit import analyze_circuit
    from qcanvas.spec.models import CircuitSpec

    try:
        spec = parse_spec(body.spec)
    except SpecError as err:
        raise HTTPException(status_code=422, detail={"issues": _issues(err)}) from err
    if not isinstance(spec, CircuitSpec):
        raise HTTPException(status_code=422, detail="Insights are for circuits; networks have their own analysis.")
    if body.noise not in PRESETS:
        raise HTTPException(status_code=422, detail=f"unknown noise preset '{body.noise}'")
    return analyze_circuit(spec, body.noise).model_dump(mode="json")


@app.post("/api/jobs/image")
async def job_image(file: UploadFile = File(...)) -> dict[str, Any]:
    """Photo -> segments + spec draft + overlay data (does not run anything yet)."""
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "the upload is empty")
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "the image is larger than 15 MB")
    try:
        analysis, _ = await asyncio.to_thread(analyze_image, raw, get_models())
    except UnknownImageError as err:
        raise HTTPException(422, str(err)) from None
    except ModelUnavailable as err:
        raise HTTPException(502, f"A Meta model call failed and fallback is off: {err}") from None
    except OSError as err:
        raise HTTPException(400, f"could not read the image: {err}") from None
    return analysis.model_dump(mode="json")


class AskRequest(BaseModel):
    question: str


@app.post("/api/jobs/{job_id}/ask")
async def ask(job_id: str, body: AskRequest) -> dict[str, Any]:
    """Answer a question about a finished run from its facts (Muse Spark live; offline rules otherwise)."""
    from qcanvas.ask import ask_context

    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    if job.result is None:
        raise HTTPException(409, "the run has not finished yet")
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "ask a question first")
    context = ask_context(job.spec, job.result)
    try:
        answer = await asyncio.to_thread(get_models().reasoning.answer, question[:600], context)
    except ModelUnavailable as err:
        raise HTTPException(502, f"A Meta model call failed and fallback is off: {err}") from None
    return answer.model_dump(mode="json")


class TextRequest(BaseModel):
    text: str


@app.post("/api/jobs/text")
async def job_text(body: TextRequest) -> dict[str, Any]:
    """Plain-language description -> spec draft (Muse Spark live; an offline parser otherwise)."""
    from qcanvas.textspec import UnknownTextError

    text = body.text.strip()
    if not text:
        raise HTTPException(400, "describe a circuit or a network first")
    if len(text) > 2000:
        raise HTTPException(413, "keep the description under 2,000 characters")
    try:
        draft = await asyncio.to_thread(get_models().reasoning.spec_from_text, text)
    except UnknownTextError as err:
        raise HTTPException(422, str(err)) from None
    except ModelUnavailable as err:
        raise HTTPException(502, f"A Meta model call failed and fallback is off: {err}") from None
    return {"kind": draft.spec.get("kind"), **draft.model_dump(mode="json", exclude={"extra_segments"})}


@app.post("/api/jobs/spec")
def job_spec(body: SpecRequest) -> dict[str, Any]:
    """Validate the spec and start an agent run; returns the job id."""
    try:
        spec = parse_spec(body.spec)
    except SpecError as err:
        raise HTTPException(422, {"message": "The spec is not valid.", "issues": _issues(err)}) from None
    if body.options.noise not in PRESETS:
        raise HTTPException(422, f"unknown noise preset '{body.options.noise}'")
    if body.options.demo_mode and body.options.demo_fault not in ("auto", *FAULTS):
        raise HTTPException(422, f"unknown demo fault '{body.options.demo_fault}'")
    job = store.submit(spec, body.options)
    return {"job_id": job.id, "kind": job.kind, "events_url": f"/api/jobs/{job.id}/events"}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, Any]:
    """Status and (when finished) the full result."""
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    return job.summary()


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str) -> EventSourceResponse:
    """Server-sent events: every log line, replayed from the start, then live."""
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")

    async def stream():
        cursor = 0
        while True:
            events = job.bus.events(cursor)
            for event in events:
                yield {"event": "log", "id": str(event.seq), "data": event.model_dump_json()}
            cursor += len(events)
            if job.bus.closed and not job.bus.events(cursor):
                yield {"event": "end", "data": json.dumps({"status": job.status, "error": job.error})}
                return
            await asyncio.sleep(0.12)

    return EventSourceResponse(stream(), ping=10)


_DIST = PROJECT_DIR / "frontend" / "dist"
if _DIST.exists():  # serve the built frontend from the same port for one-command demos
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
