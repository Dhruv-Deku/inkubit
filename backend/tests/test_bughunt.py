"""Bug hunt: rounds are reproducible and fair, the search always finds the planted bug, and the endpoints hold."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from qcanvas.adapters.config import load_settings
from qcanvas.adapters.meta_vision import MetaReasoningModel
from qcanvas.api.app import app
from qcanvas.bughunt import _round, bug_round, describe, judge, muse_facts, search
from qcanvas.verify.metrics import total_variation_distance


@pytest.mark.parametrize("level", [1, 2])
def test_every_planted_bug_is_visible_and_found_by_the_search(level):
    for seed in range(15):
        rnd, bug, good, _ = _round(level, seed)
        s = search(level, seed)
        assert bug.index in s.culprits and s.checked > len(s.culprits)
        assert sum(rnd.observed.values()) == rnd.shots == 1000
        assert set(rnd.observed) - set(rnd.intended) or total_variation_distance(
            rnd.intended, {k: v / 1000 for k, v in rnd.observed.items()}) > 0.1


def test_rounds_are_reproducible_and_never_carry_the_answer():
    a, b = bug_round(2, 41), bug_round(2, 41)
    assert a == b
    dumped = json.dumps(a.model_dump(mode="json"))
    assert "planted" not in dumped and "notes" not in json.dumps(a.spec["metadata"])
    assert a.spec["metadata"]["title"].endswith("(one gate is wrong)")


def test_judge_accepts_any_gate_whose_edit_restores_the_odds():
    rnd, bug, good, _ = _round(1, 3)
    v = judge(1, 3, bug.index)
    assert v.correct and v.planted == bug.index and v.fixed == good
    wrong = next(i for i in range(len(rnd.spec["operations"])) if i not in v.machine.culprits)
    assert not judge(1, 3, wrong).correct
    for c in v.machine.culprits:
        assert judge(1, 3, c).correct


def test_describe_reads_like_a_person_would_say_it():
    assert describe({"gate": "CX", "controls": [0], "targets": [2], "params": []}) == "CX q0→q2"
    assert describe({"gate": "RY", "controls": [], "targets": [1], "params": [1.5707963267948966]}) == "RY(π/2) on q1"
    assert describe({"gate": "SDG", "controls": [], "targets": [0], "params": []}) == "S† on q0"


def test_muse_sees_what_the_player_sees():
    facts = muse_facts(2, 7)
    rnd = bug_round(2, 7)
    assert [o["index"] for o in facts["operations"]] == list(range(len(rnd.spec["operations"])))
    assert facts["observed_counts"] == dict(sorted(rnd.observed.items()))
    assert "fixed" not in facts and "planted" not in facts


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def chat(self, model, messages, **kw):
        self.calls.append((messages, kw))
        return self.reply, False


def test_live_adapter_asks_with_the_bug_schema():
    fake = FakeClient(json.dumps({"index": 2, "fix": "move the H to q0", "reason": "q0 never splits."}))
    g = MetaReasoningModel(load_settings(), fake).find_bug(muse_facts(1, 0))  # type: ignore[arg-type]
    assert g.index == 2 and g.call.role == "find bug" and not g.call.cached
    messages, kw = fake.calls[0]
    assert kw["schema_name"] == "bug_report" and "Exactly one operation" in messages[0]["content"]


def test_endpoints():
    c = TestClient(app)
    r = c.get("/api/bughunt/round", params={"level": 1, "seed": 12})
    assert r.status_code == 200 and r.json()["id"] == "1-12"
    v = c.post("/api/bughunt/guess", json={"level": 1, "seed": 12, "index": 0}).json()
    assert {"correct", "planted", "detail", "fixed", "machine"} <= set(v)
    assert c.get("/api/bughunt/round", params={"level": 4}).status_code == 422
    assert c.post("/api/bughunt/muse", json={"level": 1, "seed": 12}).status_code == 409  # offline: no fake opponent


def test_rounds_are_fair_and_the_hard_level_includes_the_qaoa_circuit():
    from qcanvas.bughunt import MAX_SHARE

    titles = set()
    for level, seeds in ((1, range(10)), (3, range(4))):
        for seed in seeds:
            rnd, bug, good, found = _round(level, seed)
            assert len(found.culprits) <= max(1, MAX_SHARE[level] * rnd.gates)
            titles.add(rnd.title)
    assert any(t.startswith("QAOA") for t in titles) or any(t.startswith("Phase") for t in titles)
