"""Live adapters on Meta Model API: SAM 3.1, Muse Spark (reading, explaining), Muse Image.

Request shapes come from docs/meta-api (see SOURCES.md):
- SAM 3.1: POST /v1/responses, ``input_text`` noun phrase + ``input_image`` data URL,
  ``metadata.include_confidence = "true"``, streamed; output parsed by ``sam_parse``.
- Muse Spark: POST /v1/chat/completions with ``image_url`` objects and
  ``response_format`` json_schema.
- Muse Image: POST /v1/images/generations with ``response_format = "b64_json"``.
"""

from __future__ import annotations

import base64
import io
import json
import time
from typing import Any

from PIL import Image

from inkubit.adapters.base import (
    BugGuess,
    OddsGuess,
    DiagramResult,
    Explanation,
    ImageModel,
    ModelCall,
    NotationRead,
    Proposal,
    ReasoningModel,
    SCRIPTS,
    Segment,
    SegmentationModel,
    SegmentationResult,
    SpecDraft,
    Track,
    TrackResult,
)
from inkubit.adapters.config import Settings
from inkubit.adapters.imaging import annotate, data_url
from inkubit.adapters.meta_client import MetaAPIError, MetaClient
from inkubit.adapters.prompts import (
    ASK_SYSTEM,
    BUGHUNT_SYSTEM,
    ODDS_SYSTEM,
    CONCEPTS_SYSTEM,
    DRAFT_SYSTEM,
    EXPLAIN_SYSTEM,
    HINT_SYSTEM,
    NOTATION_SYSTEM,
    OPTIMIZE_SYSTEM,
    TEXT_SYSTEM,
)
from inkubit.adapters.sam_parse import parse_sam_output
from inkubit.sim.noise import get_preset
from inkubit.spec.draft import BUG_SCHEMA, CONCEPTS_SCHEMA, NOTATION_SCHEMA, ODDS_SCHEMA, REWRITE_SCHEMA, draft_schema, draft_to_spec
from inkubit.spec.models import CircuitSpec, NetworkSpec
from inkubit.spec.validation import SpecError, parse_spec

MAX_CONCEPTS = 4
MAX_SEGMENTS = 60


def _image_part(data: bytes, mime: str) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": data_url(data, mime)}}


class MetaSegmentationModel(SegmentationModel):
    """SAM 3.1 concept segmentation, one Responses call per noun phrase."""

    def __init__(self, settings: Settings, client: MetaClient):
        self.model = settings.segment_model
        self.client = client

    def segment(self, image: bytes, mime: str, concepts: list[str] | None = None) -> SegmentationResult:
        concepts = [c.strip() for c in (concepts or ["box", "circle"]) if c.strip()][:MAX_CONCEPTS]
        width, height = Image.open(io.BytesIO(image)).size
        url = data_url(image, mime)
        segments: list[Segment] = []
        cached_all = True
        start = time.perf_counter()
        for concept in concepts:
            payload = {
                "model": self.model,
                "input": [{"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": concept},
                    {"type": "input_image", "image_url": url},
                ]}],
                "metadata": {"include_confidence": "true"},
            }
            text, cached = self.client.post_stream_text("/responses", payload)
            cached_all = cached_all and cached
            for box in parse_sam_output(text):
                if box.frame != 0 or len(segments) >= MAX_SEGMENTS:
                    continue
                sx, sy = width / max(box.width, 1), height / max(box.height, 1)
                segments.append(Segment(
                    id=f"s{len(segments)}", concept=concept,
                    bbox=(box.x1 * sx, box.y1 * sy, box.x2 * sx, box.y2 * sy),
                    confidence=box.confidence if box.confidence is not None else 1.0,
                ))
        call = ModelCall(provider="meta", model=self.model, role="segment", cached=cached_all,
                         latency_s=time.perf_counter() - start)
        return SegmentationResult(width=width, height=height, segments=segments, concepts=concepts, call=call)

    def track_video(self, video: bytes, concepts: list[str], fps: float, source: str = "") -> TrackResult:
        """One request per concept with the clip as an ``input_video`` data URL (docs/meta-api/sam_segmenting.md):
        SAM 3.1 answers one line per frame and keeps each object's id across frames, so an object's first frame is
        when it appeared."""
        url = "data:video/mp4;base64," + base64.b64encode(video).decode("ascii")
        tracks: list[Track] = []
        width = height = frames = 0
        cached_all, start = True, time.perf_counter()
        for concept in concepts[:MAX_CONCEPTS]:
            payload = {"model": self.model, "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": concept}, {"type": "input_video", "video_url": url}]}],
                "metadata": {"include_confidence": "true"}}
            text, cached = self.client.post_stream_text("/responses", payload)
            cached_all = cached_all and cached
            seen: dict[int, list[Any]] = {}
            for box in parse_sam_output(text):
                seen.setdefault(box.object_id, []).append(box)
                width, height, frames = box.width, box.height, max(frames, box.frame + 1)
            for oid, boxes in sorted(seen.items()):
                last = boxes[-1]
                tracks.append(Track(id=f"{concept[:3]}{oid}", concept=concept, first_s=round(boxes[0].frame / fps, 2),
                                    last_s=round(last.frame / fps, 2), bbox=(last.x1, last.y1, last.x2, last.y2),
                                    confidence=last.confidence if last.confidence is not None else 1.0))
        call = ModelCall(provider="meta", model=self.model, role="track", cached=cached_all,
                         latency_s=time.perf_counter() - start)
        return TrackResult(width=width, height=height, frames=frames, fps=fps, tracks=tracks, concepts=concepts,
                           call=call)


