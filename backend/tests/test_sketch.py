"""P5: SAM output parsing, sample sketches, spec drafting and the live adapters (with a fake client)."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image

from qcanvas import EXAMPLES_DIR
from qcanvas.adapters.config import load_settings
from qcanvas.adapters.meta_vision import MetaReasoningModel, MetaSegmentationModel
from qcanvas.adapters.mock_vision import (
    MockReasoningModel,
    MockSegmentationModel,
    UnknownImageError,
    sample_fixtures,
)
from qcanvas.adapters.registry import Models, _WithFallback, get_models
from qcanvas.adapters.sam_parse import parse_sam_output
from qcanvas.sketch import analyze_image
from qcanvas.spec import parse_spec
from qcanvas.spec.draft import draft_to_spec
from qcanvas.verify import ideal_distribution

IMAGES = EXAMPLES_DIR / "images"
DOC_LINE = ("<0f>0<|box;x1=353;y1=382;x2=453;y2=427;w=537;h=561|><|mask;x=0;y=0;data=46,101,~a|b~!|>,"
            "1<|box;x1=260;y1=382;x2=340;y2=427;w=537;h=561|><|mask;x=0;y=0;data=46,81,~...|>")


def png(name: str) -> bytes:
    return (IMAGES / f"{name}.png").read_bytes()


def test_parse_sam_doc_example():
    boxes = parse_sam_output(DOC_LINE)
    assert [b.object_id for b in boxes] == [0, 1]
    assert (boxes[0].x1, boxes[0].y2, boxes[0].width, boxes[0].height) == (353, 427, 537, 561)
    assert boxes[0].confidence is None


def test_parse_sam_confidence_and_empty():
    line = "<0f>1<|box;x1=444;y1=625;x2=679;y2=850;w=1800;h=1200;c=0.9609375|><|mask;x=0;y=0;c=0.96;data=2,2,!xx|>"
    (box,) = parse_sam_output(line)
    assert box.object_id == 1 and box.confidence == pytest.approx(0.9609375)
    assert parse_sam_output("") == []


def test_fixtures_match_images():
    fixtures = sample_fixtures()
    assert len(fixtures) == 3
    for fx in fixtures.values():
        img = Image.open(io.BytesIO(png(fx["name"])))
        assert img.size == (fx["width"], fx["height"])
        parse_spec(fx["spec"])


def test_bell_sketch_reads_as_bell(example):
    fx = next(f for f in sample_fixtures().values() if f["name"] == "bell_sketch")
    spec = parse_spec(fx["spec"])
    assert ideal_distribution(spec) == pytest.approx(ideal_distribution(parse_spec(example("bell"))))
    assert all(op.source and op.source.segment_id for op in spec.operations)


def test_mock_segmentation_and_unknown_image():
    seg = MockSegmentationModel().segment(png("ghz_sketch"), "image/png")
    assert {s.concept for s in seg.segments} == {"gate box", "dot", "circle", "meter"}
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, format="PNG")
    with pytest.raises(UnknownImageError, match="bundled sample sketches"):
        MockSegmentationModel().segment(buf.getvalue(), "image/png")


@pytest.mark.parametrize("name,kind", [("bell_sketch", "circuit"), ("ghz_sketch", "circuit"),
                                       ("satellite_sketch", "network")])
def test_analyze_image_with_mocks(name, kind):
    analysis, _ = analyze_image(png(name), get_models())
    assert analysis.kind == kind and analysis.valid
    linked = [o for o in analysis.overlay if o.linked_to]
    assert linked, "every sample links at least one box to the spec"
    assert all(c.provider == "mock" for c in analysis.calls)


def test_draft_to_spec_links_segments():
    segs = [{"id": "s0", "concept": "gate box", "bbox": [1, 2, 3, 4], "confidence": 0.9}]
    spec = draft_to_spec("circuit", {
        "title": "t", "num_qubits": 1, "num_clbits": 1, "notes": "",
        "operations": [{"gate": "H", "targets": [0], "controls": [], "params": [], "segment_id": "s0"}],
        "measurements": [{"qubit": 0, "clbit": 0, "segment_id": ""}],
    }, segs)
    parsed = parse_spec(spec)
    assert parsed.operations[0].source.bbox == (1, 2, 3, 4)


class FakeClient:
    """Stands in for MetaClient: records requests, replays canned responses."""

    def __init__(self, chats: list[str] | None = None, sam: dict[str, str] | None = None):
        self.chats = list(chats or [])
        self.sam = sam or {}
        self.requests: list[dict] = []

    def chat(self, model, messages, **kw):
        self.requests.append({"model": model, "messages": messages, **kw})
        return self.chats.pop(0), False

    def post_stream_text(self, path, payload, use_cache=True):
        self.requests.append({"path": path, **payload})
        concept = payload["input"][0]["content"][0]["text"]
        return self.sam.get(concept, ""), False


def test_meta_segmentation_request_shape_and_scaling():
    client = FakeClient(sam={"circle": "<0f>0<|box;x1=10;y1=10;x2=20;y2=30;w=700;h=280;c=0.5|><|mask;x=0;y=0;data=1,1,~!|>"})
    model = MetaSegmentationModel(load_settings(), client)  # type: ignore[arg-type]
    result = model.segment(png("bell_sketch"), "image/png", ["circle", "dot"])
    req = client.requests[0]
    assert req["path"] == "/responses" and req["model"] == "sam-3.1"
    assert req["metadata"] == {"include_confidence": "true"}
    assert req["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,")
    (seg,) = result.segments
    assert seg.bbox == pytest.approx((20, 20, 40, 60))  # 700x280 frame scaled to the 1400x560 image
    assert seg.confidence == 0.5 and result.call.model == "sam-3.1"


def test_meta_draft_reprompts_once_on_invalid_json():
    bad = {"title": "Bell", "num_qubits": 2, "num_clbits": 2, "notes": "",
           "operations": [{"gate": "CX", "targets": [1], "controls": [1], "params": [], "segment_id": ""}],
           "measurements": [{"qubit": 0, "clbit": 0, "segment_id": ""}]}
    good = dict(bad, operations=[{"gate": "H", "targets": [0], "controls": [], "params": [], "segment_id": "s0"},
                                 {"gate": "CX", "targets": [1], "controls": [0], "params": [], "segment_id": "s2"}])
    client = FakeClient(chats=[json.dumps(bad), json.dumps(good)])
    model = MetaReasoningModel(load_settings(), client)  # type: ignore[arg-type]
    segs = MockSegmentationModel().segment(png("bell_sketch"), "image/png")
    draft = model.draft_spec(png("bell_sketch"), "image/png", segs, "circuit")
    assert draft.valid and draft.attempts == 2
    retry = client.requests[1]["messages"][-1]["content"]
    assert "fails validation" in retry and "both a control and a target" in retry
    assert client.requests[0]["schema"]["properties"]["operations"]
    assert draft.spec["operations"][0]["source"]["segment_id"] == "s0"


def test_fallback_is_labelled():
    class Broken:
        def choose_concepts(self, *a):
            raise RuntimeError("HTTP 503: service_overloaded")

    wrapped = _WithFallback(Broken(), MockReasoningModel(), allow=True, kind="reasoning")
    kind, concepts, call = wrapped.choose_concepts(png("bell_sketch"), "image/png")
    assert call.provider == "mock-fallback" and "503" in call.error
    strict = _WithFallback(Broken(), MockReasoningModel(), allow=False, kind="reasoning")
    with pytest.raises(Exception, match="503"):
        strict.choose_concepts(png("bell_sketch"), "image/png")


def test_meta_without_key_falls_back_honestly(monkeypatch):
    monkeypatch.setenv("QCANVAS_MODEL_PROVIDER", "meta")
    monkeypatch.setenv("QCANVAS_ALLOW_FALLBACK", "1")
    monkeypatch.delenv("META_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    models: Models = get_models()
    analysis, _ = analyze_image(png("bell_sketch"), models)
    assert all(c.provider == "mock-fallback" for c in analysis.calls)
    assert "META_API_KEY" in (analysis.calls[0].error or "")
