"""Quantum Rosetta: Dirac notation both ways, exact readers, proven state preparation, eight languages."""

import json
import math
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from qiskit.quantum_info import random_statevector

from inkubit.adapters.config import load_settings
from inkubit.adapters.meta_vision import MetaReasoningModel
from inkubit.api.app import app
from inkubit.copilot import ask_offline, run_tool
from inkubit.insights.circuit import step_states
from inkubit.notation import NotationError, dirac, parse_ket, scalar
from inkubit.rosetta import (ReadError, detect, dictionary, languages, prepare, read_qasm, read_qiskit, read_quil,
                             statevector, translate)
from inkubit.spec import parse_spec

S = 1 / math.sqrt(2)


@pytest.mark.parametrize("text, written", [
    ("(|00⟩ + |11⟩)/√2", "1/√2 (|00⟩ + |11⟩)"),
    ("(|01> - |10>)/sqrt(2)", "1/√2 (|01⟩ − |10⟩)"),
    ("|0⟩|+⟩", "|0+⟩"),
    ("|+⟩ ⊗ (|00⟩+|11⟩)/√2", "|+⟩ ⊗ 1/√2 (|00⟩ + |11⟩)"),
    ("(|001⟩ + |010⟩ + |100⟩)/√3", "1/√3 (|001⟩ + |010⟩ + |100⟩)"),
    ("0.6|0> + 0.8i|1>", "3/5|0⟩ + (4/5)i|1⟩"),
    ("√3/2|0⟩ + 1/2|1⟩", "√3/2|0⟩ + 1/2|1⟩"),
    ("(|0⟩ + e^{iπ/4}|1⟩)/√2", "1/√2 (|0⟩ + e^(iπ/4)|1⟩)"),
    (r"\frac{1}{\sqrt{2}}\left(|00\rangle + i|11\rangle\right)", "1/√2 (|00⟩ + i|11⟩)"),
    ("|ψ⟩ = |Φ+⟩", "1/√2 (|00⟩ + |11⟩)"),
    ("|+++⟩", "|+++⟩"),
])
def test_dirac_round_trip(text, written):
    v, _ = parse_ket(text)
    assert dirac(v).text == written
    assert abs(np.vdot(parse_ket(written)[0], v)) ** 2 > 1 - 1e-12  # what we write reads back as the same state


def test_factoring_names_entangled_groups_and_is_checked():
    v, _ = parse_ket("(|00⟩ + |11⟩)/√2 ⊗ (|01⟩ − |10⟩)/√2")
    form = dirac(v)
    assert form.groups == [[3, 2], [1, 0]] and not form.product and "⊗" in form.text
    assert dirac(parse_ket("|+⟩|−⟩")[0]).product


def test_normalisation_is_reported():
    v, norm = parse_ket("|0⟩ + |1⟩")
    assert abs(norm - math.sqrt(2)) < 1e-12 and abs(np.linalg.norm(v) - 1) < 1e-12
    assert "normalised" in translate("|0⟩ + |1⟩").source.note


@pytest.mark.parametrize("bad, says", [
    ("|ψ⟩", "is a name"), ("|0⟩ + 1", "every term needs a ket"), ("theta|0>", "don't know the symbol"),
    ("|0⟩ - |0⟩", "cancel to zero"), ("|00⟩+|1⟩", "2-qubit ket to a 1-qubit"), ("2+3", "not a state"),
])
def test_bad_kets_say_why(bad, says):
    with pytest.raises(NotationError, match=says):
        parse_ket(bad)


def test_scalars():
    assert scalar("-np.pi/2") == pytest.approx(-math.pi / 2) and scalar("2*π/3") == pytest.approx(2 * math.pi / 3)


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_any_state_gets_a_circuit_that_makes_it_exactly(n):
    for seed in range(3):
        v = random_statevector(2 ** n, seed=seed + 10 * n).data
        ops, prep = prepare(v, n)
        assert prep.fidelity > 1 - 1e-8


