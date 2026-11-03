"""The lecture checker: a filmed explanation of a circuit in, every spoken claim checked against the board as it was.

Five Meta models, each on the part it is built for, and exact physics on the part no model should own:

1. **Muse Voice Transcribe** in diarization mode: who said what, and when.
2. **SAM 3.1** on the video: every drawn part tracked through the clip, so we know when each one appeared.
3. **Muse Spark** reads the finished board (with SAM's boxes) into a circuit, and writes each spoken claim out
   formally (which qubits, which outcomes, which board version it is about). It never judges a claim.
4. **Exact simulation** judges each claim against the circuit as drawn at that moment.
5. **Muse Wonder** writes corrected notes from the verdicts; **Muse Image** draws a clean figure of the final board.

Offline, only the bundled sample (scripts/make_lecture.py) can be checked: its script's own record stands in for the
models, labelled as such. The checks are the same exact code in both modes.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from inkubit import EXAMPLES_DIR
from inkubit.adapters.base import ModelCall, Segment, SegmentationResult, TrackResult

LECTURE_DIR = EXAMPLES_DIR / "lecture"
TRACK_FPS = 2.0
TRACK_CONCEPTS = ["square", "circle"]  # what SAM 3.1 tracks reliably on pen sketches (measured on the sample)
MAX_SECONDS = 60.0
MAX_BYTES = 40_000_000
GRACE_S = 1.0  # a board version may be named if it appeared up to this long after the turn ended
KEYWORDS = ["qubit", "qubits", "Hadamard", "CNOT", "Toffoli", "GHZ", "W state", "Bell", "entangled", "superposition",
            "probability", "measure", "zero", "one"]
STATES = ["GHZ", "W", "Bell", "zero", "uniform", "none"]
KINDS = ["probability", "outcomes", "entangled", "not_entangled", "state", "other"]

CLAIMS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["claims"], "properties": {"claims": {
    "type": "array", "maxItems": 24, "items": {
        "type": "object", "additionalProperties": False,
        "required": ["turn", "quote", "kind", "board", "qubits", "outcome", "value", "outcomes", "state"],
        "properties": {
            "turn": {"type": "integer", "description": "Index of the turn the claim was made in."},
            "quote": {"type": "string", "description": "The exact words of the claim, copied from the turn."},
            "kind": {"type": "string", "enum": KINDS},
            "board": {"type": "integer", "description": "Index of the board version the claim is about."},
            "qubits": {"type": "array", "items": {"type": "integer"}},
            "outcome": {"type": "string", "description": "probability: one bit per listed qubit, in that order; else ''."},
            "value": {"type": "number", "description": "probability: the stated probability 0..1; else -1."},
            "outcomes": {"type": "array", "items": {"type": "string"},
                         "description": "outcomes: every outcome the speaker says can occur, one bit per listed qubit."},
            "state": {"type": "string", "enum": STATES, "description": "state: the named state; else none."}}}}}}

CLAIMS_SYSTEM = (
    "You turn a spoken explanation of a quantum circuit into checkable claims. You do not judge them: an exact "
    "simulator will. Read every turn and write out each statement that asserts something checkable about the qubits "
    "(a question asked as an assertion, like 'X is true, right?', is the asker's claim too). Kinds: probability "
    "(the chance that the listed qubits read the given bits), outcomes (the complete set of outcomes the listed "
    "qubits can show; use it for 'we only ever see ...' or 'exactly one reads one'), entangled (every listed qubit is "
    "entangled with the rest), not_entangled (every listed qubit is in a state of its own), state (the listed qubits "
    "are in the named state: GHZ, W, Bell, zero for all reading 0, uniform for an equal superposition of everything), "
    "other (checkable in principle but not one of these; give the quote only). Number qubits from 0 as on the board "
    "(the first or top qubit is 0). Bits in outcome and outcomes follow the order of the qubits you list. Pick the "
    "board version the claim is about: the one on the board when it was said, or one drawn during that turn if the "
    "speaker is describing what was just drawn. Skip statements about drawing itself, greetings and plans. Quote "
    "the speaker's exact words.")

NOTES_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["title", "summary", "sections", "corrections"],
                "properties": {
                    "title": {"type": "string"}, "summary": {"type": "string"},
                    "sections": {"type": "array", "maxItems": 6, "items": {
                        "type": "object", "additionalProperties": False, "required": ["heading", "text"],
                        "properties": {"heading": {"type": "string"}, "text": {"type": "string"}}}},
                    "corrections": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["quote", "speaker", "correction"],
                        "properties": {"quote": {"type": "string"}, "speaker": {"type": "string"},
                                       "correction": {"type": "string"}}}}}}

NOTES_SYSTEM = (
    "You write study notes from a short lecture about a quantum circuit. Every claim in it was checked by exact "
    "simulation; you get the verdicts and the exact numbers. Keep what was right, correct what was wrong using only "
    "the given numbers, and add nothing that was not checked. Plain, short sentences a student can learn from. One "
    "correction per wrong claim, naming who said it.")


class LectureError(ValueError):
    """The upload cannot be checked (too long, no sound, not a video...)."""


# ---------- the bundled sample ----------

@lru_cache(maxsize=1)
def _sample() -> dict[str, Any]:
    return json.loads((LECTURE_DIR / "lecture.json").read_text(encoding="utf-8"))


def sample_video() -> bytes:
    return (LECTURE_DIR / "lecture.mp4").read_bytes()


def sample_record(source: str) -> dict[str, Any]:
    """The sample's own record, if ``source`` (a SHA-256) is the sample; offline stand-ins use nothing else."""
    rec = _sample()
    if source != rec["sha256"]:
        raise RuntimeError("offline, only the bundled sample lecture can be checked; uploads need the live models")
    return rec


