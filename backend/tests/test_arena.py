"""AI alone vs Q-Canvas: scoring a model's own prediction against exact simulation, and the endpoints."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from qcanvas.adapters.config import load_settings
from qcanvas.adapters.meta_vision import MetaReasoningModel
from qcanvas.api.app import app
from qcanvas.arena import compare, facts, load_benchmark
from qcanvas.spec import parse_spec


def bell(example):
    return parse_spec(example("bell"))


def test_scoring(example):
    spec = bell(example)
    assert compare(spec, {"00": 0.5, "11": 0.5}).verdict == "matched"
    near = compare(spec, {"00": 0.52, "11": 0.48})
    assert near.verdict == "close" and near.tvd == pytest.approx(0.02)
    wrong = compare(spec, {"00": 0.25, "01": 0.25, "10": 0.25, "11": 0.25})
    assert wrong.verdict == "wrong" and wrong.tvd == pytest.approx(0.5)
    assert wrong.impossible == ["01", "10"] and wrong.missed == []
    off = compare(spec, {"00": 1.0})
    assert off.missed == ["11"] and off.verdict == "wrong"
    loose = compare(spec, {"00": 0.6, "11": 0.6})  # does not add up: normalised for the distance, flagged
    assert loose.guess_sum == pytest.approx(1.2) and loose.verdict == "close"


def test_the_model_never_sees_the_title_or_notes(example):
    f = facts(bell(example))
    text = json.dumps(f)
    assert "Bell" not in text and "notes" not in text and f["measured"]


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def chat(self, model, messages, **kw):
        self.calls.append((messages, kw))
        return self.reply, True


def test_live_adapter_reads_the_outcome_list(example):
    fake = FakeClient(json.dumps({"outcomes": [{"bits": "0 0", "probability": 0.5}, {"bits": "11", "probability": 0.5},
                                               {"bits": "10", "probability": "x"}], "reasoning": "H then CX."}))
    g = MetaReasoningModel(load_settings(), fake).predict_odds(facts(bell(example)))  # type: ignore[arg-type]
    assert g.outcomes == {"00": 0.5, "11": 0.5} and g.call.role == "predict alone" and g.call.cached
    messages, kw = fake.calls[0]
    assert kw["schema_name"] == "outcome_odds" and "cannot run code" in messages[0]["content"]


def test_endpoints(example):
    c = TestClient(app)
    assert c.post("/api/arena", json={"spec": example("bell")}).status_code == 409  # offline: never a made-up answer
    no_meas = {**example("bell"), "measurements": [], "num_clbits": 0}
    assert c.post("/api/arena", json={"spec": no_meas}).status_code == 422
    r = c.get("/api/arena/benchmark")
    assert r.status_code == (200 if load_benchmark() else 404)


def test_new_and_bigger_circuits_are_valid_repeatable_and_unnamed():
    from qcanvas.arena import bigger_circuits, fresh_circuits

    assert fresh_circuits() == fresh_circuits() and bigger_circuits() == bigger_circuits()
    for d in fresh_circuits() + bigger_circuits():
        spec = parse_spec(d)
        assert spec.measured_pairs() and "notes" not in json.dumps(facts(spec))
    big = bigger_circuits()
    assert [d["num_qubits"] for d in big] == [6, 6, 7, 7, 8, 8] and all(d["num_clbits"] == 4 for d in big)
