"""FastAPI app: sketch analysis, agent jobs with a live SSE log, examples, health.

Run:  cd backend && ../.venv/Scripts/python -m uvicorn qcanvas.api.app:app --port 8000
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from qcanvas import EXAMPLES_DIR, PROJECT_DIR, __version__
from qcanvas.adapters.config import load_settings
from qcanvas.adapters.mock_vision import UnknownImageError
from qcanvas.adapters.registry import ModelUnavailable, get_models
from qcanvas.agent.faults import FAULTS
from qcanvas.api.jobs import JobStore, RunOptions
from qcanvas.sim.noise import PRESETS, get_preset
from qcanvas.sketch import analyze_image
from qcanvas.spec.validation import SpecError, parse_spec

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("qiskit").setLevel(logging.WARNING)  # the transpiler logs every pass at INFO
log = logging.getLogger("qcanvas.api")
MAX_UPLOAD = 15 * 1024 * 1024

app = FastAPI(title="Q-Canvas", version=__version__)


@app.on_event("startup")
def _warm_up() -> None:
    """Compute the slow, input-free results (pulse sweep, observatory, the satellite planner's default view) in the
    background so no visitor waits."""
    import threading

    def work() -> None:
        try:
            from qcanvas.observatory import observatory
            from qcanvas.orbits import plan
            from qcanvas.pulse import sweep

            observatory()
            plan("chilbolton", "singapore", True, "speqtre")
            sweep()
        except Exception as err:  # noqa: BLE001 - a failed warm-up only means the first visitor computes it
            log.warning("warm-up failed: %s", err)

    threading.Thread(target=work, name="warm-up", daemon=True).start()


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
            "live_calls_left": _budget_left(s.daily_calls), **s.public()}


def _budget_left(cap: int) -> int | None:
    from qcanvas.adapters.meta_client import BUDGET

    return BUDGET.left(cap)


ALGORITHMS = {"grover2", "bernstein_vazirani", "deutsch_jozsa", "phase_estimation", "superdense", "toffoli_and",
              "teleportation", "w_state", "bit_flip_code", "shor15", "qft_period", "simon", "swap_test",
              "entanglement_swapping", "ising_trotter", "grover3", "half_adder"}


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
    from qcanvas.adapters.base import LANGUAGES

    return {"specs": specs, "images": images, "languages": list(LANGUAGES),
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


class StateRequest(BaseModel):
    spec: dict[str, Any]
    noise: str = "realistic"
    scale: float | None = Field(default=None, ge=0, le=20)


@app.post("/api/state")
def live_state(body: StateRequest) -> dict[str, Any]:
    """Fast exact state for live editing: every step's ideal state and, with ``scale``, the noisy outcome odds."""
    from qcanvas.insights.circuit import MAX_NOISY_QUBITS, noisy_distribution, scaled_preset, step_states
    from qcanvas.spec.models import CircuitSpec
    from qcanvas.verify import ideal_distribution
    from qcanvas.verify.metrics import hellinger_fidelity

    try:
        spec = parse_spec(body.spec)
    except SpecError as err:
        raise HTTPException(status_code=422, detail={"issues": _issues(err)}) from err
    if not isinstance(spec, CircuitSpec):
        raise HTTPException(status_code=422, detail="Live state is for circuits.")
    if body.noise not in PRESETS:
        raise HTTPException(status_code=422, detail=f"unknown noise preset '{body.noise}'")
    out: dict[str, Any] = {"steps": [s.model_dump(mode="json") for s in step_states(spec)], "ideal": None, "noisy": None}
    if spec.measured_pairs():
        ideal = ideal_distribution(spec)
        out["ideal"] = ideal
        if body.scale is not None and spec.num_qubits <= MAX_NOISY_QUBITS:
            base = get_preset(body.noise) if body.noise != "ideal" else get_preset("realistic")
            dist = noisy_distribution(spec, scaled_preset(base, body.scale))
            answer = max(ideal, key=ideal.get) if max(ideal.values()) > 0.99 else None
            out["noisy"] = {"scale": body.scale, "baseline": base.name, "distribution": dist,
                            "fidelity": hellinger_fidelity(ideal, dist),
                            "success": dist.get(answer, 0.0) if answer else None}
    return out


class OptimizeRequest(BaseModel):
    spec: dict[str, Any]
    ai: bool = True


@app.post("/api/optimize")
async def optimize_circuit(body: OptimizeRequest) -> dict[str, Any]:
    """Cheaper equivalent circuits from rewrite rules, Qiskit and (live) Muse Spark, each proven or rejected."""
    from qcanvas.optimize import optimize
    from qcanvas.spec.models import CircuitSpec

    try:
        spec = parse_spec(body.spec)
    except SpecError as err:
        raise HTTPException(status_code=422, detail={"issues": _issues(err)}) from err
    if not isinstance(spec, CircuitSpec):
        raise HTTPException(status_code=422, detail="Optimizing is for circuits.")
    models = get_models()
    live = models.settings.provider == "meta" and models.settings.has_key
    note = "" if live else ("Muse Spark joins with the live Meta model; offline, the rules and Qiskit compete."
                            if body.ai else "")
    propose = models.reasoning.optimize if (live and body.ai) else None
    result = await asyncio.to_thread(optimize, spec, propose, note)
    return result.model_dump(mode="json")


@app.post("/api/missions")
async def start_mission(goal: str = Form(..., min_length=3, max_length=4000), transcript: str = Form(""),
                        deep: bool = Form(False), image: UploadFile | None = File(None)) -> dict[str, Any]:
    """Mission control: words, an optional photo and speech in; a plan of exact tools runs live (see qcanvas.mission)."""
    from qcanvas.mission import Mission, launch, missions

    raw = await image.read() if image is not None else b""
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "the image is larger than 15 MB")
    m = Mission(goal.strip())
    missions.add(m)
    launch(m, get_models(), raw or None, transcript[:2000], deep)
    return {"mission_id": m.id, "events_url": f"/api/missions/{m.id}/events"}