# ---------- media ----------

def _ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


class Media:
    """What the checker cuts out of a video: the sound, a 2-frames-a-second clip for SAM, the last frame, and small
    grey frames for a pixel fallback."""

    def __init__(self, video: bytes):
        if len(video) > MAX_BYTES:
            raise LectureError(f"keep the video under {MAX_BYTES // 1_000_000} MB")
        self.sha = hashlib.sha256(video).hexdigest()
        ff = _ffmpeg()
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.mp4"
            src.write_bytes(video)
            probe = subprocess.run([ff, "-hide_banner", "-i", str(src)], capture_output=True, text=True)
            self.duration = _duration(probe.stderr)
            if self.duration is None or "Video:" not in probe.stderr:
                raise LectureError("that file is not a video ffmpeg can read")
            if "Audio:" not in probe.stderr:
                raise LectureError("the video has no sound track, so there is nothing to check")
            if self.duration > MAX_SECONDS + 0.5:
                raise LectureError(f"keep the lecture under {MAX_SECONDS:.0f} seconds")
            scale = "scale='min(1280,iw)':-2"
            wav = Path(td) / "sound.wav"  # a file, not a pipe: a piped WAV header carries no length
            subprocess.run([ff, "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
                            "-acodec", "pcm_s16le", str(wav)], check=True)
            self.wav = wav.read_bytes()
            clip = Path(td) / "clip.mp4"
            subprocess.run([ff, "-loglevel", "error", "-y", "-i", str(src), "-an", "-vf", f"fps={TRACK_FPS:g},{scale}",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(clip)], check=True)
            self.clip = clip.read_bytes()
            self.final = _run([ff, "-loglevel", "error", "-sseof", "-0.6", "-i", str(src), "-frames:v", "1",
                               "-vf", scale, "-f", "image2", "-vcodec", "png", "-"])
            from PIL import Image
            import io

            self.width, self.height = Image.open(io.BytesIO(self.final)).size
            raw = _run([ff, "-loglevel", "error", "-i", str(clip), "-vf", "scale=320:-2,format=gray", "-f", "rawvideo", "-"])
            h = round(320 * self.height / self.width / 2) * 2
            n = len(raw) // (320 * h)
            self.grey = np.frombuffer(raw[: n * 320 * h], dtype=np.uint8).reshape(n, h, 320).astype(np.int16)


def _run(cmd: list[str]) -> bytes:
    out = subprocess.run(cmd, capture_output=True)
    if out.returncode != 0 or not out.stdout:
        raise LectureError("ffmpeg could not read the video: " + out.stderr.decode(errors="replace")[-200:])
    return out.stdout


