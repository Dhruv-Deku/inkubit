"""Optimizer: every rewrite is proven by exact simulation, and wrong proposals are rejected."""

from __future__ import annotations

import json
import math
import random

import pytest
from fastapi.testclient import TestClient

from qcanvas.adapters.base import ModelCall, Proposal
from qcanvas.adapters.config import load_settings
from qcanvas.adapters.meta_vision import MetaReasoningModel
from qcanvas.api.app import app
from qcanvas.optimize import cost, optimize, prove, qiskit_proposal, rewrite
from qcanvas.spec import parse_spec

client = TestClient(app)


def _spec(n, ops, measured=None):
    measured = list(range(n)) if measured is None else measured
    return parse_spec({"kind": "circuit", "num_qubits": n, "num_clbits": n, "operations": ops,
                       "measurements": [{"qubit": q, "clbit": i} for i, q in enumerate(measured)]})


H0 = {"gate": "H", "targets": [0]}
CX01 = {"gate": "CX", "controls": [0], "targets": [1]}


def test_identities_that_hold_for_every_input_keep_the_unitary():
    spec = _spec(2, [{"gate": "RY", "targets": [0], "params": [0.4]}, {"gate": "RX", "targets": [1], "params": [0.5]},
                     H0, H0, CX01, CX01, {"gate": "S", "targets": [1]}, {"gate": "S", "targets": [1]},
                     {"gate": "RY", "targets": [1], "params": [0.2]}])
    out, log = rewrite(spec)
    assert [op.gate for op in out.operations] == ["RY", "RX", "Z", "RY"]  # H·H, CX·CX cancel; S·S = Z
    assert {w.rule for w in log} == {"cancel", "merge"} and all(w.level == "any input" for w in log)
    assert prove(spec, out).level == "unitary"


def test_h_on_both_sides_turns_cx_into_cz():
    spec = _spec(2, [{"gate": "RX", "targets": [0], "params": [0.7]}, {"gate": "RX", "targets": [1], "params": [0.2]},
                     {"gate": "H", "targets": [1]}, CX01, {"gate": "H", "targets": [1]},
                     {"gate": "RY", "targets": [1], "params": [0.3]}])
    out, log = rewrite(spec)
    assert [op.gate for op in out.operations] == ["RX", "RX", "CZ", "RY"] and log[0].rule == "conjugate"
    assert prove(spec, out).level == "unitary"


def test_starting_state_rules_are_marked_and_proven_on_the_state():
    spec = _spec(3, [{"gate": "T", "targets": [0]}, {"gate": "CX", "controls": [1], "targets": [2]},
                     {"gate": "X", "targets": [1]}, {"gate": "CCX", "controls": [1, 0], "targets": [2]},
                     H0, {"gate": "CZ", "controls": [1], "targets": [0]}])
    out, log = rewrite(spec)
    # T on |0>: nothing; CX from |0>: never fires; Toffoli with q0 still |0>: never fires;
    # CZ with q1 = |1>: a Z on q0, and that Z right before measurement changes no odds
    assert [op.gate for op in out.operations] == ["X", "H"]
    assert any("never fires" in w.text for w in log) and any(w.level == "from |0>" for w in log)
    assert prove(spec, out).level in ("state", "outcomes")


def test_measurement_rules_keep_the_odds_and_say_so():
    swap = {"gate": "SWAP", "targets": [0, 1]}
    spec = _spec(3, [H0, CX01, {"gate": "H", "targets": [2]}, {"gate": "RZ", "targets": [1], "params": [0.9]},
                     swap, {"gate": "CZ", "controls": [0], "targets": [2]}], measured=[0, 1])
    out, log = rewrite(spec)
    assert [op.gate for op in out.operations] == ["H", "CX"]  # q2 unmeasured, RZ and CZ diagonal, SWAP relabelled
    assert {(m.qubit, m.clbit) for m in out.measurements} == {(1, 0), (0, 1)}
    assert any("saves 3 CNOTs" in w.text for w in log)
    proof = prove(spec, out)
    assert proof.level == "outcomes" and proof.outcome_tvd < 1e-12
    assert cost(out).two_qubit == 1 < cost(spec).two_qubit


def test_a_wrong_circuit_is_rejected_with_the_outcome_that_differs():
    bell = _spec(2, [H0, CX01])
    wrong = _spec(2, [H0])
    proof = prove(bell, wrong)
    assert proof.level == "none" and "Outcome" in proof.detail and proof.outcome_tvd == pytest.approx(0.5)


