"""Offline Segmentation, Reasoning and Image models.

Segmentation and spec drafting recognise the bundled sample sketches by file
hash (fixtures written by scripts/make_sketches.py). Any other image gets an
honest error asking for live mode, never an invented reading.
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from typing import Any

from qcanvas import EXAMPLES_DIR
from qcanvas.adapters.base import (
    DiagramResult,
    Explanation,
    ImageModel,
    ModelCall,
    ReasoningModel,
    Segment,
    SegmentationModel,
    SegmentationResult,
    SpecDraft,
)
from qcanvas.adapters.imaging import sha256
from qcanvas.explain.diagrams import circuit_png, network_png
from qcanvas.explain.templates import explain_circuit
from qcanvas.spec.models import CircuitSpec, NetworkSpec
from qcanvas.spec.validation import SpecError, parse_spec


class UnknownImageError(LookupError):
    """The offline adapters only know the bundled sample sketches."""


@lru_cache(maxsize=1)
def sample_fixtures() -> dict[str, dict[str, Any]]:
    """Fixtures for the bundled sketches, keyed by SHA-256 of the PNG."""
    out: dict[str, dict[str, Any]] = {}
    for path in sorted((EXAMPLES_DIR / "images").glob("*.json")):
        fx = json.loads(path.read_text(encoding="utf-8"))
        out[fx["sha256"]] = fx
    return out


def _fixture(image: bytes) -> dict[str, Any]:
    fx = sample_fixtures().get(sha256(image))
    if fx is None:
        raise UnknownImageError(
            "Offline (mock) mode only recognises the bundled sample sketches. To read your own photo, "
            "set QCANVAS_MODEL_PROVIDER=meta and add META_API_KEY to .env, or paste the spec as JSON.")
    return fx


class MockSegmentationModel(SegmentationModel):
    """Returns the recorded ground-truth boxes for a bundled sketch."""

    def segment(self, image: bytes, mime: str, concepts: list[str] | None = None) -> SegmentationResult:
        fx = _fixture(image)
        wanted = set(concepts or fx["concepts"])
        segs = [Segment(**s) for s in fx["segments"] if s["concept"] in wanted]
        return SegmentationResult(width=fx["width"], height=fx["height"], segments=segs,
                                  concepts=list(concepts or fx["concepts"]),
                                  call=ModelCall(provider="mock", model="sample-sketch fixtures", role="segment"))


class MockReasoningModel(ReasoningModel):
    """Recorded readings for bundled sketches and template explanations."""

    def choose_concepts(self, image: bytes, mime: str) -> tuple[str, list[str], ModelCall]:
        fx = _fixture(image)
        return fx["kind"], list(fx["concepts"]), ModelCall(provider="mock", model="sample-sketch fixtures",
                                                           role="choose concepts")

    def draft_spec(self, image: bytes, mime: str, segments: SegmentationResult, kind: str) -> SpecDraft:
        fx = _fixture(image)
        call = ModelCall(provider="mock", model="sample-sketch fixtures", role="read sketch")
        try:
            parse_spec(fx["spec"])
            return SpecDraft(spec=fx["spec"], valid=True, call=call, notes="Recorded reading of a bundled sketch.")
        except SpecError as err:
            return SpecDraft(spec=fx["spec"], valid=False, issues=[str(i) for i in err.issues], call=call)

    def explain(self, spec: CircuitSpec | NetworkSpec, result: dict[str, Any]) -> Explanation:
        if isinstance(spec, CircuitSpec):
            text = explain_circuit(spec, result)
        else:
            from qcanvas.network.explain import explain_network

            text = explain_network(spec, result)
        return Explanation(text=text, call=ModelCall(provider="mock", model="explanation template", role="explain"))


class MockImageModel(ImageModel):
    """Exact diagrams drawn locally (Qiskit drawer / matplotlib)."""

    def diagram(self, spec: CircuitSpec | NetworkSpec, result: dict[str, Any]) -> DiagramResult:
        if isinstance(spec, CircuitSpec):
            png, caption = circuit_png(spec), "Circuit drawn by Qiskit from the verified spec."
        else:
            png, caption = network_png(spec, result.get("after") or result.get("before")), \
                "Network drawn from the spec; the weakest link is highlighted."
        return DiagramResult(image_b64=base64.b64encode(png).decode("ascii"), mime="image/png", caption=caption,
                             call=ModelCall(provider="mock", model="local renderer", role="diagram"))
