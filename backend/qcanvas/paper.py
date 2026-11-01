"""Reproduce a whole paper: a PDF (or an arXiv id) in, every experiment with a circuit and stated odds re-run exactly.

1. Find. Muse Wonder (its million-token context reads a PDF's text and an image of each page) lists up to eight
   experiments on different circuits of up to 10 qubits whose outcome probabilities the paper states, with their pages.
2. Transcribe. For each, the one to three pages are cut out (pypdf) and Muse Spark transcribes that experiment alone:
   the circuit as OpenQASM 2, every stated probability, the shot count, the hardware and the bit order, with a quote.
   Both models are told to transcribe, never to compute or correct; the focused second pass is what makes a long
   paper work (one pass over a hundred pages listed repeat runs and dropped numbers).
3. Re-run. Each circuit goes through the Rosetta's exact OpenQASM parser (a circuit that does not parse is reported,
   not guessed), then exact simulation, ideal and with the realistic preset.
4. Judge. The figure checker's rules (qcanvas.reproduce.judge): a claim is within reach inside its shot-noise error
   bar of the ideal value, or, for hardware data, between our realistic-noise value and the ideal one; the bit order
   is inferred when the paper does not state it.

The verdict counts experiments and claims; a paper whose circuits are only sketched in words is reported as such.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from typing import Any

import httpx
from pydantic import BaseModel

from qcanvas.reproduce import Claim, judge, spec_from_qasm

MAX_PDF = 20_000_000
ARXIV = re.compile(r"^(?:arxiv:)?\s*(\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)$", re.I)

LIST_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["title", "experiments", "notes"], "properties": {
    "title": {"type": "string"},
    "experiments": {"type": "array", "maxItems": 8, "items": {
        "type": "object", "additionalProperties": False, "required": ["name", "pages"],
        "properties": {"name": {"type": "string", "description": "Short name, e.g. 'Grover search, marked state 11, ibmqx4'."},
                       "pages": {"type": "array", "items": {"type": "integer"}, "maxItems": 3,
                                 "description": "The pages with its circuit and its outcome probabilities."}}}},
    "notes": {"type": "string"}}}
LIST_SYSTEM = (
    "You read quantum computing papers. List up to 8 experiments on different circuits (different algorithms or inputs; "
    "never repeat runs of the same circuit) whose circuit has at most 10 qubits and is given as a figure, code or a "
    "complete description, and whose measured or simulated outcome probabilities the paper states in a table, histogram, "
    "figure or the text. For each give a short name and the one to three pages that hold its circuit and its numbers.")
EXP_SCHEMA = {"type": "object", "additionalProperties": False,
              "required": ["name", "page", "quote", "circuit_qasm", "claims", "shots", "hardware", "bit_order"],
              "properties": {
            "name": {"type": "string", "description": "Short name, e.g. 'Bernstein-Vazirani, secret 101'."},
            "page": {"type": "integer"},
            "quote": {"type": "string", "description": "The caption or sentence that states the numbers, verbatim."},
            "circuit_qasm": {"type": "string", "description": "The circuit as OpenQASM 2.0 (include \"qelib1.inc\"; qreg q[n]; "
                                                              "creg c[n]; gates; measure), or empty if the paper does not "
                                                              "specify it completely."},
            "claims": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["outcome", "probability", "kind"],
                "properties": {"outcome": {"type": "string"}, "probability": {"type": "number"},
                               "kind": {"type": "string", "enum": ["measured", "ideal", "simulated"]}}}},
            "shots": {"type": "integer", "description": "Shots if stated, else 0."},
            "hardware": {"type": "string"},
            "bit_order": {"type": "string", "enum": ["q0_rightmost", "q0_leftmost", "unknown"]}}}
EXP_SYSTEM = (
    "You transcribe one experiment from pages of a quantum computing paper so it can be re-run exactly. When a figure "
    "shows several input settings, pick one setting and transcribe that circuit and its outcomes. Copy the circuit gate by gate as "
    "OpenQASM 2.0 with the paper's qubit numbering, using only qelib1.inc gates (x y z h s sdg t tdg rx ry rz u1 u2 u3 "
    "cx cy cz ch ccx swap cswap crz cu1 cu3, measure); write a doubly controlled Z as h, ccx, h on the target; never "
    "declare opaque or custom gates; leave the circuit empty if the paper does not specify it completely. Copy every "
    "outcome probability shown (convert percent; read histogram bars as carefully as you can, bitstrings exactly as "
    "printed) and quote the caption or sentence with its page. Transcribe only: never compute, simulate or correct.")


class Experiment(BaseModel):
    name: str
    page: int
    quote: str
    verdict: str  # reproduced | partly reproduced | not reproduced | no circuit | circuit did not parse | no claims
    circuit_qasm: str
    spec: dict[str, Any] | None = None
    claims: list[dict[str, Any]] = []
    bit_order: str = "unknown"
    bit_order_inferred: bool = False
    shots: int = 0
    hardware: str = ""
    tvd_to_ideal: float | None = None
    note: str = ""


class PaperResult(BaseModel):
    source: str
    title: str
    experiments: list[Experiment]
    reproduced: int
    checked: int  # experiments with a circuit and claims
    claims_ok: int
    claims_total: int
    headline: str
    notes: str
    calls: list[dict[str, Any]]
    seconds: float


def fetch_arxiv(ref: str) -> tuple[bytes, str]:
    m = ARXIV.match(ref.strip())
    if not m:
        raise ValueError("give an arXiv id such as 1703.10535, or upload the PDF")
    pid = m.group(1)
    r = httpx.get(f"https://arxiv.org/pdf/{pid}", follow_redirects=True, timeout=60.0,
                  headers={"User-Agent": "Q-Canvas paper reproducibility checker"})
    r.raise_for_status()
    if not r.content.startswith(b"%PDF") or len(r.content) > MAX_PDF:
        raise ValueError("arXiv did not return a PDF of at most 20 MB for that id")
    return r.content, f"arXiv:{pid}"


def check_experiment(e: dict[str, Any]) -> Experiment:
    base = Experiment(name=str(e.get("name", ""))[:120], page=int(e.get("page") or 0), quote=str(e.get("quote", ""))[:500],
                      verdict="no circuit", circuit_qasm=str(e.get("circuit_qasm", "")), shots=int(e.get("shots") or 0),
                      hardware=str(e.get("hardware", ""))[:80])
    claims = [Claim(outcome=str(c.get("outcome", "")), probability=float(c.get("probability", 0)), kind=str(c.get("kind", "measured")))
              for c in e.get("claims") or [] if re.fullmatch(r"[01 ]+", str(c.get("outcome", "")).strip() or "x")]
    if not base.circuit_qasm.strip():
        return base.model_copy(update={"note": "the paper does not specify this circuit completely"})
    try:
        spec = spec_from_qasm(base.circuit_qasm)
    except Exception as err:  # noqa: BLE001 - reported, never guessed
        return base.model_copy(update={"verdict": "circuit did not parse", "note": str(err)[:200]})
    if spec.get("num_qubits", 0) > 10:
        return base.model_copy(update={"verdict": "circuit did not parse", "spec": spec, "note": "more than 10 qubits"})
    if not claims:
        return base.model_copy(update={"verdict": "no claims", "spec": spec})
    rows, order, inferred, tvd = judge(spec, claims, base.shots, str(e.get("bit_order", "unknown")))
    ok = sum(r.ok for r in rows)
    verdict = "reproduced" if ok == len(rows) else "partly reproduced" if 2 * ok >= len(rows) else "not reproduced"
    return base.model_copy(update={"verdict": verdict, "spec": spec, "claims": [r.model_dump() for r in rows],
                                   "bit_order": order, "bit_order_inferred": inferred, "tvd_to_ideal": tvd})


def pages_pdf(pdf: bytes, pages: list[int]) -> bytes:
    """A small PDF of the given 1-based pages (and the next one, where a figure often continues)."""
    import io

    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(pdf))
    keep = sorted({p for q in pages for p in (q, q + 1) if 1 <= p <= len(reader.pages)})[:4] or [1]
    writer = PdfWriter()
    for p in keep:
        writer.add_page(reader.pages[p - 1])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _transcribe(pdf: bytes, item: dict[str, Any], reasoning: Any) -> tuple[dict[str, Any] | None, Any]:
    pages = [int(p) for p in item.get("pages") or [] if isinstance(p, int)] or [1]
    sub = pages_pdf(pdf, pages)
    user = f"Experiment: {item.get('name', '')}. These are pages {', '.join(map(str, pages))} of the paper (and the next page). Transcribe it."
    for attempt in range(2):  # one retry if the answer is not valid JSON
        try:
            data, call = reasoning.structured(EXP_SYSTEM, user + (" (second attempt)" if attempt else ""), EXP_SCHEMA,
                                              "paper_experiment", effort="medium", max_tokens=16000 if attempt == 0 else 32000,
                                              document=(sub, "pages.pdf"))
            return data | {"page": data.get("page") or pages[0]}, call
        except Exception:  # noqa: BLE001
            if attempt:
                return None, None
    return None, None


def reproduce_paper(pdf: bytes, source: str, reasoning: Any, model: str) -> PaperResult:
    from concurrent.futures import ThreadPoolExecutor

    t0 = time.perf_counter()
    listing: dict[str, Any] = {}
    calls = []
    for attempt, who in enumerate((model, model, None)):  # Muse Wonder twice, then Muse Spark
        try:
            listing, call = reasoning.structured(LIST_SYSTEM, f"Paper: {source}. List its experiments." + (f" (attempt {attempt + 1})" if attempt else ""),
                                                 LIST_SCHEMA, "paper_experiments", effort="medium", max_tokens=32000,
                                                 model=who, document=(pdf, "paper.pdf"))
            calls.append(call)
            break
        except Exception:  # noqa: BLE001 - a long paper sometimes yields a truncated answer; try again
            if attempt == 2:
                raise
    with ThreadPoolExecutor(max_workers=4) as pool:
        got = list(pool.map(lambda it: _transcribe(pdf, it, reasoning), (listing.get("experiments") or [])[:8]))
    calls += [c for _, c in got if c is not None]
    data = {"title": listing.get("title", ""), "notes": listing.get("notes", ""), "experiments": [d for d, _ in got if d]}
    seen: set[str] = set()
    unique = []
    for e in data.get("experiments") or []:
        qasm = re.sub(r"\s+", "", str(e.get("circuit_qasm", "")))
        key = qasm or str(e.get("name", ""))  # repeat runs of one circuit count once
        if key not in seen:  # the same experiment listed twice counts once
            seen.add(key)
            unique.append(e)
    exps = [check_experiment(e) for e in unique[:8]]
    checked = [e for e in exps if e.claims]
    reproduced = sum(e.verdict == "reproduced" for e in checked)
    claims_ok = sum(c["ok"] for e in checked for c in e.claims)
    claims_total = sum(len(e.claims) for e in checked)
    if checked:
        headline = (f"{reproduced} of {len(checked)} experiments reproduced exactly within their error bars; "
                    f"{claims_ok} of {claims_total} stated probabilities check out.")
    elif exps:
        headline = "The paper's experiments could be listed, but none gave both a complete circuit and stated odds."
    else:
        headline = "No experiment with a small circuit and stated outcome odds was found in this paper."
    return PaperResult(source=source, title=str(data.get("title", ""))[:200], experiments=exps, reproduced=reproduced,
                       checked=len(checked), claims_ok=claims_ok, claims_total=claims_total, headline=headline,
                       notes=str(data.get("notes", ""))[:400], calls=[c.model_dump(mode="json") for c in calls],
                       seconds=round(time.perf_counter() - t0, 1))


class Session:
    def __init__(self, source: str):
        self.id = uuid.uuid4().hex[:12]
        self.source = source
        self.status = "running"
        self.error: str | None = None
        self.result: dict[str, Any] | None = None


def launch(s: Session, pdf: bytes | None, ref: str, models: Any) -> None:
    st = models.settings
    if not (st.provider == "meta" and st.has_key):
        raise ValueError("reading a whole paper needs the live Muse Wonder; the recorded examples are shown instead")

    def go() -> None:
        try:
            data, source = (pdf, s.source) if pdf else fetch_arxiv(ref)
            s.source = source
            s.result = reproduce_paper(data, source, models.reasoning, st.deep_model).model_dump(mode="json")
            s.status = "done"
        except Exception as err:  # noqa: BLE001 - shown on the page
            s.status, s.error = "failed", str(err)[:400]

    threading.Thread(target=go, name=f"paper-{s.id}", daemon=True).start()


_sessions: dict[str, Session] = {}
_lock = threading.Lock()


def add(s: Session) -> None:
    with _lock:
        _sessions[s.id] = s
        while len(_sessions) > 10:
            _sessions.pop(next(iter(_sessions)))


def get(key: str) -> Session | None:
    with _lock:
        return _sessions.get(key)