def _duration(stderr: str) -> float | None:
    for line in stderr.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            hms = line.split(",")[0].split()[1]
            try:
                h, m, s = hms.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
            except ValueError:
                return None
    return None


# ---------- when each operation appeared ----------

def _inside(track_bbox: tuple[float, ...], box: tuple[float, ...], pad: float = 14.0) -> bool:
    cx, cy = (track_bbox[0] + track_bbox[2]) / 2, (track_bbox[1] + track_bbox[3]) / 2
    return box[0] - pad <= cx <= box[2] + pad and box[1] - pad <= cy <= box[3] + pad


def _pixels_first(media: Media, box: tuple[float, ...]) -> float | None:
    """When the region first changed for good, from the grey frames (no model): the fallback for an operation SAM
    did not track."""
    if media.grey.size == 0:
        return None
    k = media.grey.shape[2] / media.width
    x1, y1 = max(0, int(box[0] * k)), max(0, int(box[1] * k))
    x2, y2 = min(media.grey.shape[2], int(math.ceil(box[2] * k)) + 1), min(media.grey.shape[1], int(math.ceil(box[3] * k)) + 1)
    if x2 <= x1 or y2 <= y1:
        return None
    region = media.grey[:, y1:y2, x1:x2]
    final = region[-1]
    changed = np.abs(region - region[0]).mean(axis=(1, 2)) > 6
    settled = np.abs(region - final).mean(axis=(1, 2)) < 4
    for i in range(len(region)):
        if changed[i] and settled[i:].all():
            return round(i / TRACK_FPS, 2)
    return None


def op_times(spec: dict[str, Any], tracks: TrackResult, media: Media | None) -> list[dict[str, Any]]:
    """For each operation: when it was complete on the board, and how we know (the tracks inside its box, else the
    pixels, else unknown)."""
    out = []
    for i, op in enumerate(spec.get("operations", [])):
        src = op.get("source") or {}
        box = tuple(src.get("bbox") or ())
        hits = [t for t in tracks.tracks if t.id == src.get("segment_id") or (len(box) == 4 and _inside(t.bbox, box))]
        if hits:
            out.append({"op": i, "appears": max(t.first_s for t in hits), "how": "tracked by SAM 3.1",
                        "tracks": [t.id for t in hits]})
            continue
        at = _pixels_first(media, box) if media is not None and len(box) == 4 else None
        out.append({"op": i, "appears": at if at is not None else 0.0,
                    "how": "first change in the pixels" if at is not None else "unknown, taken as there from the start",
                    "tracks": []})
    return out


