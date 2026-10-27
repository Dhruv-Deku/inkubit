"""P8: explanations and diagrams (offline templates and the Muse adapters with a fake client)."""

from __future__ import annotations

import base64
import json

from qcanvas.adapters.config import load_settings
from qcanvas.adapters.meta_vision import MetaImageModel, MetaReasoningModel, diagram_prompt
from qcanvas.adapters.mock_vision import MockImageModel, MockReasoningModel
from qcanvas.network.agent import run_network_agent
from qcanvas.spec import parse_spec
from qcanvas.verify import verify_counts

PNG = b"\x89PNG\r\n\x1a\n"


def bell_result(example, noise: str = "realistic") -> dict:
    spec = parse_spec(example("bell"))
    counts = {"00": 1930, "11": 1850, "01": 160, "10": 156}
    verdict = verify_counts(spec, counts, noise)
    return {"verified": verdict.passed, "verdict": verdict.model_dump(mode="json"), "attempts": [{}, {}],
            "fault": {"name": "missing_cnot", "label": "Missing CNOT", "description": "x"}}


def test_circuit_explanation_uses_real_numbers(example):
    spec = parse_spec(example("bell"))
    result = bell_result(example)
    text = MockReasoningModel().explain(spec, result).text
    assert "Hadamard" in text and "CNOT" in text and "entanglement" in text
    stray = (160 + 156) / 4096 * 100
    assert f"{stray:.1f}%" in text
    assert "Missing CNOT" in text and len(text.split("\n\n")) == 3


def test_network_explanation_mentions_fixes(example):
    spec = parse_spec(example("network_fiber_chain"))
    result = run_network_agent(spec).model_dump(mode="json")
    text = MockReasoningModel().explain(spec, result).text
    assert "entanglement swapping" in text and "relay" in text and "secret key" in text


def test_mock_diagrams_are_pngs(example):
    for name in ("bell", "network_satellite"):
        spec = parse_spec(example(name))
        result = run_network_agent(spec).model_dump(mode="json") if spec.kind == "network" else bell_result(example)
        out = MockImageModel().diagram(spec, result)
        assert base64.b64decode(out.image_b64).startswith(PNG) and out.call.provider == "mock"


class FakeClient:
    def __init__(self, reply):
        self.reply, self.requests = reply, []

    def chat(self, model, messages, **kw):
        self.requests.append({"model": model, "messages": messages, **kw})
        return self.reply, False

    def post(self, path, payload, use_cache=True):
        self.requests.append({"path": path, **payload})
        return self.reply, False


def test_meta_explain_sends_the_numbers(example):
    client = FakeClient("Your circuit makes a Bell pair...")
    model = MetaReasoningModel(load_settings(), client)  # type: ignore[arg-type]
    out = model.explain(parse_spec(example("bell")), bell_result(example))
    sent = client.requests[0]["messages"][1]["content"]
    assert "measured_probabilities" in sent and "exact_noisy_prediction" in sent
    assert out.call.model == "muse-spark-1.3" and out.text.startswith("Your circuit")


def test_meta_image_request_shape(example):
    b64 = base64.b64encode(PNG + b"rest").decode()
    client = FakeClient({"created": 1, "data": [{"b64_json": b64}]})
    model = MetaImageModel(load_settings(), client)  # type: ignore[arg-type]
    out = model.diagram(parse_spec(example("ghz3")), {})
    req = client.requests[0]
    assert req["path"] == "/images/generations" and req["model"] == "muse-image-1.0"
    assert req["response_format"] == "b64_json" and req["output_format"] == "png"
    assert out.image_b64 == b64 and out.call.provider == "meta"


def test_diagram_prompt_describes_every_gate(example):
    prompt = diagram_prompt(parse_spec(example("ghz3")), {})
    assert prompt.count("control on wire") == 2 and "box labelled H" in prompt and "no glow" in prompt
    net = diagram_prompt(parse_spec(example("network_satellite")), {})
    assert "1100 km" in net and "satellite" in net
    json.dumps(prompt)