@pytest.mark.parametrize("ket, two_qubit, max_gates", [
    ("(|0000⟩ + |1111⟩)/√2", 3, 4),  # GHZ fan-out
    ("|+−1⟩", 0, 4),  # product: no entangling gate
    ("(|00⟩+|01⟩+|10⟩-|11⟩)/2", 1, 3),  # graph state: H, H, CZ found by search
    ("(|01⟩ − |10⟩)/√2", 1, 4),
])
def test_textbook_states_get_short_circuits(ket, two_qubit, max_gates):
    v, _ = parse_ket(ket)
    _, prep = prepare(v, int(math.log2(len(v))))
    assert prep.two_qubit == two_qubit and prep.gates <= max_gates and prep.fidelity > 1 - 1e-9


def test_detect():
    assert detect("OPENQASM 2.0; qreg q[1]; h q[0];") == "qasm"
    assert detect("qc.h(0)\nqc.cx(0, 1)") == "qiskit"
    assert detect("H 0\nCNOT 0 1") == "quil"
    assert detect("(|0⟩+|1⟩)/√2") == "dirac"
    assert detect("import cirq\nq = cirq.LineQubit.range(2)") == "code"
    assert detect("from braket.circuits import Circuit\ncircuit = Circuit().rx(0, 1.0)") == "code"
    assert detect("a GHZ state on 4 qubits") == "words"


BELL = np.array([S, 0, 0, S])


def test_exact_readers_agree():
    qasm2_spec, label = read_qasm('OPENQASM 2.0;\nqreg q[2];\nh q[0];\ncx q[0],q[1];')
    assert label == "OpenQASM 2"
    qasm3_spec, label = read_qasm('OPENQASM 3.0;\ninclude "stdgates.inc";\nqubit[2] q;\nh q[0];\ncx q[0], q[1];')
    assert label == "OpenQASM 3"
    quil_spec, _ = read_quil("DECLARE ro BIT[2]\nH 0\nCNOT 0 1\nMEASURE 0 ro[0]\nMEASURE 1 ro[1]")
    qk_spec, _ = read_qiskit("qc = QuantumCircuit(2, 2)\nqc.h(0)\nqc.cx(0, 1)\nqc.measure([0, 1], [0, 1])")
    for spec in (qasm2_spec, qasm3_spec, quil_spec, qk_spec):
        assert abs(np.vdot(statevector(spec), BELL)) ** 2 > 1 - 1e-12
        assert spec.measured_pairs()  # a program that measures nothing gets every qubit measured
    rot, _ = read_qiskit("qc.rz(np.pi/4, 1)\nqc.cp(pi/2, 0, 1)\nqc.h([0, 1])")
    assert [o.gate for o in rot.operations if o.gate != "MEASURE"] == ["RZ", "CP", "H"]
    assert rot.operations[0].params[0] == pytest.approx(math.pi / 4)


def test_reader_errors():
    with pytest.raises(ReadError, match="did not parse"):
        read_qasm("OPENQASM 2.0;\nqreg q[2];\nfoo q[0];")
    with pytest.raises(ReadError, match="Quil line"):
        read_quil("H 0\nwhat is this")
    offline = SimpleNamespace(settings=SimpleNamespace(provider="mock", has_key=False), reasoning=None)
    with pytest.raises(ReadError, match="live model"):
        translate("import cirq\nq = cirq.LineQubit.range(2)", offline)


GHZ = {"kind": "circuit", "version": "1.0", "num_qubits": 3, "num_clbits": 3, "metadata": {"title": "t"},
       "operations": [{"gate": "H", "targets": [0]}, {"gate": "CX", "controls": [0], "targets": [1]},
                      {"gate": "CP", "controls": [1], "targets": [2], "params": [math.pi / 4]},
                      {"gate": "SX", "targets": [2]}, {"gate": "SDG", "targets": [1]},
                      {"gate": "CCX", "controls": [0, 1], "targets": [2]}, {"gate": "RY", "targets": [0], "params": [0.3]},
                      {"gate": "SWAP", "targets": [0, 2]}, {"gate": "CZ", "controls": [2], "targets": [0]}],
       "measurements": [{"qubit": q, "clbit": q} for q in range(3)]}


