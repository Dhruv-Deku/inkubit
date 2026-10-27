"""Sketch understanding: photo -> segments -> spec draft -> overlay data."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from qcanvas.adapters.base import ModelCall, Segment
from qcanvas.adapters.imaging import normalise_upload, sha256
from qcanvas.adapters.registry import Models


class OverlayBox(BaseModel):
    """One box to draw on the photo, and what in the spec it became."""

    segment_id: str
    concept: str
    bbox: tuple[float, float, float, float]
    confidence: float
    linked_to: str | None = None  # e.g. "operations[1]" or "nodes[0]"
    label: str = ""


class SketchAnalysis(BaseModel):
    """Everything the correction screen needs."""

    image_sha256: str
    mime: str
    width: int
    height: int
    kind: str
    concepts: list[str]
    segments: list[Segment]
    spec: dict[str, Any]
    valid: bool
    issues: list[str] = Field(default_factory=list)
    notes: str = ""
    overlay: list[OverlayBox] = Field(default_factory=list)
    calls: list[ModelCall] = Field(default_factory=list)


def _link_overlay(spec: dict[str, Any], segments: list[Segment]) -> list[OverlayBox]:
    links: dict[str, tuple[str, str]] = {}
    if spec.get("kind") == "circuit":
        for i, op in enumerate(spec.get("operations", [])):
            sid = (op.get("source") or {}).get("segment_id")
            if sid:
                qs = ",".join(f"q{q}" for q in op.get("targets", []))
                ctrl = ",".join(f"q{q}" for q in op.get("controls", []))
                arrow = ctrl + "→" if ctrl else ""
                label = f"{op.get('gate')} {arrow}{qs}"
                links[sid] = (f"operations[{i}]", label)
    else:
        for i, node in enumerate(spec.get("nodes", [])):
            sid = (node.get("source") or {}).get("segment_id")
            if sid:
                links[sid] = (f"nodes[{i}]", node.get("label") or node.get("id", ""))
        for i, link in enumerate(spec.get("links", [])):
            sid = (link.get("source") or {}).get("segment_id")
            if sid:
                links[sid] = (f"links[{i}]", f"{link.get('length_km')} km {link.get('medium', '')}".strip())
    out = []
    for s in segments:
        linked, label = links.get(s.id, (None, s.concept))
        out.append(OverlayBox(segment_id=s.id, concept=s.concept, bbox=s.bbox, confidence=s.confidence,
                              linked_to=linked, label=label))
    return out


def analyze_image(raw: bytes, models: Models) -> tuple[SketchAnalysis, bytes]:
    """Run the sketch pipeline; returns the analysis and the normalised image bytes."""
    image, mime, width, height = normalise_upload(raw)
    kind, concepts, concept_call = models.reasoning.choose_concepts(image, mime)
    segmentation = models.segmentation.segment(image, mime, concepts)
    draft = models.reasoning.draft_spec(image, mime, segmentation, kind)
    analysis = SketchAnalysis(
        image_sha256=sha256(image), mime=mime, width=width, height=height, kind=kind, concepts=concepts,
        segments=segmentation.segments, spec=draft.spec, valid=draft.valid, issues=draft.issues,
        notes=draft.notes, overlay=_link_overlay(draft.spec, segmentation.segments),
        calls=[concept_call, segmentation.call, draft.call],
    )
    return analysis, image