@app.get("/api/missions/{mission_id}")
def mission_status(mission_id: str) -> dict[str, Any]:
    from qcanvas.mission import missions

    m = missions.get(mission_id)
    if m is None:
        raise HTTPException(404, "no such mission")
    return m.summary()


@app.get("/api/missions/{mission_id}/report")
def mission_report(mission_id: str) -> Response:
    """A finished mission as one self-contained HTML page: plan, every step and check, the traced report, code."""
    from qcanvas.mission import missions
    from qcanvas.mission_report import render

    m = missions.get(mission_id)
    if m is None:
        raise HTTPException(404, "no such mission")
    if m.status == "running":
        raise HTTPException(409, "the mission has not finished yet")
    return Response(render(m), media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="qcanvas_mission_{m.id}.html"'})


@app.get("/api/missions/{mission_id}/events")
async def mission_events(mission_id: str) -> EventSourceResponse:
    """Server-sent events: every node change, replayed from the start, then live."""
    from qcanvas.mission import missions

    m = missions.get(mission_id)
    if m is None:
        raise HTTPException(404, "no such mission")

    async def stream():
        cursor = 0
        while True:
            events = m.bus.events(cursor)
            for event in events:
                yield {"event": "mission", "id": str(event.seq), "data": json.dumps(event.details, default=str)}
            cursor += len(events)
            if m.bus.closed and not m.bus.events(cursor):
                yield {"event": "end", "data": json.dumps({"status": m.status, "error": m.error})}
                return
            await asyncio.sleep(0.1)

    return EventSourceResponse(stream(), ping=10)


class MlVerifyRequest(BaseModel):
    spec: dict[str, Any]
    scale: float = Field(default=1.0, ge=0.05, le=5)


@app.post("/api/mlverify")
async def ml_verify(body: MlVerifyRequest) -> dict[str, Any]:
    """The ML verifier's prediction for a circuit, then the exact answer (up to 10 qubits)."""
    from qcanvas.mlverify import check

    try:
        spec = parse_spec(body.spec)
    except SpecError as err:
        raise HTTPException(422, {"message": str(err), "issues": _issues(err)}) from None
    if spec.kind != "circuit":
        raise HTTPException(422, "the ML verifier reads circuits")
    return (await asyncio.to_thread(check, spec, body.scale)).model_dump(mode="json")


@app.get("/api/mlverify/report")
def ml_verify_report() -> dict[str, Any]:
    """How the ML verifier was trained and how well it does on held-out and textbook circuits."""
    from qcanvas.mlverify import load_model

    m = load_model()
    return {"metrics": m.metrics, "q90": m.q90, "features": m.features, "scatter": m.scatter, "gallery": m.gallery}


class DiscoveryRequest(BaseModel):
    goal: str = Field(default="w4", max_length=20)
    ket: str | None = Field(default=None, max_length=400)
    deep: bool = False


@app.get("/api/discovery/goals")
def discovery_goals() -> dict[str, Any]:
    from qcanvas.discovery import goal_list

    return {"goals": [g.model_dump() for g in goal_list()]}


@app.post("/api/discovery")
def start_discovery(body: DiscoveryRequest) -> dict[str, Any]:
    """Autonomous discovery: Muse Spark proposes CNOT layouts, exact fitting and simulation prove and score them."""
    from qcanvas.discovery import GOALS, Discovery, custom_goal, discoveries, goal_target, launch

    try:
        if body.ket:
            goal, target = custom_goal(body.ket)
        elif body.goal in GOALS:
            goal, target = GOALS[body.goal], goal_target(GOALS[body.goal])
        else:
            raise ValueError(f"unknown goal {body.goal!r}")
    except ValueError as err:
        raise HTTPException(422, str(err)) from None
    d = Discovery(goal)
    discoveries.add(d)
    launch(d, target, get_models(), body.deep)
    return {"discovery_id": d.id, "events_url": f"/api/discovery/{d.id}/events"}


@app.get("/api/discovery/{discovery_id}/events")
async def discovery_events(discovery_id: str) -> EventSourceResponse:
    from qcanvas.discovery import discoveries

    d = discoveries.get(discovery_id)
    if d is None:
        raise HTTPException(404, "no such discovery run")

    async def stream():
        cursor = 0
        while True:
            events = d.bus.events(cursor)
            for event in events:
                yield {"event": "discovery", "id": str(event.seq), "data": json.dumps(event.details, default=str)}
            cursor += len(events)
            if d.bus.closed and not d.bus.events(cursor):
                yield {"event": "end", "data": json.dumps({"status": d.status, "error": d.error})}
                return
            await asyncio.sleep(0.15)

    return EventSourceResponse(stream(), ping=10)


@app.get("/api/discovery/{discovery_id}")
def discovery_status(discovery_id: str) -> dict[str, Any]:
    from qcanvas.discovery import discoveries

    d = discoveries.get(discovery_id)
    if d is None:
        raise HTTPException(404, "no such discovery run")
    return {"id": d.id, "status": d.status, "error": d.error, "result": d.result}


class LearningRequest(BaseModel):
    goal: str = Field(default="w4", max_length=20)


@app.get("/api/learning/benchmark")
def learning_benchmark() -> dict[str, Any]:
    """The recorded learning benchmark (scripts/learning_bench.py): with feedback, without, and random wiring."""
    path = EXAMPLES_DIR / "learning_benchmark.json"
    if not path.exists():
        raise HTTPException(404, "no recorded learning benchmark yet")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/learning")
def start_learning(body: LearningRequest) -> dict[str, Any]:
    """Run the three conditions live: Muse Spark proposes in rounds, exact physics judges every layout."""
    from qcanvas.learning import TARGETS, Session, launch, sessions

    if body.goal not in TARGETS:
        raise HTTPException(422, f"unknown goal {body.goal!r}")
    s = Session(TARGETS[body.goal])
    try:
        launch(s, get_models())
    except ValueError as err:
        raise HTTPException(409, str(err)) from None
    sessions.add(s)
    return {"learning_id": s.id, "events_url": f"/api/learning/{s.id}/events"}


@app.get("/api/learning/{learning_id}/events")
async def learning_events(learning_id: str) -> EventSourceResponse:
    from qcanvas.learning import sessions

    s = sessions.get(learning_id)
    if s is None:
        raise HTTPException(404, "no such learning run")

    async def stream():
        cursor = 0
        while True:
            events = s.bus.events(cursor)
            for event in events:
                yield {"event": "learning", "id": str(event.seq), "data": json.dumps(event.details, default=str)}
            cursor += len(events)
            if s.bus.closed and not s.bus.events(cursor):
                yield {"event": "end", "data": json.dumps({"status": s.status, "error": s.error})}
                return
            await asyncio.sleep(0.2)

    return EventSourceResponse(stream(), ping=10)


def _recorded(name: str) -> dict[str, Any]:
    path = EXAMPLES_DIR / name
    if not path.exists():
        raise HTTPException(404, f"no recorded {name} yet")
    return json.loads(path.read_text(encoding="utf-8"))


class RefereeRequest(BaseModel):
    index: int | None = Field(default=None, ge=0, le=20)
    spec: dict[str, Any] | None = None


@app.get("/api/referee/benchmark")
def referee_benchmark() -> dict[str, Any]:
    """The recorded AI referee benchmark (scripts/referee_bench.py)."""
    return _recorded("referee_benchmark.json")


@app.post("/api/referee")
def start_referee(body: RefereeRequest) -> dict[str, Any]:
    """A live debate on one circuit: Muse Spark claims, Muse Wonder challenges, exact simulation decides."""
    from qcanvas import referee
    from qcanvas.spec import parse_spec

    try:
        if body.spec is not None:
            spec, title = parse_spec(body.spec), "your circuit"
        else:
            import importlib.util

            path = PROJECT_DIR / "scripts" / "referee_bench.py"
            mod = importlib.util.module_from_spec(importlib.util.spec_from_file_location("referee_bench", path))
            mod.__spec__.loader.exec_module(mod)  # type: ignore[union-attr]
            title, raw = mod.circuits()[body.index or 0]
            spec = parse_spec(raw)
    except (ValueError, IndexError) as err:
        raise HTTPException(422, str(err)) from None
    if spec.kind != "circuit" or spec.num_qubits > 10:
        raise HTTPException(422, "a circuit of at most 10 qubits")
    s = referee.Session(spec, title)
    try:
        referee.launch(s, get_models())
    except ValueError as err:
        raise HTTPException(409, str(err)) from None
    referee.add(s)
    return {"referee_id": s.id}


@app.get("/api/referee/{referee_id}")
def referee_status(referee_id: str) -> dict[str, Any]:
    from qcanvas import referee

    s = referee.get(referee_id)
    if s is None:
        raise HTTPException(404, "no such debate")
    return {"id": s.id, "status": s.status, "error": s.error, "steps": s.steps, "result": s.result}


@app.get("/api/paper/examples")
def paper_examples() -> dict[str, Any]:
    """Recorded whole-paper reproductions."""
    return _recorded("paper_examples.json")


@app.post("/api/paper")
async def start_paper(arxiv: str = Form(""), pdf: UploadFile | None = File(None)) -> dict[str, Any]:
    """Reproduce a whole paper: an arXiv id or a PDF; Muse Wonder finds the experiments, Muse Spark transcribes each,
    exact simulation judges every stated probability."""
    from qcanvas import paper

    raw = await pdf.read() if pdf is not None else b""
    if raw and (len(raw) > paper.MAX_PDF or not raw.startswith(b"%PDF")):
        raise HTTPException(413, "a PDF of at most 20 MB")
    if not raw and not paper.ARXIV.match(arxiv.strip()):
        raise HTTPException(422, "give an arXiv id such as 1804.03719, or upload the PDF")
    s = paper.Session(pdf.filename if raw and pdf is not None else arxiv.strip())
    try:
        paper.launch(s, raw or None, arxiv, get_models())
    except ValueError as err:
        raise HTTPException(409, str(err)) from None
    paper.add(s)
    return {"paper_id": s.id}


@app.get("/api/paper/{paper_id}")
def paper_status(paper_id: str) -> dict[str, Any]:
    from qcanvas import paper

    s = paper.get(paper_id)
    if s is None:
        raise HTTPException(404, "no such paper run")
    return {"id": s.id, "status": s.status, "error": s.error, "source": s.source, "result": s.result}


class CodeRequest(BaseModel):
    generators: list[str] = Field(min_length=1, max_length=12)


@app.get("/api/codes")
def codes_lab() -> dict[str, Any]:
    """Code lab: known codes scored by the exact checker, and the recorded design runs (scripts/codes_bench.py)."""
    from qcanvas.codes import TARGETS, references

    path = EXAMPLES_DIR / "codes_benchmark.json"
    bench = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return {"references": references(), "targets": [t.model_dump() for t in TARGETS.values()], "benchmark": bench}


@app.post("/api/codes/analyse")
async def codes_analyse(body: CodeRequest) -> dict[str, Any]:
    """Check any stabilizer code exactly: commutation, independence, k, and the distances d, dX, dZ."""
    from qcanvas.codes import analyse

    return (await asyncio.to_thread(analyse, body.generators)).model_dump()


class DistributedRequest(BaseModel):
    spec: dict[str, Any]
    capacity: int | None = Field(default=None, ge=1, le=4)
    medium: str = Field(default="fiber", pattern="^(fiber|satellite)$")
    km: float = Field(default=1.0, gt=0, le=3000)


@app.post("/api/distributed")
async def distributed(body: DistributedRequest) -> dict[str, Any]:
    """One circuit on two chips joined by a quantum link: best split, remote CNOTs by teleportation, exact fidelity."""
    from qcanvas.distributed import distribute

    try:
        spec = parse_spec(body.spec)
        if spec.kind != "circuit":
            raise ValueError("the distributed computer takes circuits")
        res = await asyncio.to_thread(distribute, spec, body.capacity, body.medium, body.km)
    except SpecError as err:
        raise HTTPException(422, {"message": str(err), "issues": _issues(err)}) from None
    except ValueError as err:
        raise HTTPException(422, str(err)) from None
    return res.model_dump(mode="json")


class EstimateRequest(BaseModel):
    text: str | None = Field(default=None, max_length=2000)
    preset: str | None = Field(default=None, max_length=20)
    params: dict[str, Any] | None = None
    hardware: str = Field(default="superconducting", max_length=20)


@app.get("/api/estimate/presets")
def estimate_presets() -> dict[str, Any]:
    from qcanvas.estimator import HARDWARE, PRESETS

    return {"presets": [{"id": k, "label": v["label"]} for k, v in PRESETS.items()],
            "hardware": [h.model_dump() for h in HARDWARE.values()]}


@app.post("/api/estimate")
async def estimate(body: EstimateRequest) -> dict[str, Any]:
    """When does quantum win? Muse Spark maps the problem; error-corrected estimates against the classical route."""
    from qcanvas.estimator import MAP_SCHEMA, MAP_SYSTEM, PRESETS, estimate as run, offline_map

    call = None
    read_by = "preset"
    if body.preset:
        if body.preset not in PRESETS:
            raise HTTPException(422, f"unknown preset {body.preset!r}")
        params = PRESETS[body.preset]
    elif body.params:
        params, read_by = body.params, "params"
    elif body.text and body.text.strip():
        models = get_models()
        if models.settings.provider == "meta" and models.settings.has_key:
            try:
                params, call = await asyncio.to_thread(models.reasoning.structured, MAP_SYSTEM, body.text.strip(),
                                                       MAP_SCHEMA, "problem_map", "low", 4000)
                read_by = "muse"
            except Exception as err:  # noqa: BLE001 - the keyword reader stands in, labelled
                params, read_by = offline_map(body.text), f"offline (the model failed: {str(err)[:80]})"
        else:
            params, read_by = offline_map(body.text), "offline"
    else:
        raise HTTPException(422, "give a problem, a preset or parameters")
    res = run(params, body.hardware)
    res.read_by = read_by
    out = res.model_dump(mode="json")
    out["call"] = call.model_dump(mode="json") if call else None
    out["mapped"] = params
    return out


@app.post("/api/live/read")
async def live_read(file: UploadFile = File(...)) -> dict[str, Any]:
    """Live board: one camera frame read by SAM 3.1 + Muse Spark, simulated exactly, odds pinned to the wires."""
    import time

    from qcanvas.live import read_frame

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "the frame is empty")
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "the frame is larger than 15 MB")
    start = time.perf_counter()
    try:
        analysis, _ = await asyncio.to_thread(analyze_image, raw, get_models())
    except UnknownImageError:
        raise HTTPException(422, "Offline, only the sample sketches can be read; the live board needs the Meta key.") from None
    except ModelUnavailable as err:
        raise HTTPException(502, f"A Meta model call failed: {err}") from None
    except OSError as err:
        raise HTTPException(400, f"could not read the frame: {err}") from None
    read_s = time.perf_counter() - start
    result = await asyncio.to_thread(read_frame, analysis)
    return {"analysis": analysis.model_dump(mode="json"), "result": result, "read_seconds": round(read_s, 2),
            "total_seconds": round(time.perf_counter() - start, 2)}