def _random_spec(rng: random.Random):
    n = rng.randint(1, 4)
    one = ["H", "X", "Y", "Z", "S", "T", "SDG", "TDG", "SX", "RX", "RY", "RZ"]
    angles = [math.pi / 4, math.pi / 2, math.pi, -math.pi / 2, 0.3, 2 * math.pi]
    ops = []
    for _ in range(rng.randint(1, 12)):
        r = rng.random()
        if r < 0.55 or n == 1:
            g = rng.choice(one)
            op = {"gate": g, "targets": [rng.randrange(n)], **({"params": [rng.choice(angles)]} if g[0] == "R" else {})}
        elif r < 0.9 or n == 2:
            g = rng.choice(["CX", "CZ", "CP", "SWAP"])
            a, b = rng.sample(range(n), 2)
            op = ({"gate": g, "targets": [a, b]} if g == "SWAP" else
                  {"gate": g, "controls": [a], "targets": [b], **({"params": [rng.choice(angles)]} if g == "CP" else {})})
        else:
            a, b, c = rng.sample(range(n), 3)
            op = {"gate": "CCX", "controls": [a, b], "targets": [c]}
        ops.append(op)
        if rng.random() < 0.25:
            ops.append(dict(op))
    return _spec(n, ops, measured=rng.sample(range(n), rng.randint(1, n)))


def test_rules_never_change_the_odds_of_random_circuits():
    rng = random.Random(2026)
    fired = set()
    for _ in range(300):
        spec = _random_spec(rng)
        out, log = rewrite(spec)
        fired |= {w.rule for w in log}
        assert prove(spec, out).level != "none", spec.model_dump_json(exclude_none=True)
    assert fired >= {"cancel", "merge", "start", "unmeasured", "before-measure"}


def test_qiskit_finds_the_classical_core_of_superdense_coding(example):
    spec = parse_spec(example("superdense"))
    q = qiskit_proposal(spec)
    assert not isinstance(q, str) and prove(spec, q).level == "unitary"
    assert cost(q).two_qubit == 0 < cost(spec).two_qubit


def test_optimize_picks_the_cheapest_proven_candidate(example):
    spec = parse_spec(example("phase_estimation"))
    res = optimize(spec)
    assert [c.source for c in res.candidates] == ["rules", "qiskit", "combined"]
    best = res.candidates[res.best]
    assert best.better and best.proof.level != "none"
    assert all(best.cost.two_qubit <= c.cost.two_qubit for c in res.candidates if c.accepted)
    assert best.cost.fidelity > res.original.fidelity  # fewer gates, less noise
    tight = optimize(parse_spec(example("bell")))
    assert tight.best is None and "already tight" in tight.summary


def _proposer(*replies):
    seen = []

    def propose(facts):
        seen.append(facts)
        reply = replies[len(seen) - 1]
        if isinstance(reply, Exception):
            raise reply
        return Proposal(operations=reply, idea="Dropped what measurement cannot see.",
                        call=ModelCall(provider="meta", model="muse-spark-1.3", role="optimize"))
    return propose, seen


def test_a_wrong_model_proposal_is_rejected_and_the_retry_sees_why():
    spec = _spec(2, [H0, CX01, {"gate": "Z", "targets": [1]}])
    propose, seen = _proposer([H0], [H0, CX01])  # first drops the CNOT (wrong), then just the Z (right)
    res = optimize(spec, propose)
    muse = res.candidates[-1]
    assert muse.source == "muse" and muse.attempts == 2 and muse.accepted and muse.better
    assert "previous_attempt" in seen[1] and "Rejected" in seen[1]["previous_attempt"]["problem"]
    assert "solution" not in json.dumps(seen[0])


def test_a_model_that_fails_or_cheats_is_reported_not_trusted():
    spec = _spec(2, [H0, CX01])
    propose, _ = _proposer(RuntimeError("timeout"))
    res = optimize(spec, propose)
    assert "model call failed" in res.candidates[-1].note and not res.candidates[-1].accepted
    propose, _ = _proposer([], [{"gate": "X", "targets": [5]}])  # nothing at all, then an invalid qubit
    res = optimize(spec, propose)
    muse = res.candidates[-1]
    assert not muse.accepted and muse.note.startswith(("Rejected", "Not usable")) and res.best is None


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def chat(self, model, messages, **kw):
        self.calls.append((messages, kw))
        return self.reply, True


def test_live_adapter_sends_the_circuit_with_a_schema_and_returns_the_proposal():
    fake = FakeClient(json.dumps({"idea": "H twice is nothing.", "operations": [CX01]}))
    prop = MetaReasoningModel(load_settings(), fake).optimize({"operations": [H0, H0, CX01]})  # type: ignore[arg-type]
    assert prop.operations == [CX01] and prop.call.role == "optimize" and prop.call.cached
    messages, kw = fake.calls[0]
    assert kw["schema_name"] == "circuit_rewrite" and "exact simulation" in messages[0]["content"]


def test_optimize_endpoint_offline_says_who_competed(example):
    r = client.post("/api/optimize", json={"spec": example("grover2")})
    body = r.json()
    assert r.status_code == 200 and "Muse Spark" in body["ai_note"]
    assert [c["source"] for c in body["candidates"]] == ["rules", "qiskit", "combined"]
    assert body["candidates"][body["best"]]["proof"]["level"] == "unitary"
    assert client.post("/api/optimize", json={"spec": example("network_satellite")}).status_code == 422
