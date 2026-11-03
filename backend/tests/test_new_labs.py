"""The learning loop, the AI referee, whole-paper reproduction and the code lab: every verdict exact, with scripted
models standing in for Muse Spark and Muse Wonder (no billed call in the tests)."""

from __future__ import annotations

import io
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from inkubit.adapters.base import ModelCall
from inkubit.api.app import app

CHAIN5 = [(0, 1), (1, 0), (1, 2), (2, 1), (2, 3), (3, 2), (3, 4), (4, 3)]


def _call(name: str) -> ModelCall:
    return ModelCall(provider="mock", model="scripted", role=name)


# ---------------------------------------------------------------- learning under proof

def test_the_judge_proves_reaches_and_rejects():
    from inkubit.learning import TARGETS, judge, target_of

    g = TARGETS["w5_line"]
    t, rng, seen = target_of(g), np.random.default_rng(1), set()
    ok = judge(g, t, CHAIN5, rng, seen)
    assert ok.verdict == "reached" and ok.proof > 1 - 1e-8
    assert judge(g, t, CHAIN5, rng, seen).verdict == "repeat"
    assert judge(g, t, [(0, 2)], rng, seen).note == "pair [0, 2] is not wired"
    assert judge(g, t, [(0, 1), (1, 2), (2, 3), (3, 4)], rng, seen).verdict == "missed"  # 4 CNOTs cannot make W5


def test_feedback_reaches_the_prompt_and_random_wiring_uses_the_same_lengths():
    from inkubit.learning import TARGETS, run_condition, target_of

    g = TARGETS["w5_line"]
    seen_prompts = []

    class Scripted:
        def structured(self, system, user, schema, name, effort, max_tokens, model=None):
            seen_prompts.append(json.loads(user))
            k = len(seen_prompts)
            return {"ideas": [{"cnots": [list(p) for p in CHAIN5[:9 - k]], "why": "chain"}]}, _call(name)

    run = run_condition(g, target_of(g), "feedback", Scripted(), rounds=2)
    assert [r.best_so_far for r in run.rounds] == [8, 8]  # round 2 tried 7 CNOTs and missed
    assert seen_prompts[1]["best_proven_cnots_so_far"] == 8 and seen_prompts[1]["earlier_proposals"][0]["result"].startswith("reached")
    rnd = run_condition(g, target_of(g), "random", rounds=2, lengths=[[8], [7]])
    assert [len(p.cnots) for r in rnd.rounds for p in r.proposals] == [8, 7]


def test_learning_endpoints():
    client = TestClient(app)
    bench = client.get("/api/learning/benchmark")
    assert bench.status_code in (200, 404)
    if bench.status_code == 200:
        assert {"feedback", "fresh", "random"} <= set(bench.json()["targets"][0]["curves"])
    assert client.post("/api/learning", json={"goal": "w4"}).status_code == 409  # needs the live model
    assert client.post("/api/learning", json={"goal": "nope"}).status_code == 422


# ---------------------------------------------------------------- the AI referee

def test_the_referee_grades_every_kind_of_claim_exactly():
    from inkubit.referee import check, negativity, questions, truth
    from inkubit.spec import parse_spec

    bell = parse_spec({"kind": "circuit", "version": "1.0", "num_qubits": 3, "num_clbits": 3,
                       "operations": [{"gate": "H", "targets": [0]}, {"gate": "CX", "controls": [0], "targets": [1]},
                                      {"gate": "H", "targets": [2]}],
                       "measurements": [{"qubit": q, "clbit": q} for q in range(3)]})
    probs, psi = truth(bell)
    assert negativity(psi, 0, 1, 3) == pytest.approx(0.5) and negativity(psi, 0, 2, 3) == pytest.approx(0)
    assert check({"kind": "probability", "bits": "011", "probability": 0.25}, probs, psi, 3)[0]
    assert not check({"kind": "probability", "bits": "001", "probability": 0.25}, probs, psi, 3)[0]
    assert check({"kind": "most_likely", "bits": "111"}, probs, psi, 3)[0]  # four outcomes tie at 0.25
    assert not check({"kind": "entangled", "qubits": [1, 2], "entangled": True}, probs, psi, 3)[0]
    qs = questions(bell, probs)
    assert [q["kind"] for q in qs] == ["most_likely", "probability", "entangled"] and probs[qs[1]["bits"]] > 0


def test_a_debate_counts_catches_false_alarms_and_concessions():
    from inkubit.referee import debate
    from inkubit.spec import parse_spec

    spec = parse_spec(json.loads(open(__file__.replace("tests/test_new_labs.py", "../examples/specs/bell.json").replace(
        "tests\\test_new_labs.py", "..\\examples\\specs\\bell.json"), encoding="utf-8").read()))

    class Scripted:
        def structured(self, system, user, schema, name, effort, max_tokens, model=None):
            if name == "claims":  # most likely 00 (right), P(second) = 0.3 (wrong: 0.5), entangled true (right)
                return {"claims": [{"kind": "most_likely", "bits": "00", "qubits": [], "probability": -1, "entangled": False, "statement": ""},
                                   {"kind": "probability", "bits": "", "qubits": [], "probability": 0.3, "entangled": False, "statement": ""},
                                   {"kind": "entangled", "bits": "", "qubits": [], "probability": -1, "entangled": True, "statement": ""}]}, _call(name)
            if name == "challenge":
                return {"responses": [{"agree": True, "probability": -1, "bits": "", "entangled": False, "reason": ""},
                                      {"agree": False, "probability": 0.5, "bits": "", "entangled": False, "reason": "it is 1/2"},
                                      {"agree": False, "probability": -1, "bits": "", "entangled": False, "reason": "no"}]}, _call(name)
            return {"replies": [{"stand": True, "reason": ""}, {"stand": False, "reason": "right"}, {"stand": True, "reason": "sure"}]}, _call(name)

    d = debate(spec, Scripted(), "wonder")
    assert (d.spark_first, d.caught, d.false_alarms, d.talked_out, d.final_right) == (2, 1, 1, 0, 3)