@app.get("/api/orbits/cities")
def orbit_cities() -> dict[str, Any]:
    from qcanvas.orbits import CITIES, MICIUS, PAIRS
    from qcanvas.satellites import SATELLITES

    sats = [{"id": k, "name": v["name"], "norad": v["norad"], "real": True, "status": "in orbit"} for k, v in SATELLITES.items()]
    sats.append({"id": "micius", "name": MICIUS["name"], "norad": MICIUS["norad"], "real": False, "status": MICIUS["status"]})
    return {"cities": [{"id": k, "name": v[0], "lat": v[1], "lon": v[2]} for k, v in CITIES.items()],
            "pairs": [{"a": a, "b": b, "label": label, "sat": sat} for a, b, label, sat in PAIRS], "satellites": sats}


@app.get("/api/orbits")
async def orbits(a: str = "delingha", b: str = "lijiang", night: bool = True, sat: str = "micius") -> dict[str, Any]:
    """A quantum satellite over two cities: SpeQtre or QUBE-II on today's real orbit (CelesTrak, SGP4) under the
    cloud forecast, or Micius (re-entered January 2026) on a modelled orbit; every pass and the key it gives."""
    from qcanvas.orbits import plan

    try:
        return (await asyncio.to_thread(plan, a, b, night, sat)).model_dump(mode="json")
    except ValueError as err:
        raise HTTPException(422, str(err)) from None