class MetaReasoningModel(ReasoningModel):
    """Muse Spark reads sketches into specs and explains results."""

    def __init__(self, settings: Settings, client: MetaClient):
        self.model = settings.reasoning_model
        self.client = client

    def _json(self, messages: list[dict[str, Any]], schema: dict[str, Any], name: str,
              effort: str, max_tokens: int = 12000) -> tuple[dict[str, Any], bool, str]:
        content, cached = self.client.chat(self.model, messages, schema=schema, schema_name=name,
                                           reasoning_effort=effort, max_tokens=max_tokens)
        try:
            return json.loads(content), cached, content
        except json.JSONDecodeError:
            raise MetaAPIError(f"{self.model} returned text that is not JSON") from None

    def choose_concepts(self, image: bytes, mime: str) -> tuple[str, list[str], ModelCall]:
        start = time.perf_counter()
        messages = [
            {"role": "system", "content": CONCEPTS_SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": (
                    "Is this a quantum circuit or a quantum network? List 1 to 4 short noun phrases for the "
                    "drawn parts a segmentation model should find. Typical for circuits: 'gate box', 'dot', "
                    "'circle', 'meter'. Typical for networks: 'satellite', 'antenna dish', 'tower', "
                    "'dashed line'. Use phrases for what is actually drawn.")},
                _image_part(image, mime),
            ]},
        ]
        data, cached, _ = self._json(messages, CONCEPTS_SCHEMA, "diagram_concepts", "low")
        kind = data.get("kind") if data.get("kind") in ("circuit", "network") else "circuit"
        concepts = [str(c)[:40] for c in data.get("concepts", []) if str(c).strip()][:MAX_CONCEPTS]
        call = ModelCall(provider="meta", model=self.model, role="choose concepts", cached=cached,
                         latency_s=time.perf_counter() - start)
        return kind, concepts or ["box", "circle"], call

    def draft_spec(self, image: bytes, mime: str, segments: SegmentationResult, kind: str,
                   context: str = "") -> SpecDraft:
        start = time.perf_counter()
        seg_dicts = [s.model_dump() for s in segments.segments]
        listing = "\n".join(
            f"- {s.id}: '{s.concept}' at x1={s.bbox[0]:.0f}, y1={s.bbox[1]:.0f}, x2={s.bbox[2]:.0f}, "
            f"y2={s.bbox[3]:.0f} (confidence {s.confidence:.2f})" for s in segments.segments) or "- none found"
        marked = annotate(image, [(s.id, s.bbox) for s in segments.segments])
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": DRAFT_SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": (
                    f"This is a hand-drawn quantum {kind}. The image is {segments.width}x{segments.height} pixels. "
                    f"Segments found by SAM 3.1 (pixel boxes):\n{listing}\n\n"
                    "The first image is the photo; the second shows the same segments as numbered red boxes. "
                    "Fill the JSON for the drawing. Use segment ids exactly as listed (empty string if none)."
                    + (f" {context}" if context else ""))},
                _image_part(image, mime),
                _image_part(marked, "image/jpeg"),
            ]},
        ]
        spec, data, cached, attempts, issues = self._draft_validated(
            messages, kind, seg_dicts, (segments.width, segments.height), "drawing")
        call = ModelCall(provider="meta", model=self.model, role="read sketch", cached=cached,
                         latency_s=time.perf_counter() - start)
        extra = _grid_segments(spec, self.model)
        return SpecDraft(spec=spec, valid=not issues, issues=issues, notes=str(data.get("notes", "")),
                         call=call, attempts=attempts, extra_segments=extra)

    def _draft_validated(self, messages: list[dict[str, Any]], kind: str, seg_dicts: list[dict[str, Any]],
                         size: tuple[int, int] | None, what: str):
        """Structured draft, validated; one re-prompt with the readable issues if it fails."""
        schema = draft_schema(kind, text=what == "description")
        data, cached, raw = self._json(messages, schema, f"{kind}_draft", "medium")
        attempts = 1
        spec = draft_to_spec(kind, data, seg_dicts, size)
        issues: list[str] = []
        try:
            parse_spec(spec)
        except SpecError as err:
            issues = [str(i) for i in err.issues]
            attempts = 2
            messages = [*messages,
                        {"role": "assistant", "content": raw},
                        {"role": "user", "content": "That JSON fails validation:\n- " + "\n- ".join(issues)
                                                    + f"\nReturn corrected JSON for the same {what}."}]
            data, cached2, raw = self._json(messages, schema, f"{kind}_draft", "medium")
            cached = cached and cached2
            spec = draft_to_spec(kind, data, seg_dicts, size)
            try:
                parse_spec(spec)
                issues = []
            except SpecError as err2:
                issues = [str(i) for i in err2.issues]
        return spec, data, cached, attempts, issues

    def spec_from_text(self, text: str) -> SpecDraft:
        from inkubit.textspec import looks_like_network

        start = time.perf_counter()
        kind = "network" if looks_like_network(text) else "circuit"
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": TEXT_SYSTEM},
            {"role": "user", "content": f"Kind: quantum {kind}.\nDescription: {text.strip()[:2000]}\n\n"
                                        "Fill the JSON for this description."},
        ]
        spec, data, cached, attempts, issues = self._draft_validated(messages, kind, [], None, "description")
        spec.setdefault("metadata", {})["origin"] = "text"
        call = ModelCall(provider="meta", model=self.model, role="read description", cached=cached,
                         latency_s=time.perf_counter() - start)
        return SpecDraft(spec=spec, valid=not issues, issues=issues, notes=str(data.get("notes", "")),
                         call=call, attempts=attempts)

    def answer(self, question: str, context: dict[str, Any]) -> Explanation:
        start = time.perf_counter()
        facts = dict(context)
        for key in ("ideal", "measured", "expected_with_noise"):
            if isinstance(facts.get(key), dict):
                facts[key] = _rounded(facts[key])
        content, cached = self.client.chat(self.model, [
            {"role": "system", "content": ASK_SYSTEM},
            {"role": "user", "content": f"Facts about this run:\n{json.dumps(facts, indent=1, default=str)}"
                                        f"\n\nQuestion: {question.strip()[:600]}"},
        ], reasoning_effort="low", max_tokens=4000)
        if not content.strip():
            raise MetaAPIError("empty answer")
        return Explanation(text=content.strip(), call=ModelCall(provider="meta", model=self.model, role="answer",
                                                                cached=cached, latency_s=time.perf_counter() - start))

    def optimize(self, facts: dict[str, Any]) -> Proposal:
        start = time.perf_counter()
        messages = [
            {"role": "system", "content": OPTIMIZE_SYSTEM},
            {"role": "user", "content": f"Circuit and cost:\n{json.dumps(facts, indent=1)}\n\n"
                                        "Return a cheaper circuit with the same measured outcome odds."},
        ]
        data, cached, _ = self._json(messages, REWRITE_SCHEMA, "circuit_rewrite", "medium")
        ops = data.get("operations")
        if not isinstance(ops, list):
            raise MetaAPIError(f"{self.model} returned no operations list")
        return Proposal(operations=[o for o in ops if isinstance(o, dict)], idea=str(data.get("idea", "")),
                        call=ModelCall(provider="meta", model=self.model, role="optimize", cached=cached,
                                       latency_s=time.perf_counter() - start))

    def tool_chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], model: str | None = None,
                  effort: str = "low") -> tuple[dict[str, Any], ModelCall]:
        start = time.perf_counter()
        model = model or self.model
        msg, cached = self.client.chat_message(model, messages, tools, reasoning_effort=effort,
                                               max_tokens=6000 if effort == "low" else 16000)
        return msg, ModelCall(provider="meta", model=model, role="assistant", cached=cached,
                              latency_s=time.perf_counter() - start)

    def structured(self, system: str, user: str, schema: dict[str, Any], name: str, effort: str = "low",
                   max_tokens: int = 8000, model: str | None = None, image: bytes | None = None,
                   mime: str = "image/png", document: tuple[bytes, str] | None = None) -> tuple[dict[str, Any], ModelCall]:
        start = time.perf_counter()
        model = model or self.model
        body: Any = user if image is None else [{"type": "text", "text": user}, _image_part(image, mime)]
        if document is not None:  # a PDF inline: the API converts it to text plus an image of each page
            data_url = "data:application/pdf;base64," + base64.b64encode(document[0]).decode()
            body = [{"type": "text", "text": user}, {"type": "file", "file": {"filename": document[1], "file_data": data_url}}]
        content, cached = self.client.chat(model, [{"role": "system", "content": system},
                                                   {"role": "user", "content": body}],
                                           schema=schema, schema_name=name, reasoning_effort=effort,
                                           max_tokens=max_tokens)
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            raise MetaAPIError(f"{model} returned text that is not JSON") from None
        return data, ModelCall(provider="meta", model=model, role=name.replace("_", " "), cached=cached,
                               latency_s=time.perf_counter() - start)

    def predict_odds(self, facts: dict[str, Any]) -> OddsGuess:
        start = time.perf_counter()
        messages = [
            {"role": "system", "content": ODDS_SYSTEM},
            {"role": "user", "content": f"Circuit:\n{json.dumps(facts, indent=1)}\n\n"
                                        "What are the measured outcome probabilities?"},
        ]
        data, cached, _ = self._json(messages, ODDS_SCHEMA, "outcome_odds", "medium", max_tokens=24000)
        outcomes: dict[str, float] = {}
        for o in data.get("outcomes", []) if isinstance(data.get("outcomes"), list) else []:
            if isinstance(o, dict) and isinstance(o.get("bits"), str) and isinstance(o.get("probability"), (int, float)):
                bits = o["bits"].strip().replace(" ", "")
                outcomes[bits] = outcomes.get(bits, 0.0) + max(0.0, float(o["probability"]))
        if not outcomes:
            raise MetaAPIError(f"{self.model} returned no outcomes")
        return OddsGuess(outcomes=outcomes, reasoning=str(data.get("reasoning", ""))[:600],
                         call=ModelCall(provider="meta", model=self.model, role="predict alone", cached=cached,
                                        latency_s=time.perf_counter() - start))

    def find_bug(self, facts: dict[str, Any]) -> BugGuess:
        start = time.perf_counter()
        messages = [
            {"role": "system", "content": BUGHUNT_SYSTEM},
            {"role": "user", "content": f"Broken circuit and results:\n{json.dumps(facts, indent=1)}\n\n"
                                        "Which operation is wrong?"},
        ]
        data, cached, _ = self._json(messages, BUG_SCHEMA, "bug_report", "medium")
        index = data.get("index")
        if not isinstance(index, int):
            raise MetaAPIError(f"{self.model} returned no operation index")
        return BugGuess(index=index, fix=str(data.get("fix", ""))[:200], reason=str(data.get("reason", ""))[:500],
                        call=ModelCall(provider="meta", model=self.model, role="find bug", cached=cached,
                                       latency_s=time.perf_counter() - start))

    def read_notation(self, image: bytes, mime: str) -> NotationRead:
        start = time.perf_counter()
        messages = [
            {"role": "system", "content": NOTATION_SYSTEM},
            {"role": "user", "content": [{"type": "text", "text": "Transcribe the quantum notation in this photo."},
                                         _image_part(image, mime)]},
        ]
        data, cached, _ = self._json(messages, NOTATION_SCHEMA, "notation", "low", max_tokens=4000)
        text = str(data.get("text", "")).strip()
        if not text or data.get("kind") == "none":
            raise MetaAPIError(f"{self.model} found no quantum notation in the photo")
        return NotationRead(kind=str(data.get("kind", "")), text=text[:4000], notes=str(data.get("notes", ""))[:300],
                            call=ModelCall(provider="meta", model=self.model, role="read notation", cached=cached,
                                           latency_s=time.perf_counter() - start))

    def hint(self, facts: dict[str, Any]) -> Explanation:
        start = time.perf_counter()
        content, cached = self.client.chat(self.model, [
            {"role": "system", "content": HINT_SYSTEM},
            {"role": "user", "content": f"Puzzle and progress:\n{json.dumps(facts, indent=1, default=str)}\n\nGive the hint."},
        ], reasoning_effort="low", max_tokens=3000)
        if not content.strip():
            raise MetaAPIError("empty hint")
        return Explanation(text=content.strip(), call=ModelCall(provider="meta", model=self.model, role="hint",
                                                                cached=cached, latency_s=time.perf_counter() - start))

    def explain(self, spec: CircuitSpec | NetworkSpec, result: dict[str, Any],
                language: str = "English") -> Explanation:
        start = time.perf_counter()
        facts = _explain_facts(spec, result)
        script = f", in {SCRIPTS[language]} script, not in Latin letters" if language in SCRIPTS else ""
        lang = "" if language == "English" else (f" Write the explanation in {language}{script}; keep numbers, "
                                                 "qubit names like q0 and bitstrings like |00> as they are.")
        content, cached = self.client.chat(self.model, [
            {"role": "system", "content": EXPLAIN_SYSTEM},
            {"role": "user", "content": f"Design spec:\n{spec.model_dump_json(by_alias=True, exclude_none=True)}"
                                        f"\n\nResults:\n{json.dumps(facts, indent=1)}\n\nExplain these results.{lang}"},
        ], reasoning_effort="low", max_tokens=6000)
        call = ModelCall(provider="meta", model=self.model, role="explain", cached=cached,
                         latency_s=time.perf_counter() - start)
        if not content.strip():
            raise MetaAPIError("empty explanation")
        return Explanation(text=content.strip(), call=call, language=language)


