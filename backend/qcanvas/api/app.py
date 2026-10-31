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


ALGORITHMS = {"grover2", "bernstein_vazirani", "deutsch_jozsa", "phase_estimation", "superdense", "toffoli_and",
              "teleportation", "w_state", "bit_flip_code", "shor15"}


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
def arena_benchmark() -> dict[str, Any]:
    """The recorded AI-alone benchmark (scripts/arena_bench.py)."""
    from qcanvas.arena import load_benchmark

    bench = load_benchmark()
    if bench is None:
        raise HTTPException(404, "no recorded benchmark yet")
    return bench.model_dump(mode="json")


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