@app.post("/api/reproduce")
async def reproduce_paper(text: str = Form(""), image: UploadFile | None = File(None)) -> dict[str, Any]:
    """Paper reproducibility: a figure and/or its caption and OpenQASM; the circuit re-run exactly; each claim judged."""
    from qcanvas.reproduce import reproduce

    raw = await image.read() if image is not None else b""
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "the image is larger than 15 MB")
    if not raw and not text.strip():
        raise HTTPException(422, "give a figure, or paste a caption with OpenQASM")
    models = get_models()
    live = models.settings.provider == "meta" and models.settings.has_key
    try:
        res = await asyncio.to_thread(reproduce, raw or None, text[:6000], models if live else None)
    except ValueError as err:
        raise HTTPException(422, str(err)) from None
    except ModelUnavailable as err:
        raise HTTPException(502, f"A Meta model call failed: {err}") from None
    return res.model_dump(mode="json")


@app.get("/api/decoder")
def decoder_report(p: float = 0.01, seed: int = 1, d: int = 3) -> dict[str, Any]:
    """Surface-code decoders: matching against the neural network (stored evaluations at distance 3 and 5) and one
    sampled shot at the chosen distance."""
    from qcanvas.decoder import example, model, model_d5

    if not 0.001 <= p <= 0.1:
        raise HTTPException(422, "p must be between 0.001 and 0.1")
    m5 = model_d5()
    if d not in (3, 5) or (d == 5 and m5 is None):
        raise HTTPException(422, "distance 3, or 5 once its decoder is trained")
    m = model()
    return {"curve": m["curve"], "train_shots": m["train_shots"], "train_p": m["train_p"], "rounds": m["rounds"],
            "d5": None if m5 is None else {"curve": m5["curve"], "train_shots": m5["train_shots"], "train_p": m5["train_p"]},
            "example": example(round(p, 4), seed, d)}