def _grid_segments(spec: dict[str, Any], model: str) -> list[Segment]:
    """Turn boxes the reader reported itself (no SAM match) into labelled overlay segments."""
    out: list[Segment] = []
    groups = ("operations",) if spec.get("kind") == "circuit" else ("nodes", "links")
    for group in groups:
        for item in spec.get(group, []):
            src = item.get("source")
            if src and not src.get("segment_id"):
                src["segment_id"] = f"m{len(out)}"
                out.append(Segment(id=src["segment_id"], concept=f"seen by {model}", bbox=tuple(src["bbox"]),
                                   confidence=src["confidence"]))
    return out


def _rounded(d: dict[str, float] | None) -> dict[str, float]:
    return {k: round(v, 4) for k, v in sorted((d or {}).items(), key=lambda kv: -kv[1])[:16]}


def _explain_facts(spec: CircuitSpec | NetworkSpec, result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(spec, CircuitSpec):
        v = result.get("verdict") or {}
        noise = v.get("noise", "ideal")
        return {
            "verified": result.get("verified"), "noise_preset": get_preset(noise).as_dict(),
            "ideal_probabilities": _rounded(v.get("ideal")), "measured_probabilities": _rounded(v.get("measured")),
            "exact_noisy_prediction": _rounded(v.get("expected")), "metrics": v.get("metrics"),
            "attempts": len(result.get("attempts", [])), "planted_fault": result.get("fault"),
            "bit_order": "Qiskit: rightmost character is classical bit 0",
        }
    return {k: result.get(k) for k in ("before", "after", "fix", "candidates", "path")}


class MetaImageModel(ImageModel):
    """Muse Image draws a clean, annotated diagram of the final design."""

    def __init__(self, settings: Settings, client: MetaClient):
        self.model = settings.image_model
        self.client = client

    def diagram(self, spec: CircuitSpec | NetworkSpec, result: dict[str, Any]) -> DiagramResult:
        start = time.perf_counter()
        prompt = diagram_prompt(spec, result)
        data, cached = self.client.post("/images/generations", {
            "model": self.model, "prompt": prompt, "n": 1, "size": "1536x1024",
            "response_format": "b64_json", "output_format": "png", "reasoning_strength": "high",
        })
        try:
            b64 = data["data"][0]["b64_json"]
            base64.b64decode(b64[:64] + "=" * (-len(b64[:64]) % 4))
        except (KeyError, IndexError, TypeError, ValueError):
            raise MetaAPIError("image generation returned no image") from None
        call = ModelCall(provider="meta", model=self.model, role="diagram", cached=cached,
                         latency_s=time.perf_counter() - start)
        return DiagramResult(image_b64=b64, mime="image/png", call=call,
                             caption="Illustration by Muse Image. The exact circuit is the Qiskit drawing.")

    def edit(self, image_b64: str, mime: str, prompt: str) -> DiagramResult:
        """``POST /images/edits`` with the figure as a data URL (docs/meta-api/api-reference_images_edit-image.md)."""
        start = time.perf_counter()
        data, cached = self.client.post("/images/edits", {
            "model": self.model, "prompt": prompt, "images": [{"image_url": f"data:{mime};base64,{image_b64}"}],
            "n": 1, "size": "1536x1024", "response_format": "b64_json", "output_format": "png",
            "reasoning_strength": "high",
        })
        try:
            b64 = data["data"][0]["b64_json"]
        except (KeyError, IndexError, TypeError):
            raise MetaAPIError("image edit returned no image") from None
        return DiagramResult(image_b64=b64, mime="image/png", caption="Corrected by Muse Image.",
                             call=ModelCall(provider="meta", model=self.model, role="correct figure", cached=cached,
                                            latency_s=time.perf_counter() - start))


def diagram_prompt(spec: CircuitSpec | NetworkSpec, result: dict[str, Any]) -> str:
    """A precise description of the design for Muse Image."""
    style = ("Flat, precise technical illustration on a dark charcoal background (#16171b), off-white lines and "
             "labels, a single warm gold accent for the entangling element, generous spacing, legible sans-serif "
             "text, no glow, no gradients, no decorative particles. Draw exactly what is described, nothing more.")
    if isinstance(spec, CircuitSpec):
        steps = []
        for op in spec.operations:
            if spec.is_dynamic() and op.gate == "MEASURE":
                steps.append("a measurement meter in the middle of " + ", ".join(f"q{q}" for q in op.targets)
                             + ", its result sent down a double line to classical bit "
                             + ", ".join(f"c{c}" for c in op.clbits))
                continue
            before = len(steps)
            if op.gate in ("CX", "CZ"):
                steps.append(f"{op.gate} with control on wire q{op.controls[0]} (solid dot) and target on wire "
                             f"q{op.targets[0]} ({'circled plus' if op.gate == 'CX' else 'solid dot'})")
            elif op.gate == "CCX":
                steps.append(f"Toffoli with controls on q{op.controls[0]} and q{op.controls[1]} (solid dots) "
                             f"and target on q{op.targets[0]} (circled plus)")
            elif op.gate == "CP":
                steps.append(f"controlled phase P({op.params[0]:.2f} rad) between q{op.controls[0]} and "
                             f"q{op.targets[0]} (two solid dots joined, labelled P)")
            elif op.gate == "SWAP":
                steps.append(f"SWAP between q{op.targets[0]} and q{op.targets[1]} (two crosses joined)")
            elif op.gate not in ("BARRIER", "MEASURE"):
                angle = f"({op.params[0]:.2f} rad)" if op.params else ""
                steps.append(f"a box labelled {op.gate}{angle} on " + ", ".join(f"q{q}" for q in op.targets))
            if op.conditional is not None and len(steps) > before:
                pairs = op.conditional.pairs()
                when = " and ".join(f"c{c} reads {v}" for c, v in pairs)
                wires = ", ".join(f"c{c} (={v})" for c, v in pairs)
                steps[-1] += f", applied only when {when} (a dashed line from the gate down to {wires})"
        measured = (result.get("verdict") or {}).get("measured", {})
        top = ", ".join(f"{k}: {v * 100:.0f}%" for k, v in sorted(measured.items(), key=lambda kv: -kv[1])[:4])
        return (f"An annotated quantum circuit diagram titled '{spec.metadata.title or 'Quantum circuit'}'. "
                f"{spec.num_qubits} horizontal wires labelled q0 to q{spec.num_qubits - 1} from top to bottom. "
                f"Left to right: {'; '.join(steps)}; then a measurement meter at the end of every wire. "
                + ("No captions, step labels or other text besides the title, the wire labels and the gate letters. "
                   if result.get("plain") else "Add one short caption under each step explaining it for a student. ")
                + (f"To the right, a small bar chart of the measured results ({top}). " if top else "")
                + style)
    nodes = "; ".join(f"{n.label or n.id} ({n.type.replace('_', ' ')})" for n in spec.nodes)
    links = "; ".join(f"{l.from_node} to {l.to_node}: {l.medium.replace('_', ' ')}, {l.length_km:g} km"
                      for l in spec.links)
    return (f"An annotated quantum network diagram titled '{spec.metadata.title or 'Quantum network'}'. "
            f"Nodes: {nodes}. Links: {links}. Entangled photon pairs travel from {spec.source} to "
            f"{spec.destination}; label each link with its distance. " + style)