def versions(times: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The board as it grew: version k holds every operation that had appeared by its time."""
    starts = sorted({0.0} | {t["appears"] for t in times})
    return [{"index": k, "time": s, "ops": [t["op"] for t in times if t["appears"] <= s]} for k, s in enumerate(starts)]


def op_label(op: dict[str, Any]) -> str:
    q = ", ".join(f"q{t}" for t in op.get("targets", []))
    if op.get("controls"):
        return f"{op['gate']} {','.join(f'q{c}' for c in op['controls'])}→{q}"
    return f"{op['gate']}({', '.join(f'{p:.2f}' for p in op['params'])}) on {q}" if op.get("params") else f"{op['gate']} on {q}"


# ---------- exact checks ----------

def _statevector(spec: dict[str, Any], ops: list[int]):
    from qiskit.quantum_info import Statevector

    from inkubit.spec.validation import parse_spec
    from inkubit.verify.expected import build_reference_circuit

    n = int(spec["num_qubits"])
    if not ops:
        return Statevector.from_label("0" * n)
    sub = {**spec, "operations": [spec["operations"][i] for i in ops], "metadata": {},
           "num_clbits": n, "measurements": [{"qubit": q, "clbit": q} for q in range(n)]}
    return Statevector(build_reference_circuit(parse_spec(sub)))


def _target(name: str, m: int):
    from qiskit.quantum_info import Statevector

    v = np.zeros(2 ** m, dtype=complex)
    if name in ("GHZ", "Bell"):
        v[0] = v[-1] = 1
    elif name == "W":
        for k in range(m):
            v[1 << k] = 1
    elif name == "zero":
        v[0] = 1
    elif name == "uniform":
        v[:] = 1
    return Statevector(v / np.linalg.norm(v))


def _reduced(sv, keep: list[int]):
    from qiskit.quantum_info import DensityMatrix, partial_trace

    others = [q for q in range(sv.num_qubits) if q not in keep]
    return partial_trace(sv, others) if others else DensityMatrix(sv)


def check_claim(spec: dict[str, Any], ops: list[int], claim: dict[str, Any]) -> dict[str, Any]:
    """Judge one formal claim exactly; returns verdict (true, false, unclear), a sentence and the numbers."""
    n = int(spec["num_qubits"])
    qubits = [int(q) for q in claim.get("qubits") or []]
    kind = claim.get("kind")
    if kind == "other" or not qubits:
        return {"verdict": "unclear", "detail": "Not a kind of claim the simulator can settle on its own.", "numbers": {}}
    if any(q < 0 or q >= n for q in qubits) or len(set(qubits)) != len(qubits):
        return {"verdict": "unclear", "detail": f"Names a qubit the board does not have (it has q0 to q{n - 1}).",
                "numbers": {}}
    sv = _statevector(spec, ops)
    probs = {k[::-1]: float(v) for k, v in sv.probabilities_dict(qargs=qubits).items() if v > 1e-12}
    names = " ".join(f"q{q}" for q in qubits)
    if kind == "probability":
        bits, want = str(claim.get("outcome", "")), float(claim.get("value", -1))
        if len(bits) != len(qubits) or set(bits) - {"0", "1"} or not 0 <= want <= 1:
            return {"verdict": "unclear", "detail": "The claim's outcome or probability could not be read.", "numbers": {}}
        p = probs.get(bits, 0.0)
        ok = abs(p - want) <= 0.02
        return {"verdict": "true" if ok else "false", "numbers": {"exact": round(p, 4), "stated": want},
                "detail": f"P({names} = {bits}) is exactly {p:.3f}" + ("." if ok else f", not {want:g}.")}
    if kind == "outcomes":
        said = sorted({str(o) for o in claim.get("outcomes") or []})
        if not said or any(len(o) != len(qubits) or set(o) - {"0", "1"} for o in said):
            return {"verdict": "unclear", "detail": "The stated outcomes could not be read.", "numbers": {}}
        real = sorted(k for k, v in probs.items() if v > 1e-9)
        ok = said == real
        return {"verdict": "true" if ok else "false", "numbers": {"possible": real, "stated": said},
                "detail": f"{names} can read " + ", ".join(f"{k} ({probs[k]:.2f})" for k in real)
                          + ("." if ok else "; the claim said " + ", ".join(said) + ".")}
    if kind in ("entangled", "not_entangled"):
        purity = {q: float(np.real(_reduced(sv, [q]).purity())) for q in qubits}
        tangled = {q: p < 0.999 for q, p in purity.items()}
        ok = all(tangled.values()) if kind == "entangled" else not any(tangled.values())
        parts = [f"q{q} {'is entangled' if t else 'is in a state of its own'} (purity {purity[q]:.3f})"
                 for q, t in tangled.items()]
        return {"verdict": "true" if ok else "false", "numbers": {f"purity_q{q}": round(p, 4) for q, p in purity.items()},
                "detail": "; ".join(parts) + "."}
    if kind == "state":
        name = claim.get("state", "none")
        if name not in STATES[:-1]:
            return {"verdict": "unclear", "detail": "The named state could not be read.", "numbers": {}}
        rho = _reduced(sv, sorted(qubits))
        fid = {}
        for s in STATES[:-1]:
            if s == "Bell" and len(qubits) != 2:
                continue
            t = _target(s, len(qubits)).data  # every named state is symmetric under swapping qubits, so order is moot
            fid[s] = float(np.real(t.conj() @ rho.data @ t))
        best = max(fid, key=fid.get)
        ok = fid[name] >= 0.99
        detail = f"Fidelity with the {name} state is {fid[name]:.3f}"
        detail += "." if ok else (f"; it is the {best} state ({fid[best]:.3f})." if fid[best] >= 0.99
                                  else f"; the closest named state is {best} ({fid[best]:.3f}).")
        return {"verdict": "true" if ok else "false", "numbers": {k: round(v, 4) for k, v in fid.items()},
                "detail": detail}
    return {"verdict": "unclear", "detail": "Unknown kind of claim.", "numbers": {}}


# ---------- the run ----------

STEPS = [("media", "Cut the clip", "ffmpeg"), ("listen", "Who said what, and when", "Muse Voice (diarization)"),
         ("track", "What was drawn, and when", "SAM 3.1 (video)"), ("read", "Read the finished board", "Muse Spark"),
         ("claims", "Write each claim out", "Muse Spark"), ("check", "Check every claim", "exact simulation"),
         ("notes", "Corrected notes", "Muse Wonder"),
         ("figure", "Clean figure, read back and proven", "Muse Image, SAM 3.1, Muse Spark")]


class Session:
    def __init__(self, source: str):
        self.id = uuid.uuid4().hex[:12]
        self.source = source
        self.status = "running"
        self.error: str | None = None
        self.result: dict[str, Any] | None = None
        self.steps = [{"id": i, "label": label, "by": by, "status": "waiting", "detail": "", "seconds": None}
                      for i, label, by in STEPS]
        self._t: dict[str, float] = {}
        self.lock = threading.Lock()

    def step(self, sid: str, status: str, detail: str = "") -> None:
        with self.lock:
            for s in self.steps:
                if s["id"] == sid:
                    if status == "running":
                        self._t[sid] = time.perf_counter()
                    elif sid in self._t:
                        s["seconds"] = round(time.perf_counter() - self._t[sid], 1)
                    s["status"], s["detail"] = status, detail[:240]

    def view(self) -> dict[str, Any]:
        with self.lock:
            return {"id": self.id, "status": self.status, "error": self.error, "steps": [dict(s) for s in self.steps],
                    "result": self.result}


def _call(c: ModelCall) -> dict[str, Any]:
    return c.model_dump(mode="json")


def _is_offline(call: ModelCall) -> bool:
    return call.provider == "mock"


def run(session: Session, video: bytes, models: Any, sample: bool) -> dict[str, Any]:
    t0 = time.perf_counter()
    st = models.settings
    live = st.provider == "meta" and st.has_key
    calls: list[dict[str, Any]] = []

    session.step("media", "running")
    media = Media(video)
    record = _sample() if media.sha == _sample()["sha256"] else None
    if not live and record is None:
        raise LectureError("offline, only the bundled sample lecture can be checked; uploads need the live models")
    session.step("media", "done", f"{media.duration:.1f} s, {media.width}×{media.height}, "
                                  f"{len(media.grey)} frames at {TRACK_FPS:g} a second for tracking")

    def listen():
        session.step("listen", "running")
        tr = models.speech.transcribe_turns(media.wav, KEYWORDS, source=media.sha)
        speakers = sorted({t.speaker for t in tr.turns})
        session.step("listen", "offline" if _is_offline(tr.call) else "done",
                     f"{len(tr.turns)} turns, {len(speakers)} speaker{'s' if len(speakers) != 1 else ''}")
        return tr

    def track_and_read():
        session.step("track", "running")
        tracks = models.segmentation.track_video(media.clip, TRACK_CONCEPTS, TRACK_FPS, source=media.sha)
        tracks = _rescale(tracks, media)
        session.step("track", "offline" if _is_offline(tracks.call) else "done",
                     f"{len(tracks.tracks)} drawn parts followed through {tracks.frames} frames")
        session.step("read", "running")
        spec, read_call, how = _read_board(models, media, tracks, record)
        session.step("read", "offline" if read_call.provider == "mock" else "done",
                     f"{len(spec['operations'])} operations on {spec['num_qubits']} qubits ({how})")
        return tracks, spec, read_call

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_listen, f_board = pool.submit(listen), pool.submit(track_and_read)
        transcript = f_listen.result()
        tracks, spec, read_call = f_board.result()
    calls += [_call(transcript.call), _call(tracks.call), _call(read_call)]

    if record is not None and read_call.provider == "mock":
        times = [{"op": i, "appears": next(e["appears"] for e in record["elements"] if e["id"] == el),
                  "how": "the sample's own record", "tracks": []} for i, el in enumerate(record["op_elements"])]
    else:
        times = op_times(spec, tracks, media)
    board = versions(times)
    turns = [{"index": i, **t.model_dump()} for i, t in enumerate(transcript.turns)]

    session.step("claims", "running")
    claims, claims_call = _claims(models, turns, spec, board, record)
    calls.append(_call(claims_call))
    session.step("claims", "offline" if claims_call.provider == "mock" else "done", f"{len(claims)} claims written out")

    session.step("check", "running")
    checked = []
    for c in claims:
        turn = turns[c["turn"]] if 0 <= c["turn"] < len(turns) else None
        if turn is None:
            continue
        v = _allowed_version(board, turn, c.get("board"))
        verdict = check_claim(spec, board[v]["ops"], c)
        checked.append({**c, "speaker": turn["speaker"], "time": turn["start"], "board": v,
                        "board_ops": [op_label(spec["operations"][i]) for i in board[v]["ops"]], **verdict})
    tally = {k: sum(c["verdict"] == k for c in checked) for k in ("true", "false", "unclear")}
    session.step("check", "done", f"{tally['true']} right, {tally['false']} wrong, {tally['unclear']} not checkable")

    def notes():
        session.step("notes", "running")
        n, call = _notes(models, turns, checked, spec)
        session.step("notes", "offline" if call.provider == "mock" else "done", n.get("title", ""))
        return n, call

    def figure():
        session.step("figure", "running")
        fig = _figure(models, spec, session)
        proof = fig.get("proof")
        session.step("figure", "offline" if fig["call"]["provider"] == "mock" else "done",
                     proof["detail"] if proof else fig["caption"])
        return fig

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_notes, f_fig = pool.submit(notes), pool.submit(figure)
        (note_data, notes_call), fig = f_notes.result(), f_fig.result()
    calls += [_call(notes_call), fig["call"], *fig.pop("calls")]

    wrong = [c for c in checked if c["verdict"] == "false"]
    who = sorted({c["speaker"] for c in wrong})
    headline = (f"{len(checked)} claims checked against the board as it was when each was made: {tally['true']} right, "
                f"{tally['false']} wrong" + (f" (speaker {', '.join(who)})" if who else "")
                + (f", {tally['unclear']} not checkable" if tally["unclear"] else "") + ".")
    return {
        "source": "sample" if record is not None else "upload", "sha256": media.sha,
        "title": record["title"] if record is not None else "Your lecture",
        "made_by": record["made_by"] if record is not None else "",
        "duration": round(media.duration, 2), "width": media.width, "height": media.height,
        "frame": "data:image/png;base64," + base64.b64encode(media.final).decode("ascii"),
        "turns": turns, "tracks": [t.model_dump() for t in tracks.tracks],
        "spec": spec, "ops": [{**t, "label": op_label(spec["operations"][t["op"]])} for t in times],
        "versions": board, "claims": checked, "tally": tally, "headline": headline,
        "notes": note_data, "figure": {k: v for k, v in fig.items() if k != "call"},
        "calls": calls, "offline": not live, "seconds": round(time.perf_counter() - t0, 1),
    }


def _rescale(tracks: TrackResult, media: Media) -> TrackResult:
    """SAM reports boxes in the pixels of the clip it was sent; the final frame has the same size, but be safe."""
    if not tracks.width or (tracks.width, tracks.height) == (media.width, media.height):
        return tracks
    sx, sy = media.width / tracks.width, media.height / tracks.height
    for t in tracks.tracks:
        t.bbox = (t.bbox[0] * sx, t.bbox[1] * sy, t.bbox[2] * sx, t.bbox[3] * sy)
    tracks.width, tracks.height = media.width, media.height
    return tracks


def _read_board(models: Any, media: Media, tracks: TrackResult, record: dict[str, Any] | None):
    """Muse Spark reads the last frame, given SAM's boxes of everything still on the board as segments."""
    from inkubit.spec.validation import parse_spec

    end = max((t.last_s for t in tracks.tracks), default=0.0)
    segs = SegmentationResult(width=media.width, height=media.height, concepts=tracks.concepts, call=tracks.call,
                              segments=[Segment(id=t.id, concept=t.concept, bbox=t.bbox, confidence=t.confidence)
                                        for t in tracks.tracks if t.last_s >= end - 1.0])
    try:
        draft = models.reasoning.draft_spec(media.final, "image/png", segs, "circuit")
        if draft.valid and draft.call.provider != "mock":
            parse_spec(draft.spec)
            return draft.spec, draft.call, "read by Muse Spark"
        problem = "; ".join(draft.issues[:2]) or "the reading was not a valid circuit"
    except Exception as err:  # noqa: BLE001 - fall back below, or report
        problem = str(err)[:200]
    if record is not None:
        return record["spec"], ModelCall(provider="mock", model="the sample's own script", role="read board",
                                         error=None if not models.settings.has_key else problem), "the sample's record"
    raise LectureError(f"the board could not be read into a circuit: {problem}")


def _board_text(spec: dict[str, Any], board: list[dict[str, Any]]) -> str:
    lines = []
    for v in board:
        ops = ", ".join(op_label(spec["operations"][i]) for i in v["ops"]) or "empty wires, every qubit at 0"
        lines.append(f"board {v['index']} (from {v['time']:.1f} s): {ops}")
    return "\n".join(lines)


def _claims(models: Any, turns: list[dict[str, Any]], spec: dict[str, Any], board: list[dict[str, Any]],
            record: dict[str, Any] | None) -> tuple[list[dict[str, Any]], ModelCall]:
    st = models.settings
    if st.provider == "meta" and st.has_key:
        user = (f"The board has {spec['num_qubits']} qubits. How it grew:\n{_board_text(spec, board)}\n\nTurns:\n"
                + "\n".join(f"turn {t['index']} ({t['start']:.1f}-{t['end']:.1f} s, speaker {t['speaker']}): {t['text']}"
                            for t in turns))
        try:
            data, call = models.reasoning.structured(CLAIMS_SYSTEM, user, CLAIMS_SCHEMA, "lecture_claims", effort="low",
                                                     max_tokens=6000)
            return [c for c in data.get("claims", []) if isinstance(c, dict)], call
        except Exception as err:  # noqa: BLE001
            if record is None:
                raise LectureError(f"the claims could not be written out: {str(err)[:200]}") from None
            error = str(err)[:200]
    else:
        error = None
    if record is None:
        raise LectureError("offline, only the bundled sample lecture can be checked")
    times = [t["start"] for t in turns]
    out = []
    for c in record["claims"]:
        rec_turn = record["turns"][c["turn"]]
        idx = min(range(len(times)), key=lambda i: abs(times[i] - rec_turn["start"]))  # same turn in this transcript
        appears = {e["id"]: e["appears"] for e in record["elements"]}
        drawn = [i for i, el in enumerate(record["op_elements"]) if appears[el] <= rec_turn["start"]]
        version = max((v["index"] for v in board if set(v["ops"]) == set(drawn)), default=0)
        out.append({"turn": idx, "quote": c["quote"], "kind": c["kind"], "board": version, "qubits": c["qubits"],
                    "outcome": c.get("outcome", ""), "value": c.get("value", -1), "outcomes": c.get("outcomes", []),
                    "state": c.get("state", "none")})
    return out, ModelCall(provider="mock", model="the sample's own script", role="lecture claims", error=error)


def _allowed_version(board: list[dict[str, Any]], turn: dict[str, Any], asked: Any) -> int:
    """The board version a claim is checked against: the model's pick if it was on the board during the turn (or
    appeared within GRACE_S after it), else the one on the board when the turn began."""
    at_start = max(v["index"] for v in board if v["time"] <= turn["start"])
    try:
        k = int(asked)
    except (TypeError, ValueError):
        return at_start
    if 0 <= k < len(board) and board[k]["time"] <= turn["end"] + GRACE_S and (
            k == len(board) - 1 or board[k + 1]["time"] > turn["start"]):
        return k
    return at_start


def _notes(models: Any, turns: list[dict[str, Any]], checked: list[dict[str, Any]],
           spec: dict[str, Any]) -> tuple[dict[str, Any], ModelCall]:
    st = models.settings
    facts = {"circuit": [op_label(o) for o in spec["operations"]], "qubits": spec["num_qubits"],
             "transcript": [{"speaker": t["speaker"], "text": t["text"]} for t in turns],
             "checks": [{"speaker": c["speaker"], "quote": c["quote"], "verdict": c["verdict"], "exact": c["detail"],
                         "board": c["board_ops"]} for c in checked]}
    if st.provider == "meta" and st.has_key:
        try:
            data, call = models.reasoning.structured(NOTES_SYSTEM, json.dumps(facts, ensure_ascii=False), NOTES_SCHEMA,
                                                     "lecture_notes", effort="medium", max_tokens=5000,
                                                     model=st.deep_model)
            return data, call
        except Exception as err:  # noqa: BLE001
            error = str(err)[:200]
    else:
        error = None
    wrong = [c for c in checked if c["verdict"] == "false"]
    data = {"title": "Notes from the checks", "summary": f"{len(checked) - len(wrong)} of {len(checked)} claims hold.",
            "sections": [{"heading": "What was built", "text": "; ".join(facts["circuit"]) + "."}],
            "corrections": [{"quote": c["quote"], "speaker": c["speaker"], "correction": c["detail"]} for c in wrong]}
    return data, ModelCall(provider="mock", model="written from the checks", role="lecture notes", error=error)


def _figure(models: Any, spec: dict[str, Any], session: Session | None = None) -> dict[str, Any]:
    """Muse Image draws the final board (no captions, so a reader cannot take the words for the drawing); the figure
    is then read back by SAM 3.1 and Muse Spark and proven equal to the circuit, or corrected, or replaced by the exact
    drawing (inkubit.figproof)."""
    from inkubit import figproof
    from inkubit.spec.validation import parse_spec

    parsed = parse_spec({**spec, "metadata": {**spec.get("metadata", {}), "title": spec.get("metadata", {}).get("title")
                                              or "The lecture's circuit"}})
    d = models.image.diagram(parsed, {"plain": True})
    fig: dict[str, Any] = {"image": f"data:{d.mime};base64,{d.image_b64}", "caption": d.caption, "call": _call(d.call),
                           "calls": []}
    if d.call.provider != "meta":
        return fig
    if session is not None:
        session.step("figure", "running", "drawn; reading it back to prove it shows this circuit")
    proof = figproof.prove(models, spec, d.image_b64, d.mime)
    fig["image"] = f"data:{proof['mime']};base64,{proof['image']}"
    fig["proof"] = {k: proof[k] for k in ("verdict", "detail", "read_ops", "attempts")}
    fig["calls"] = [_call(c) for c in proof["calls"]]
    fig["caption"] = {"proven": "Drawn by Muse Image, then read back by SAM 3.1 and Muse Spark and proven to show this circuit.",
                      "repaired": "Drawn and corrected by Muse Image, then read back and proven to show this circuit.",
                      }.get(proof["verdict"], "The exact Qiskit drawing, because Muse Image's figure could not be proven.")
    return fig


# ---------- sessions ----------

_sessions: dict[str, Session] = {}
_lock = threading.Lock()


def launch(video: bytes, models: Any, sample: bool) -> Session:
    s = Session("sample" if sample else "upload")
    with _lock:
        _sessions[s.id] = s
        while len(_sessions) > 8:
            _sessions.pop(next(iter(_sessions)))

    def go() -> None:
        try:
            s.result = run(s, video, models, sample)
            s.status = "done"
        except Exception as err:  # noqa: BLE001 - shown on the page
            s.status, s.error = "failed", str(err)[:400]
            for step in s.steps:
                if step["status"] == "running":
                    step["status"] = "failed"

    threading.Thread(target=go, name=f"lecture-{s.id}", daemon=True).start()
    return s


def get(key: str) -> Session | None:
    with _lock:
        return _sessions.get(key)