@app.get("/api/pulse")
async def pulse_lab(duration: float = 20.0, drag: bool = True) -> dict[str, Any]:
    """Pulse lab: a pi pulse on a three-level transmon with T1/T2, Gaussian or DRAG, and the duration sweep."""
    from qcanvas.pulse import run, sweep

    if not 4 <= duration <= 100:
        raise HTTPException(422, "duration must be between 4 and 100 ns")
    r, s = await asyncio.gather(asyncio.to_thread(run, round(duration, 1), drag), asyncio.to_thread(sweep))
    return {"run": r.model_dump(mode="json"), "sweep": s.model_dump(mode="json")}


@app.get("/api/hardware")
def hardware_runs() -> dict[str, Any]:
    """Counts from a real IBM device next to Q-Canvas's predictions (scripts/hardware_check.py); 404 before a run."""
    path = EXAMPLES_DIR / "hardware_runs.json"
    if not path.exists():
        raise HTTPException(404, "no real hardware run yet")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/observatory")
async def observatory_charts() -> dict[str, Any]:
    """Five exact sweeps: satellites vs fiber, quantum walk, Grover vs noise, entanglement growth, the memory wall."""
    from qcanvas.observatory import observatory

    return (await asyncio.to_thread(observatory)).model_dump(mode="json")