def test_referee_endpoints():
    client = TestClient(app)
    assert client.get("/api/referee/benchmark").status_code in (200, 404)
    assert client.post("/api/referee", json={"index": 0}).status_code == 409  # needs the live models


# ---------------------------------------------------------------- whole-paper reproduction

BELL_QASM = 'OPENQASM 2.0; include "qelib1.inc"; qreg q[2]; creg c[2]; h q[0]; cx q[0],q[1]; measure q -> c;'


def test_an_experiment_is_judged_or_reported_never_guessed():
    from inkubit.paper import check_experiment

    ok = check_experiment({"name": "Bell", "page": 3, "quote": "", "circuit_qasm": BELL_QASM, "shots": 1000, "hardware": "sim",
                           "bit_order": "unknown", "claims": [{"outcome": "00", "probability": 0.507, "kind": "simulated"},
                                                              {"outcome": "11", "probability": 0.493, "kind": "simulated"}]})
    assert ok.verdict == "reproduced" and len(ok.claims) == 2
    assert check_experiment({"name": "x", "page": 1, "circuit_qasm": "", "claims": []}).verdict == "no circuit"
    bad = check_experiment({"name": "x", "page": 1, "circuit_qasm": 'OPENQASM 2.0; qreg q[3]; opaque ccz a,b,c; ccz q[0],q[1],q[2];',
                            "claims": [{"outcome": "000", "probability": 1, "kind": "ideal"}]})
    assert bad.verdict == "circuit did not parse"


def test_two_passes_over_a_pdf_and_repeat_runs_count_once():
    from pypdf import PdfWriter

    from inkubit.paper import fetch_arxiv, pages_pdf, reproduce_paper

    w = PdfWriter()
    for _ in range(5):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    pdf = buf.getvalue()
    from pypdf import PdfReader

    assert len(PdfReader(io.BytesIO(pages_pdf(pdf, [2]))).pages) == 2  # page 2 and the next
    seen = []

    class Scripted:
        def structured(self, system, user, schema, name, effort, max_tokens, model=None, document=None):
            seen.append((name, model, document[1] if document else None))
            if name == "paper_experiments":
                return {"title": "T", "notes": "", "experiments": [{"name": "Bell", "pages": [2]}, {"name": "Bell again", "pages": [3]}]}, _call(name)
            return {"name": "Bell", "page": 2, "quote": "q", "circuit_qasm": BELL_QASM, "shots": 0, "hardware": "", "bit_order": "unknown",
                    "claims": [{"outcome": "00", "probability": 0.5, "kind": "ideal"}, {"outcome": "11", "probability": 0.5, "kind": "ideal"}]}, _call(name)

    r = reproduce_paper(pdf, "test", Scripted(), "wonder")
    assert seen[0] == ("paper_experiments", "wonder", "paper.pdf") and all(s[2] == "pages.pdf" for s in seen[1:])
    assert len(r.experiments) == 1 and r.reproduced == 1 and r.claims_ok == 2  # the repeat run counted once
    with pytest.raises(ValueError):
        fetch_arxiv("not an id")


def test_paper_endpoints():
    client = TestClient(app)
    assert client.get("/api/paper/examples").status_code in (200, 404)
    assert client.post("/api/paper", data={"arxiv": "nonsense"}).status_code == 422
    assert client.post("/api/paper", data={"arxiv": "1804.03719"}).status_code == 409  # needs the live models


# ---------------------------------------------------------------- the code lab

def test_the_checker_scores_textbook_codes():
    from inkubit.codes import analyse, references

    refs = {r["name"]: r for r in references()}
    assert (refs["Five-qubit perfect code"]["n"], refs["Five-qubit perfect code"]["d"]) == (5, 3)
    assert refs["Steane code"]["d"] == 3 and refs["Steane code"]["css"]
    assert refs["Shor code"]["d"] == 3 and refs["Rotated surface code, d = 3"]["d"] == 3
    rep = analyse(["ZZI", "IZZ"])  # the bit-flip repetition code: guards against X only
    assert (rep.k, rep.d, rep.dx, rep.dz) == (1, 1, 3, 1)
    assert "anticommute" in analyse(["XII", "ZII"]).note
    assert "not independent" in analyse(["ZZI", "IZZ", "ZIZ"]).note


def test_a_design_run_keeps_the_best_proven_code():
    from inkubit.codes import TARGETS, run

    class Scripted:
        def __init__(self):
            self.k = 0

        def structured(self, system, user, schema, name, effort, max_tokens, model=None):
            self.k += 1
            codes = [{"generators": ["ZZIII", "IZZII", "IIZZI", "IIIZZ"], "why": "repetition"}] if self.k == 1 else \
                [{"generators": ["XZZXI", "IXZZX", "XIXZZ", "ZXIXZ"], "why": "cyclic"}]
            return {"codes": codes}, _call(name)

    res = run(TARGETS["five"], Scripted(), rounds=2)
    assert res["curve"] == [1, 3] and res["best"]["d"] == 3


def test_codes_endpoints():
    client = TestClient(app)
    lab = client.get("/api/codes").json()
    assert len(lab["references"]) == 5
    v = client.post("/api/codes/analyse", json={"generators": ["IIIXXXX", "IXXIIXX", "XIXIXIX", "IIIZZZZ", "IZZIIZZ", "ZIZIZIZ"]}).json()
    assert v["valid"] and v["d"] == 3 and v["css"]
