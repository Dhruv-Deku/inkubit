"""New gates (SDG, TDG, SX, CP, CCX) and the algorithm gallery."""

from __future__ import annotations

import math

import pytest

from qcanvas.adapters.mock_code import MockCodeModel
from qcanvas.agent.loop import AgentOptions, run_agent
from qcanvas.codegen.template import generate_code
from qcanvas.sim.runner import run_code
from qcanvas.spec import SpecError, parse_spec
from qcanvas.verify import ideal_distribution, verify_counts

GALLERY = {
    "grover2": {"11": 1.0},
    "bernstein_vazirani": {"101": 1.0},
    "deutsch_jozsa": {"11": 1.0},
    "phase_estimation": {"001": 1.0},
    "superdense": {"11": 1.0},
    "toffoli_and": {"000": 0.25, "001": 0.25, "010": 0.25, "111": 0.25},
    "teleportation": {"0": 0.25, "1": 0.75},
    "w_state": {"001": 1 / 3, "010": 1 / 3, "100": 1 / 3},
}


@pytest.mark.parametrize("name,answer", GALLERY.items())
def test_gallery_algorithms_give_the_textbook_answer(example, name, answer):
    assert ideal_distribution(parse_spec(example(name))) == pytest.approx(answer, abs=1e-9)


def _circuit(ops, n=3):
    return {"kind": "circuit", "num_qubits": n, "num_clbits": n, "operations": ops,
            "measurements": [{"qubit": q, "clbit": q} for q in range(n)]}


def test_aliases_and_new_gate_validation():
    spec = parse_spec(_circuit([{"gate": "toffoli", "controls": [0, 1], "targets": [2]},
                                {"gate": "√X", "targets": [0]}, {"gate": "sdag", "targets": [1]}]))
    assert [op.gate for op in spec.operations] == ["CCX", "SX", "SDG"]
    with pytest.raises(SpecError, match="two controls of CCX must be different"):
        parse_spec(_circuit([{"gate": "CCX", "controls": [0, 0], "targets": [2]}]))
    with pytest.raises(SpecError, match="CP needs 1 angle parameter"):
        parse_spec(_circuit([{"gate": "CP", "controls": [0], "targets": [1]}]))


def test_one_qubit_phase_gates_match_their_definitions():
    # SX twice is X; S then SDG and T then TDG cancel.
    spec = parse_spec(_circuit([{"gate": "SX", "targets": [0]}, {"gate": "SX", "targets": [0]},
                                {"gate": "H", "targets": [1]}, {"gate": "S", "targets": [1]},
                                {"gate": "SDG", "targets": [1]}, {"gate": "T", "targets": [1]},
                                {"gate": "TDG", "targets": [1]}, {"gate": "H", "targets": [1]}]))
    assert ideal_distribution(spec) == pytest.approx({"001": 1.0})


@pytest.mark.parametrize("name", ["toffoli_and", "phase_estimation"])
def test_new_gate_code_verifies_under_realistic_noise(example, name):
    spec = parse_spec(example(name))
    code = generate_code(spec, noise="realistic")
    if name == "toffoli_and":
        assert "three_qubit" in code and "qc.ccx(0, 1, 2)" in code
    else:
        assert "qc.cp(pi / 4, 0, 3)" in code and "three_qubit" not in code
    run = run_code(code)
    assert run.ok, run.stderr
    verdict = verify_counts(spec, run.counts, "realistic")
    assert verdict.passed, verdict.reason


def test_planted_fault_is_repaired_in_a_controlled_phase_circuit(example):
    result = run_agent(parse_spec(example("phase_estimation")), MockCodeModel(),
                       AgentOptions(noise="low_noise", demo_fault="wrong_qubit_index"))
    assert result.verified and len(result.attempts) == 2


def test_toffoli_noise_is_six_cnots_worth():
    from qcanvas.sim.noise import get_preset, toffoli_error

    p2 = get_preset("realistic").p2
    assert toffoli_error(get_preset("realistic")) == pytest.approx(1 - (1 - p2) ** 6)
    assert math.isclose(toffoli_error(get_preset("ideal")), 0.0)