@app.get("/api/lab/repetition")
def lab_repetition(scale: float = 1.0) -> dict[str, Any]:
    """The bit-flip code against a bare qubit, with perfect and with ``scale`` x realistic gates."""
    from qcanvas.qec import repetition_lab

    if not 0 <= scale <= 20:
        raise HTTPException(422, "scale must be between 0 and 20")
    return repetition_lab(float(f"{scale:.3g}")).model_dump(mode="json")


@app.get("/api/lab/shor")
def lab_shor(a: int = 7) -> dict[str, Any]:
    """Shor's algorithm for 15 with base ``a``: exact odds, seeded shots and the classical finish."""
    from qcanvas.shor import shor_lab

    if not 2 <= a <= 14:
        raise HTTPException(422, "a must be between 2 and 14")
    return shor_lab(a).model_dump(mode="json")


@app.get("/api/lab/chem")
async def lab_chem(r: float = 0.74) -> dict[str, Any]:
    """H2 from first principles at bond length ``r`` (angstrom): Hartree-Fock, exact, and VQE raw and mitigated."""
    from qcanvas.chem import chem_lab

    if not 0.25 <= r <= 3.5:
        raise HTTPException(422, "bond length must be between 0.25 and 3.5 angstrom")
    return (await asyncio.to_thread(chem_lab, round(r, 2))).model_dump(mode="json")


@app.get("/api/lab/qkd")
def lab_qkd(photons: int = 1000, eve: float = 0.0, noise: float = 0.01, seed: int = 7) -> dict[str, Any]:
    """BB84 with an intercept-resend eavesdropper on a share ``eve`` of the photons."""
    from qcanvas.qkd import bb84

    try:
        return bb84(photons, eve, noise, seed).model_dump(mode="json")
    except ValueError as err:
        raise HTTPException(422, str(err)) from None


class QaoaRequest(BaseModel):
    n: int = Field(ge=3, le=8)
    edges: list[tuple[int, int]] = Field(max_length=40)
    labels: list[str] | None = Field(default=None, max_length=8)


@app.post("/api/lab/qaoa")
async def lab_qaoa(body: QaoaRequest) -> dict[str, Any]:
    """QAOA Max-Cut on a small graph: brute-force answer, depth-1 landscape, optimized depths 1 to 3."""
    from qcanvas.qaoa import qaoa_lab

    labels = [str(x).strip()[:12] for x in body.labels] if body.labels else None
    try:
        lab = await asyncio.to_thread(qaoa_lab, body.n, body.edges, "realistic", labels)
    except ValueError as err:
        raise HTTPException(422, str(err)) from None
    return lab.model_dump(mode="json")


class CopilotRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=12)
    deep: bool = False  # Muse Wonder instead of Muse Spark


