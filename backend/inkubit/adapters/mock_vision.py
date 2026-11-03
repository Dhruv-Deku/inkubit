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

from inkubit import EXAMPLES_DIR
from inkubit.adapters.base import (
    DiagramResult,
    Explanation,
    ImageModel,
    ModelCall,
    ReasoningModel,
    Segment,
    SegmentationModel,
    SegmentationResult,
    SpecDraft,
    Track,
    TrackResult,
)
from inkubit.adapters.imaging import sha256
from inkubit.explain.diagrams import circuit_png, network_png
from inkubit.explain.templates import explain_circuit
from inkubit.spec.models import CircuitSpec, NetworkSpec
from inkubit.spec.validation import SpecError, parse_spec


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
            "set INKUBIT_MODEL_PROVIDER=meta and add META_API_KEY to .env, or paste the spec as JSON.")
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

    def track_video(self, video: bytes, concepts: list[str], fps: float, source: str = "") -> TrackResult:
        """Offline, only the bundled sample lecture can be tracked: its script recorded when each part was drawn."""
        from inkubit.lecture import sample_record

        rec = sample_record(source)
        tracks = [Track(id=f"{e['id']}{k}", concept=seg["concept"], first_s=e["appears"], last_s=rec["duration"],
                        bbox=tuple(seg["bbox"]))
                  for e in rec["elements"] for k, seg in enumerate(e["segments"])]
        return TrackResult(width=rec["width"], height=rec["height"], frames=int(rec["duration"] * fps), fps=fps,
                           tracks=tracks, concepts=concepts,
                           call=ModelCall(provider="mock", model="the sample's own script", role="track"))


class MockReasoningModel(ReasoningModel):
    """Recorded readings for bundled sketches and template explanations."""

    def choose_concepts(self, image: bytes, mime: str) -> tuple[str, list[str], ModelCall]:
        fx = _fixture(image)
        return fx["kind"], list(fx["concepts"]), ModelCall(provider="mock", model="sample-sketch fixtures",
                                                           role="choose concepts")

    def draft_spec(self, image: bytes, mime: str, segments: SegmentationResult, kind: str,
                   context: str = "") -> SpecDraft:
        fx = _fixture(image)
        call = ModelCall(provider="mock", model="sample-sketch fixtures", role="read sketch")
        try:
            parse_spec(fx["spec"])
            return SpecDraft(spec=fx["spec"], valid=True, call=call, notes="Recorded reading of a bundled sketch.")
        except SpecError as err:
            return SpecDraft(spec=fx["spec"], valid=False, issues=[str(i) for i in err.issues], call=call)

    def explain(self, spec: CircuitSpec | NetworkSpec, result: dict[str, Any],
                language: str = "English") -> Explanation:
        if isinstance(spec, CircuitSpec):
            text = explain_circuit(spec, result)
        else:
            from inkubit.network.explain import explain_network

            text = explain_network(spec, result)
        note = "" if language == "English" else f"Offline explanations are in English only; Muse Spark writes them in {language}."
        return Explanation(text=text, call=ModelCall(provider="mock", model="explanation template", role="explain"),
                           note=note)


    def answer(self, question: str, context: dict[str, Any]) -> Explanation:
        from inkubit.ask import offline_answer

        return Explanation(text=offline_answer(question, context),
                           call=ModelCall(provider="mock", model="offline answer rules", role="answer"))

    def hint(self, facts: dict[str, Any]) -> Explanation:
        return Explanation(text=facts["authored_hint"],
                           call=ModelCall(provider="mock", model="puzzle author's hints", role="hint"))

    def spec_from_text(self, text: str) -> SpecDraft:
        from inkubit.textspec import parse_description

        spec, how = parse_description(text)
        call = ModelCall(provider="mock", model="offline text parser", role="read description")
        try:
            parse_spec(spec)
            return SpecDraft(spec=spec, valid=True, call=call, notes=f"Read as {how}.")
        except SpecError as err:
            return SpecDraft(spec=spec, valid=False, issues=[str(i) for i in err.issues], call=call,
                             notes=f"Read as {how}.")


class MockImageModel(ImageModel):
    """Exact diagrams drawn locally (Qiskit drawer / matplotlib)."""

    def diagram(self, spec: CircuitSpec | NetworkSpec, result: dict[str, Any]) -> DiagramResult:
        if isinstance(spec, CircuitSpec):
            png, caption = circuit_png(spec), "Circuit drawn by Qiskit from the verified spec."
        else:
            final = NetworkSpec.model_validate(result["spec_after"]) if result.get("spec_after") else spec
            png = network_png(final, result.get("after") or result.get("before"))
            caption = ("Final network after the agent's fixes; " if result.get("spec_after") else "Network as drawn; ") \
                + "the weakest remaining link is highlighted."
        return DiagramResult(image_b64=base64.b64encode(png).decode("ascii"), mime="image/png", caption=caption,
                             call=ModelCall(provider="mock", model="local renderer", role="diagram"))
