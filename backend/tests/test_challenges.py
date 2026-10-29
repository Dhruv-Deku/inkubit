"""Challenge mode: exact scoring, stars against par, hints, and the live-state endpoint."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from qcanvas.adapters.config import load_settings
from qcanvas.adapters.meta_vision import MetaReasoningModel
from qcanvas.api.app import app
from qcanvas.challenges import BY_ID, CHALLENGES, check, hint_facts, info

client = TestClient(app)


def _spec(n, ops):
    return {"kind": "circuit", "num_qubits": n, "num_clbits": n, "operations": ops,
            "measurements": [{"qubit": q, "clbit": q} for q in range(n)]}


def _ref(ch):
    return _spec(ch.num_qubits, list(ch.solution))


@pytest.mark.parametrize("ch", CHALLENGES, ids=lambda c: c.id)
def test_every_reference_solution_scores_three_stars_at_par(ch):
    res = check(ch, _ref(ch))
    assert res.solved and res.stars == 3 and res.gates == ch.par and res.fidelity == pytest.approx(1.0)
    assert res.lesson == ch.lesson
    # the hints never spell out the whole reference sequence
    assert len(ch.hints) >= 2


def test_solutions_are_never_sent_to_the_browser():
    body = client.get("/api/challenges").json()
    assert {c["id"] for c in body["challenges"]} == set(BY_ID)
    text = json.dumps(body)
    assert "solution" not in text and "lesson" not in text and "authored" not in text
    w = next(c for c in body["challenges"] if c["id"] == "w")
    assert [a["basis"] for a in w["target"]] == ["001", "010", "100"]
    assert w["starter"]["operations"] == [] and len(w["starter"]["measurements"]) == 3


def test_targets_show_what_to_build():
    minus = info(BY_ID["minus"])
    assert [round(a.phase, 3) for a in minus.target] == [0.0, 3.142]  # same odds as the coin, opposite sign
    assert minus.target_bloch[0] == pytest.approx([-1, 0, 0], abs=1e-6)
    cz = info(BY_ID["cz-from-cx"])
    assert [(r.input, r.output) for r in cz.table][-1] == ("|11⟩", "−|11⟩")
    swap = info(BY_ID["swap-cx"])
    assert [(r.input, r.output) for r in swap.table][1] == ("|01⟩", "|10⟩")


def test_other_correct_answers_count_and_global_phase_is_ignored():
    # |−⟩ also comes from H then Z; the singlet built differently differs by a global phase of -1
    assert check(BY_ID["minus"], _spec(1, [{"gate": "H", "targets": [0]}, {"gate": "Z", "targets": [0]}])).solved
    singlet = [{"gate": "X", "targets": [0]}, {"gate": "H", "targets": [0]}, {"gate": "X", "targets": [1]},
               {"gate": "CX", "targets": [1], "controls": [0]}]
    assert check(BY_ID["singlet"], _spec(2, singlet)).solved


def test_stars_follow_par():
    coin = BY_ID["coin"]
    long_way = [{"gate": "H", "targets": [0]}, {"gate": "X", "targets": [0]}, {"gate": "X", "targets": [0]}]
    assert check(coin, _spec(1, long_way)).stars == 2
    five = long_way + [{"gate": "Z", "targets": [0]}, {"gate": "Z", "targets": [0]}]
    res = check(coin, _spec(1, five))
    assert res.stars == 1 and "par is 1" in res.message
    barrier = [{"gate": "H", "targets": [0]}, {"gate": "BARRIER", "targets": []}]
    assert check(coin, _spec(1, barrier)).stars == 3  # barriers are not gates


def test_near_misses_say_what_is_off():
    assert check(BY_ID["minus"], _spec(1, [{"gate": "H", "targets": [0]}])).message == \
        "The probabilities are already right; a relative phase is off."
    res = check(BY_ID["bell"], _spec(2, [{"gate": "H", "targets": [0]}]))
    assert not res.solved and res.fidelity == pytest.approx(0.25) and "25%" in res.message  # |<Bell|+0>|^2
    res = check(BY_ID["swap-cx"], _spec(2, [{"gate": "CX", "targets": [1], "controls": [0]}]))
    assert res.rows_right == 1 and "1 of 4" in res.message
    assert "uses 2 qubits" in check(BY_ID["bell"], _spec(3, [])).message
    assert check(BY_ID["bell"], _spec(2, [])).message.startswith("Add gates")


def test_gate_restrictions_are_enforced():
    res = check(BY_ID["x-from-hz"], _spec(1, [{"gate": "X", "targets": [0]}]))
    assert not res.solved and res.illegal == ["X"] and "allows only H, Z" in res.message


def test_noisy_fidelity_shows_what_hardware_keeps():
    res = check(BY_ID["ghz"], _ref(BY_ID["ghz"]))
    assert 0.9 < res.noisy_fidelity < 0.999
    assert check(BY_ID["swap-cx"], _ref(BY_ID["swap-cx"])).noisy_fidelity is None  # gate puzzles: process only


def test_check_and_hint_endpoints():
    r = client.post("/api/challenges/bell/check", json={"spec": _ref(BY_ID["bell"])})
    assert r.status_code == 200 and r.json()["stars"] == 3
    assert client.post("/api/challenges/nope/check", json={"spec": _spec(1, [])}).status_code == 404
    bad = client.post("/api/challenges/bell/check", json={"spec": {"kind": "circuit"}}).json()
    assert not bad["solved"] and bad["message"].startswith("Fix the spec first")
    hint = client.post("/api/challenges/bell/hint", json={"spec": _spec(2, []), "number": 1}).json()
    assert hint["text"] == BY_ID["bell"].hints[1] and hint["call"]["provider"] == "mock"
    last = client.post("/api/challenges/bell/hint", json={"spec": _spec(2, []), "number": 9}).json()
    assert last["text"] == BY_ID["bell"].hints[-1]


class FakeClient:
    def __init__(self, reply):
        self.reply, self.requests = reply, []

    def chat(self, model, messages, **kw):
        self.requests.append(messages)
        return self.reply, False


def test_live_hint_gets_progress_but_never_the_solution():
    ch = BY_ID["w"]
    facts = hint_facts(ch, _spec(3, [{"gate": "H", "targets": [0]}]), 0)
    fake = FakeClient("Try an uneven rotation on q0 first.")
    out = MetaReasoningModel(load_settings(), fake).hint(facts)  # type: ignore[arg-type]
    assert out.call.provider == "meta" and out.call.role == "hint" and out.text.startswith("Try")
    sent = fake.requests[0][1]["content"]
    assert '"player_circuit"' in sent and "Overlap with the target" in sent
    assert "1.9106" not in sent and "solution" not in sent  # the reference angles never leave the server


def test_live_state_endpoint_is_fast_and_exact(example):
    r = client.post("/api/state", json={"spec": example("teleportation")})
    body = r.json()
    assert r.status_code == 200 and body["noisy"] is None
    assert body["ideal"] == pytest.approx({"0": 0.25, "1": 0.75})
    # teleportation: q2 ends exactly where q0 started
    assert body["steps"][-1]["bloch"][2] == pytest.approx(body["steps"][1]["bloch"][0], abs=1e-6)
    better = client.post("/api/state", json={"spec": example("bell"), "scale": 0.1}).json()["noisy"]
    worse = client.post("/api/state", json={"spec": example("bell"), "scale": 4}).json()["noisy"]
    assert better["fidelity"] > worse["fidelity"] and better["baseline"] == "realistic"
    perfect = client.post("/api/state", json={"spec": example("bell"), "scale": 0}).json()["noisy"]
    assert perfect["fidelity"] == pytest.approx(1.0)
    assert client.post("/api/state", json={"spec": example("bell"), "scale": -1}).status_code == 422
    assert client.post("/api/state", json={"spec": example("network_satellite")}).status_code == 422