@app.post("/api/copilot")
async def copilot(body: CopilotRequest) -> dict[str, Any]:
    """Ask Q-Canvas: Muse Spark (or Muse Wonder in deep mode) calls the exact tools; every number is traced."""
    from functools import partial

    from qcanvas.copilot import DEEP_ROUNDS, MAX_ROUNDS, ask_live, ask_offline

    models = get_models()
    if models.settings.provider == "meta" and models.settings.has_key:
        try:
            chat = models.reasoning.tool_chat
            if body.deep:
                chat = partial(chat, model=models.settings.deep_model, effort="medium")
            reply = await asyncio.to_thread(ask_live, body.message, body.history, chat,
                                            DEEP_ROUNDS if body.deep else MAX_ROUNDS)
        except Exception as err:  # noqa: BLE001 - reported, never replaced by a made-up answer
            raise HTTPException(502, f"The assistant failed: {err}") from None
    else:
        reply = await asyncio.to_thread(ask_offline, body.message)
    return reply.model_dump(mode="json")


class RosettaRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@app.post("/api/rosetta")
async def rosetta(body: RosettaRequest) -> dict[str, Any]:
    """Quantum Rosetta: Dirac notation, OpenQASM, Quil, Qiskit, other code or words in; math, a proven circuit,
    words and eight languages out."""
    from qcanvas.notation import NotationError
    from qcanvas.rosetta import ReadError, translate
    from qcanvas.spec import SpecError

    try:
        res = await asyncio.to_thread(translate, body.text, get_models())
    except (ReadError, NotationError, SpecError) as err:
        raise HTTPException(422, str(err)) from None
    except ModelUnavailable as err:
        raise HTTPException(502, f"A Meta model call failed and fallback is off: {err}") from None
    return res.model_dump(mode="json")


@app.get("/api/rosetta/dictionary")
async def rosetta_dictionary() -> dict[str, Any]:
    """The words of quantum computing, each with an example state computed exactly."""
    from qcanvas.rosetta import dictionary

    return {"entries": await asyncio.to_thread(dictionary)}


@app.post("/api/rosetta/photo")
async def rosetta_photo(file: UploadFile = File(...)) -> dict[str, Any]:
    """A photo of notation (textbook, slide, whiteboard) -> text, by Muse Spark; live only, never guessed offline."""
    from qcanvas.adapters.imaging import normalise_upload

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "the upload is empty")
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "the image is larger than 15 MB")
    models = get_models()
    if not (models.settings.provider == "meta" and models.settings.has_key):
        raise HTTPException(409, "Reading a photo of notation needs the live model (Muse Spark). Type or paste it instead.")
    try:
        data, mime, _, _ = normalise_upload(raw)
        read = await asyncio.to_thread(models.reasoning.read_notation, data, mime)
    except OSError as err:
        raise HTTPException(400, f"could not read the image: {err}") from None
    except Exception as err:  # noqa: BLE001 - reported, never replaced by a guess
        raise HTTPException(502, f"Muse Spark could not read the photo: {err}") from None
    return read.model_dump(mode="json")


class ArenaRequest(BaseModel):
    spec: dict[str, Any]


@app.post("/api/arena")
async def arena(body: ArenaRequest) -> dict[str, Any]:
    """Ask Muse Spark alone (no simulator) what the circuit outputs, and score it against the exact truth."""
    from qcanvas.arena import ask_alone

    try:
        spec = parse_spec(body.spec)
    except SpecError as err:
        raise HTTPException(422, {"message": "The spec has problems", "issues": _issues(err)}) from None
    if spec.kind != "circuit" or not spec.measured_pairs():
        raise HTTPException(422, "needs a circuit with measurements")
    models = get_models()
    if models.settings.provider != "meta" or not models.settings.has_key:
        raise HTTPException(409, "asking the AI alone needs the live model; the start page shows the recorded results")
    try:
        res = await asyncio.to_thread(ask_alone, spec, models.reasoning.predict_odds)
    except Exception as err:  # noqa: BLE001 - reported, never replaced by a made-up answer
        raise HTTPException(502, f"Muse Spark could not answer: {err}") from None
    return res.model_dump(mode="json")


@app.get("/api/arena/benchmark")
def arena_benchmark(model: str = "spark") -> dict[str, Any]:
    """The recorded AI-alone benchmark (scripts/arena_bench.py): Muse Spark, or Muse Glimmer run locally (--glimmer)."""
    from qcanvas.arena import BENCH_FILE, load_benchmark

    files = {"spark": BENCH_FILE, "glimmer": BENCH_FILE.with_name(BENCH_FILE.stem + "_glimmer.json")}
    if model not in files:
        raise HTTPException(422, "model is spark or glimmer")
    bench = load_benchmark(files[model])
    if bench is None:
        raise HTTPException(404, "no recorded benchmark yet")
    return bench.model_dump(mode="json") | {"available": [k for k, f in files.items() if f.exists()]}


@app.get("/api/bughunt/round")
async def bughunt_round(level: int = 1, seed: int = 0) -> dict[str, Any]:
    """A bug-hunt round: a known circuit with one wrong gate, what it should give and what it gave."""
    from qcanvas.bughunt import LEVELS, bug_round

    if level not in LEVELS or not 0 <= seed < 10**9:
        raise HTTPException(422, "level is 1, 2 or 3 and seed a non-negative integer")
    return (await asyncio.to_thread(bug_round, level, seed)).model_dump(mode="json")


