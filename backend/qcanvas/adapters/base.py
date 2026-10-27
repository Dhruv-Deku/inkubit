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


class Explanation(BaseModel):
    """Plain-language explanation of a result."""

    text: str
    call: ModelCall


class DiagramResult(BaseModel):
    """A rendered diagram (PNG/WebP bytes, base64)."""

    image_b64: str
    mime: str
    caption: str
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
    def explain(self, spec: CircuitSpec | NetworkSpec, result: dict[str, Any]) -> Explanation: ...


class CodeModel(ABC):
    """Writes and repairs Qiskit code."""

    @abstractmethod
    def generate(self, spec: CircuitSpec, noise: str, shots: int, seed: int) -> CodeResult: ...

    @abstractmethod
    def repair(self, request: RepairRequest) -> RepairResult: ...


class ImageModel(ABC):
    """Muse Image: final design -> clean annotated diagram."""

    @abstractmethod
    def diagram(self, spec: CircuitSpec | NetworkSpec, result: dict[str, Any]) -> DiagramResult: ...
