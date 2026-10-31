"""Model adapter interfaces and the data they exchange.

Every model call in Q-Canvas goes through one of these four interfaces, each
with a ``meta`` (real Meta Model API) and a ``mock`` (deterministic, offline)
implementation. Results carry a :class:`ModelCall` so the UI can always say
which model produced what, and whether it was cached or a mock fallback.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field

from qcanvas.spec.models import CircuitSpec, NetworkSpec

CallProvider = Literal["meta", "mock", "mock-fallback"]


class ModelCall(BaseModel):
    """Provenance of one model result."""

    provider: CallProvider
    model: str
    role: str
    cached: bool = False
    latency_s: float = 0.0
    error: str | None = None  # set when a live call failed (and the mock stood in)


class Segment(BaseModel):
    """One SAM detection in source-image pixels."""

    id: str
    concept: str
    bbox: tuple[float, float, float, float]
    confidence: float = 1.0
    polygon: list[tuple[float, float]] | None = None


class SegmentationResult(BaseModel):
    """All segments found in one image."""

    width: int
    height: int
    segments: list[Segment]
    concepts: list[str]
    call: ModelCall


class SpecDraft(BaseModel):
    """A spec proposed from an image, before the user corrects it."""

    spec: dict[str, Any]
    valid: bool
    issues: list[str] = Field(default_factory=list)
    notes: str = ""
    call: ModelCall
    attempts: int = 1
    extra_segments: list[Segment] = Field(default_factory=list)  # boxes the reader reported itself


class CodeResult(BaseModel):
    """Code written for a spec."""

    code: str
    call: ModelCall
    notes: str = ""


class AttemptSummary(BaseModel):
    """What happened in an earlier attempt (given to the repairer)."""

    attempt: int
    outcome: str
    fix_summary: str = ""


class RepairRequest(BaseModel):
    """Everything the repairer needs to fix one failed attempt."""

    spec: CircuitSpec
    noise: str
    code: str
    error: str | None = None
    stderr_tail: str = ""
    verdict_reason: str | None = None
    diagnosis: str = ""
    diagnosis_category: str = ""
    history: list[AttemptSummary] = Field(default_factory=list)


class RepairResult(BaseModel):
    """A proposed fix."""

    code: str
    diagnosis: str
    fix_summary: str
    changed: bool
    call: ModelCall


LANGUAGES = ("English", "Hindi", "Spanish", "French", "German", "Portuguese", "Japanese", "Chinese (Simplified)",
             "Arabic", "Bengali", "Tamil", "Indonesian")
# Seen live: without this, Hindi came back transliterated into Latin letters.
SCRIPTS = {"Hindi": "Devanagari", "Japanese": "Japanese (kanji and kana)", "Chinese (Simplified)": "simplified Chinese",
           "Arabic": "Arabic", "Bengali": "Bengali", "Tamil": "Tamil"}


class Explanation(BaseModel):
    """Plain-language explanation of a result."""

    text: str
    call: ModelCall
    language: str = "English"
    note: str = ""


class Proposal(BaseModel):
    """A cheaper circuit a model proposes (operations, no measurements) and its one-line idea."""

    operations: list[dict[str, Any]]
    idea: str = ""
    call: ModelCall


class DiagramResult(BaseModel):
    """A rendered diagram (PNG/WebP bytes, base64)."""

    image_b64: str
    mime: str
    caption: str
    call: ModelCall


class Transcript(BaseModel):
    """Speech turned into text."""

    text: str
    duration_ms: int = 0
    call: ModelCall


class OddsGuess(BaseModel):
    """A model's own prediction of a circuit's outcome odds, with no simulator."""

    outcomes: dict[str, float]
    reasoning: str = ""
    call: ModelCall


class NotationRead(BaseModel):
    """Quantum notation transcribed from a photo."""

    kind: str
    text: str
    notes: str = ""
    call: ModelCall


class BugGuess(BaseModel):
    """A model's pick in the bug hunt."""

    index: int
    fix: str = ""
    reason: str = ""
    call: ModelCall


class SegmentationModel(ABC):
    """SAM 3.1: image -> segments."""

    @abstractmethod
    def segment(self, image: bytes, mime: str, concepts: list[str] | None = None) -> SegmentationResult: ...


class ReasoningModel(ABC):
    """Muse Spark: sketch -> spec draft, and results -> explanation."""

    @abstractmethod
    def draft_spec(self, image: bytes, mime: str, segments: SegmentationResult, kind: str) -> SpecDraft: ...

    @abstractmethod
    def choose_concepts(self, image: bytes, mime: str) -> tuple[str, list[str], ModelCall]:
        """Return (kind guess, noun phrases for SAM, call info)."""

    @abstractmethod
    def explain(self, spec: CircuitSpec | NetworkSpec, result: dict[str, Any],
                language: str = "English") -> Explanation: ...

    def spec_from_text(self, text: str) -> SpecDraft:
        """A spec from a plain-language description."""
        raise NotImplementedError

    def answer(self, question: str, context: dict[str, Any]) -> Explanation:
        """Answer a question about a design and its results, using only the given context."""
        raise NotImplementedError

    def optimize(self, facts: dict[str, Any]) -> Proposal:
        """Propose a cheaper circuit with the same measured odds (checked by exact simulation afterwards)."""
        raise NotImplementedError("circuit proposals need the live model")

    def hint(self, facts: dict[str, Any]) -> Explanation:
        """A nudge toward a challenge's goal that does not give the solution away."""
        raise NotImplementedError

    def find_bug(self, facts: dict[str, Any]) -> BugGuess:
        """Pick the one wrong operation in a bug-hunt round."""
        raise NotImplementedError("the bug hunt opponent needs the live model")

    def read_notation(self, image: bytes, mime: str) -> NotationRead:
        """Transcribe a photo of quantum notation (a ket, OpenQASM, Quil, code) into text, without solving it."""
        raise NotImplementedError("reading a photo of notation needs the live model")

    def tool_chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], model: str | None = None,
                  effort: str = "low") -> tuple[dict[str, Any], ModelCall]:
        """One assistant turn with tools: the full message (text or tool calls) and the call record.

        ``model`` overrides the reasoning model (Ask Q-Canvas deep mode uses Muse Wonder)."""
        raise NotImplementedError("the assistant needs the live model")

    def predict_odds(self, facts: dict[str, Any]) -> OddsGuess:
        """Answer like a chatbot: predict the outcome odds without running anything."""
        raise NotImplementedError("asking the AI alone needs the live model")

    def structured(self, system: str, user: str, schema: dict[str, Any], name: str, effort: str = "low",
                   max_tokens: int = 8000, model: str | None = None) -> tuple[dict[str, Any], ModelCall]:
        """One JSON-schema answer (mission plans, step repairs, mission reports) and the call record."""
        raise NotImplementedError("mission control's planner needs the live model")


class CodeModel(ABC):
    """Writes and repairs Qiskit code."""

    @abstractmethod
    def generate(self, spec: CircuitSpec, noise: str, shots: int, seed: int) -> CodeResult: ...

    @abstractmethod
    def repair(self, request: RepairRequest) -> RepairResult: ...


class SpeechModel(ABC):
    """Muse Voice Transcribe: a short recording -> text."""

    @abstractmethod
    def transcribe(self, wav: bytes, keywords: list[str] | None = None) -> Transcript: ...


class ImageModel(ABC):
    """Muse Image: final design -> clean annotated diagram."""

    @abstractmethod
    def diagram(self, spec: CircuitSpec | NetworkSpec, result: dict[str, Any]) -> DiagramResult: ...