class BugGuessRequest(BaseModel):
    level: int = Field(ge=1, le=3)
    seed: int = Field(ge=0, lt=10**9)
    index: int = Field(ge=0, le=200)


@app.post("/api/bughunt/guess")
async def bughunt_guess(body: BugGuessRequest) -> dict[str, Any]:
    """Grade a pick: right if one edit of that gate restores the intended odds exactly; reveals the machine's search."""
    from qcanvas.bughunt import judge

    return (await asyncio.to_thread(judge, body.level, body.seed, body.index)).model_dump(mode="json")


class BugRoundRequest(BaseModel):
    level: int = Field(ge=1, le=3)
    seed: int = Field(ge=0, lt=10**9)


@app.post("/api/bughunt/muse")
async def bughunt_muse(body: BugRoundRequest) -> dict[str, Any]:
    """Muse Spark's pick for the same round (live only; it sees what the player sees)."""
    from qcanvas.bughunt import muse_facts

    models = get_models()
    if models.settings.provider != "meta" or not models.settings.has_key:
        raise HTTPException(409, "Muse Spark plays in live mode")
    facts = await asyncio.to_thread(muse_facts, body.level, body.seed)
    try:
        guess = await asyncio.to_thread(models.reasoning.find_bug, facts)
    except Exception as err:  # noqa: BLE001 - reported, never replaced by a made-up pick
        raise HTTPException(502, f"Muse Spark could not play: {err}") from None
    return guess.model_dump(mode="json")


class ChallengeRequest(BaseModel):
    spec: dict[str, Any]
    number: int = Field(default=0, ge=0, le=9)


def _challenge(challenge_id: str) -> Any:
    from qcanvas.challenges import BY_ID

    ch = BY_ID.get(challenge_id)
    if ch is None:
        raise HTTPException(404, "no such challenge")
    return ch


@app.get("/api/challenges")
def challenges() -> dict[str, Any]:
    """The puzzle list, with each target (state amplitudes or a gate's truth table); never the solutions."""
    from qcanvas.challenges import CHALLENGES, LEVELS, info

    return {"levels": LEVELS, "challenges": [info(c).model_dump(mode="json") for c in CHALLENGES]}


@app.post("/api/challenges/{challenge_id}/check")
def challenge_check(challenge_id: str, body: ChallengeRequest) -> dict[str, Any]:
    """Score a circuit against a challenge exactly: fidelity, stars against par, and what is still off."""
    from qcanvas.challenges import check

    return check(_challenge(challenge_id), body.spec).model_dump(mode="json")


@app.post("/api/challenges/{challenge_id}/hint")
async def challenge_hint(challenge_id: str, body: ChallengeRequest) -> dict[str, Any]:
    """One hint for where the player's circuit is now (Muse Spark live; the author's hints offline)."""
    from qcanvas.challenges import hint_facts

    facts = hint_facts(_challenge(challenge_id), body.spec, body.number)
    try:
        hint = await asyncio.to_thread(get_models().reasoning.hint, facts)
    except ModelUnavailable as err:
        raise HTTPException(502, f"A Meta model call failed and fallback is off: {err}") from None
    return hint.model_dump(mode="json")


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


@app.get("/api/jobs/{job_id}/report")
def report(job_id: str) -> Response:
    """A self-contained HTML report of a finished run."""
    from qcanvas.report import render_report

    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    if job.result is None:
        raise HTTPException(409, "the run has not finished yet")
    name = "".join(c if c.isalnum() else "_" for c in (job.spec.metadata.title or "qcanvas")).strip("_").lower()
    return Response(render_report(job.spec, job.result), media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name or "qcanvas"}_report.html"'})


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


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict[str, Any]:
    """A short spoken description -> text (Muse Voice Transcribe; live mode only, never faked offline)."""
    from qcanvas.adapters.voice import AudioError, check_wav

    raw = await audio.read()
    if len(raw) > 4_000_000:
        raise HTTPException(413, "keep the recording under a minute")
    try:
        check_wav(raw)
    except AudioError as err:
        raise HTTPException(400, str(err)) from None
    models = get_models()
    if models.settings.provider != "meta":
        raise HTTPException(409, "offline mode cannot transcribe audio; the browser's own speech recognition is used instead")
    try:
        out = await asyncio.to_thread(models.speech.transcribe, raw)
    except Exception as err:  # noqa: BLE001 - reported, never replaced by a made-up transcript
        raise HTTPException(502, f"Transcription failed: {err}") from None
    if not out.text:
        raise HTTPException(422, "no speech was heard in the recording")
    return out.model_dump(mode="json")


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
