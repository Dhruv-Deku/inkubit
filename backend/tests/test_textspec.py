"""Describe-it-in-words: the offline parser and the live adapter (with a fake client)."""

from __future__ import annotations

import json

import pytest

from qcanvas.adapters.config import load_settings
from qcanvas.adapters.meta_vision import MetaReasoningModel
from qcanvas.adapters.mock_vision import MockReasoningModel
from qcanvas.spec import parse_spec
from qcanvas.textspec import UnknownTextError, parse_description
from qcanvas.verify import ideal_distribution


@pytest.mark.parametrize("text,answer", [
    ("Bell pair", {"00": 0.5, "11": 0.5}),
    ("GHZ state on 4 qubits", {"0000": 0.5, "1111": 0.5}),
    ("Bernstein-Vazirani with secret 1011", {"1011": 1.0}),
    ("superdense coding sending 10", {"10": 1.0}),
    ("superdense coding sending 01", {"01": 1.0}),
    ("Deutsch-Jozsa with a constant oracle", {"00": 1.0}),
    ("grover search", {"11": 1.0}),
    ("h 0; cx 0 1", {"00": 0.5, "11": 0.5}),
    ("x 0, x 1, ccx 0 1 2", {"111": 1.0}),
    ("rx pi 0; measure 0", {"1": 1.0}),
])
def test_offline_parser_builds_the_right_circuit(text, answer):
    spec, _ = parse_description(text)
    parsed = parse_spec(spec)
    assert parsed.metadata.origin in ("text", "manual") and ideal_distribution(parsed) == pytest.approx(answer, abs=1e-9)


def test_qft_spreads_amplitude_evenly():
    spec, how = parse_description("QFT on 3 qubits of 5")
    assert "Fourier" in how
    assert ideal_distribution(parse_spec(spec)) == pytest.approx({format(i, "03b"): 1 / 8 for i in range(8)})


def test_networks_from_words():
    spec, _ = parse_description("300 km of fiber with 2 repeaters")
    net = parse_spec(spec)
    assert [l.length_km for l in net.links] == [100, 100, 100] and sum(n.type == "repeater" for n in net.nodes) == 2
    sat, _ = parse_description("a satellite link")
    assert any(n.type == "satellite" for n in parse_spec(sat).nodes)


def test_unknown_text_is_an_honest_error():
    with pytest.raises(UnknownTextError, match="Offline mode understands"):
        parse_description("make me a sandwich")


def test_mock_model_labels_its_answer():
    draft = MockReasoningModel().spec_from_text("GHZ on 3 qubits")
    assert draft.valid and draft.call.model == "offline text parser" and "GHZ" in draft.notes


class FakeClient:
    def __init__(self, chats):
        self.chats, self.requests = list(chats), []

    def chat(self, model, messages, **kw):
        self.requests.append({"model": model, "messages": messages, **kw})
        return self.chats.pop(0), False


def test_live_text_reading_uses_the_draft_schema_and_reprompts():
    bad = {"title": "Bell", "num_qubits": 2, "num_clbits": 2, "notes": "",
           "operations": [{"gate": "CX", "targets": [0], "controls": [0], "params": [], "segment_id": "", "box": []}],
           "measurements": [{"qubit": 0, "clbit": 0, "segment_id": ""}, {"qubit": 1, "clbit": 1, "segment_id": ""}]}
    good = dict(bad, operations=[{"gate": "H", "targets": [0], "controls": [], "params": [], "segment_id": "", "box": []},
                                 {"gate": "CX", "targets": [1], "controls": [0], "params": [], "segment_id": "", "box": []}])
    client = FakeClient([json.dumps(bad), json.dumps(good)])
    draft = MetaReasoningModel(load_settings(), client).spec_from_text("an entangled pair of qubits")  # type: ignore[arg-type]
    assert draft.valid and draft.attempts == 2 and draft.spec["metadata"]["origin"] == "text"
    first = client.requests[0]
    assert first["schema"]["properties"]["operations"] and "quantum circuit" in first["messages"][1]["content"]
    assert "fails validation" in client.requests[1]["messages"][-1]["content"]