def test_languages_run_and_match_where_they_can():
    spec = parse_spec(GHZ)
    langs = {lang.id: lang for lang in languages(spec)}  # type: ignore[arg-type]
    assert list(langs) == ["qiskit", "qasm2", "qasm3", "cirq", "pennylane", "qsharp", "quil", "braket"]
    assert langs["qiskit"].checked and langs["qasm2"].checked and langs["qasm3"].checked
    pytest.importorskip("cirq")
    assert langs["cirq"].checked, langs["cirq"].note
    assert "Controlled R1" in langs["qsharp"].code and "qml.ControlledPhaseShift" in langs["pennylane"].code
    assert "CPHASE(pi/4) 1 2" in langs["quil"].code and "circuit.v(2)" in langs["braket"].code
    assert "same state" in langs["quil"].note  # read back by our own Quil reader


def test_narration_follows_the_exact_state():
    steps = translate("qc.h(0)\nqc.cx(0, 1)\nqc.z(0)\nqc.cx(1, 0)").steps
    effects = [s.effect for s in steps[1:]]
    assert "superposition of 2" in effects[0] and "Entangles q1 and q0" in effects[1]
    assert "only phases" in effects[2]
    assert steps[2].dirac == "1/√2 (|00⟩ + |11⟩)"
    idle = translate("qc.cx(0, 1)").steps[1].effect
    assert "control is never 1" in idle


def test_dictionary_examples_all_translate():
    entries = dictionary()
    assert len(entries) >= 25 and all(e["dirac"] for e in entries)
    by = {e["term"]: e for e in entries}
    assert by["Entanglement"]["dirac"] == "1/√2 (|00⟩ + |11⟩)" and by["Entanglement"]["entangled"]
    assert by["Interference"]["dirac"] == "|1⟩"


def test_step_states_carry_dirac():
    spec = parse_spec(json.loads((__import__("inkubit").PROJECT_DIR / "examples/specs/ghz3.json").read_text()))
    assert [s.dirac for s in step_states(spec)][-1] == "1/√2 (|000⟩ + |111⟩)"  # type: ignore[arg-type]


def test_endpoints():
    c = TestClient(app)
    r = c.post("/api/rosetta", json={"text": "(|01⟩ − |10⟩)/√2"})
    body = r.json()
    assert r.status_code == 200 and body["state"]["text"] == "1/√2 (|01⟩ − |10⟩)" and body["preparation"]["fidelity"] > 0.999999
    assert c.post("/api/rosetta", json={"text": "|0⟩ + 1"}).status_code == 422
    assert len(c.get("/api/rosetta/dictionary").json()["entries"]) >= 25


def test_copilot_tool_and_offline_router():
    run = run_tool("translate_notation", {"text": "(|000⟩+|111⟩)/√2"})
    assert run.error is None and run.facts["two_qubit_gates"] == 2 and run.facts["entangled_groups"] == [[2, 1, 0]]
    assert run.card and run.card["type"] == "rosetta"
    rep = ask_offline("What circuit makes (|01⟩ − |10⟩)/√2 ?")
    assert rep.tools[0].name == "translate_notation" and rep.tools[0].args["text"] == "(|01⟩ − |10⟩)/√2"
    assert not rep.trace.untraced


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def chat(self, model, messages, **kw):
        self.calls.append((messages, kw))
        return self.reply, False


def test_photo_reader_asks_for_a_transcription_not_a_solution():
    fake = FakeClient(json.dumps({"kind": "dirac", "text": "(|01⟩ − |10⟩)/√2", "notes": ""}))
    read = MetaReasoningModel(load_settings(), fake).read_notation(b"\x89PNG", "image/png")  # type: ignore[arg-type]
    assert read.text == "(|01⟩ − |10⟩)/√2" and read.call.role == "read notation"
    messages, kw = fake.calls[0]
    assert kw["schema_name"] == "notation" and "do not solve" in messages[0]["content"]
    assert messages[1]["content"][1]["type"] == "image_url"
