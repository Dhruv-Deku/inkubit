"""Mid-circuit measurement and feed-forward: the format, its safety checks, the exact model, the code and the tools."""

from __future__ import annotations

import dataclasses
import math

import pytest
from fastapi.testclient import TestClient
from qiskit import transpile
from qiskit_aer import AerSimulator

from inkubit.adapters.mock_code import MockCodeModel
from inkubit.agent.loop import AgentOptions, run_agent
from inkubit.codegen.template import generate_code
from inkubit.sim.noise import build_noise_model, get_preset
from inkubit.sim.runner import run_code
from inkubit.spec import SpecError, parse_spec
from inkubit.verify import ideal_distribution, verify_counts
from inkubit.verify.expected import DynamicCircuitError, build_reference_circuit, noisy_distribution, physical_circuit
from inkubit.verify.metrics import total_variation_distance


def _ff(ops, n=3, nc=3, measurements=None):
    return {"kind": "circuit", "num_qubits": n, "num_clbits": nc, "operations": ops,
            "measurements": measurements if measurements is not None else [{"qubit": n - 1, "clbit": nc - 1}]}


H0 = {"gate": "H", "targets": [0]}
M0 = {"gate": "MEASURE", "targets": [0], "clbits": [0]}


def _sampled(spec, preset, shots=200_000, seed=5):
    sim = AerSimulator(noise_model=build_noise_model(preset), seed_simulator=seed)
    counts = sim.run(transpile(physical_circuit(spec), sim, optimization_level=0), shots=shots).result().get_counts()
    return {k: v / shots for k, v in counts.items()}


def _shot_floor(dist, shots):
    return sum(math.sqrt(p * (1 - p) / shots) for p in dist.values()) * math.sqrt(2 / math.pi) / 2


# ---------------------------------------------------------------- the format and its safety checks

def test_the_requested_json_shape_is_accepted():
    spec = parse_spec(_ff([H0, M0, {"gate": "x", "targets": [2], "conditional": {"classical_register": 0, "value": 1}}]))
    op = spec.operations[2]
    assert op.gate == "X" and op.conditional.classical_register == 0 and op.conditional.value == 1
    assert spec.is_dynamic()


def test_static_specs_are_unchanged(example):
    spec = parse_spec(example("teleportation"))
    assert not spec.is_dynamic()
    assert "conditional" not in spec.model_dump_json(exclude_none=True)


@pytest.mark.parametrize("ops,message", [
    ([H0, {"gate": "X", "targets": [1], "conditional": {"classical_register": 0, "value": 1}}],
     "no earlier MEASURE writes it"),
    ([H0, {"gate": "X", "targets": [1], "conditional": {"classical_register": 0, "value": 1}}, M0],
     "no earlier MEASURE writes it"),
    ([H0, M0, {"gate": "X", "targets": [1], "conditional": {"classical_register": 7, "value": 1}}], "out of range"),
    ([H0, M0, {"gate": "MEASURE", "targets": [1], "clbits": [1], "conditional": {"classical_register": 0, "value": 1}}],
     "MEASURE cannot be conditional"),
    ([H0, M0, {"gate": "RESET", "targets": [0], "conditional": {"classical_register": 0, "value": 1}}],
     "RESET cannot be conditional"),
    ([H0, M0, {"gate": "X", "targets": [1], "conditional": {"classical_register": [0, 1], "value": 1}}],
     "no earlier MEASURE writes it"),
    ([H0, M0, {"gate": "X", "targets": [1], "conditional": {"classical_register": [0, 0], "value": 1}}],
     "same classical bit twice"),
    ([H0, M0, {"gate": "MEASURE", "targets": [1], "clbits": [1]},
      {"gate": "X", "targets": [2], "conditional": {"classical_register": [0, 1], "value": 4}}], "does not fit in 2 bits"),
    ([H0, M0, {"gate": "RESET", "targets": [0], "params": [1.0]}], "RESET takes only target qubits"),
])
def test_unsafe_feed_forward_is_refused(ops, message):
    with pytest.raises(SpecError, match=message):
        parse_spec(_ff(ops))


def test_a_condition_value_must_be_a_bit():
    with pytest.raises(SpecError):
        parse_spec(_ff([H0, M0, {"gate": "X", "targets": [1], "conditional": {"classical_register": 0, "value": 2}}]))


def test_the_record_qubit_budget_is_enforced():
    ops = [{"gate": "H", "targets": [q]} for q in range(6)]
    ops += [{"gate": "MEASURE", "targets": [q], "clbits": [q]} for q in range(5)]
    ops.append({"gate": "X", "targets": [5], "conditional": {"classical_register": 0, "value": 1}})
    with pytest.raises(SpecError, match="above the limit of 10"):
        parse_spec(_ff(ops, n=6, nc=6, measurements=[{"qubit": 5, "clbit": 5}]))


# ---------------------------------------------------------------- the exact model

def test_feed_forward_teleportation_matches_the_deferred_version(example):
    ff = ideal_distribution(parse_spec(example("teleportation_feedforward")))
    deferred = ideal_distribution(parse_spec(example("teleportation")))
    c2 = {"0": 0.0, "1": 0.0}
    for key, p in ff.items():
        c2[key[0]] += p
    assert c2 == pytest.approx(deferred, abs=1e-12)


@pytest.mark.parametrize("preset_name", ["ideal", "realistic", "calibrated"])
def test_the_exact_prediction_matches_a_large_sample_of_the_real_if_test_circuit(example, preset_name):
    spec = parse_spec(example("teleportation_feedforward"))
    exact = noisy_distribution(spec, preset_name)
    sampled = _sampled(spec, get_preset(preset_name))
    assert total_variation_distance(exact, sampled) < 3 * _shot_floor(exact, 200_000)


def test_heavy_noise_conditional_two_qubit_gates_and_value_zero_conditions():
    spec = parse_spec(_ff([
        {"gate": "RY", "targets": [0], "params": [1.3]}, {"gate": "H", "targets": [1]}, M0,
        {"gate": "CX", "controls": [1], "targets": [2], "conditional": {"classical_register": 0, "value": 1}},
        {"gate": "RX", "targets": [3], "params": [0.9], "conditional": {"classical_register": 0, "value": 0}},
        {"gate": "MEASURE", "targets": [1], "clbits": [1]},
        {"gate": "CZ", "controls": [2], "targets": [3], "conditional": {"classical_register": 1, "value": 0}},
        {"gate": "X", "targets": [2, 3], "conditional": {"classical_register": 1, "value": 1}},
    ], n=4, nc=4, measurements=[{"qubit": 2, "clbit": 2}, {"qubit": 3, "clbit": 3}]))
    stress = dataclasses.replace(get_preset("realistic"), name="stress", label="stress",
                                 p1=0.06, p2=0.12, readout_p01=0.07, readout_p10=0.1)
    exact = noisy_distribution(spec, stress)
    sampled = _sampled(spec, stress)
    assert total_variation_distance(exact, sampled) < 3 * _shot_floor(exact, 200_000)
    # and the noise matters: the noiseless prediction is far off, so the agreement above is not luck
    assert total_variation_distance(noisy_distribution(spec, "ideal"), sampled) > 0.1


# ---------------------------------------------------------------- the generated code and the agent

def test_generated_code_uses_if_test_and_verifies_under_noise(example):
    spec = parse_spec(example("teleportation_feedforward"))
    code = generate_code(spec, noise="realistic")
    assert "with qc.if_test((qc.clbits[1], 1)):" in code and "        qc.x(2)" in code
    assert "c_if" not in code
    run = run_code(code)
    assert run.ok, run.stderr
    verdict = verify_counts(spec, run.counts, "realistic")
    assert verdict.passed, verdict.reason


@pytest.mark.parametrize("fault", ["auto", "missing_cnot", "swapped_control_target", "missing_measurement"])
def test_the_agent_catches_and_repairs_a_planted_bug_in_feed_forward_code(example, fault):
    result = run_agent(parse_spec(example("teleportation_feedforward")), MockCodeModel(),
                       AgentOptions(noise="realistic", demo_fault=fault))
    assert result.verified and len(result.attempts) >= 2
    assert "if_test" in result.final_code


def test_planted_bugs_never_land_inside_an_if_test_block(example):
    from inkubit.agent.faults import inject

    spec = parse_spec(example("teleportation_feedforward"))
    code = generate_code(spec, noise="realistic")
    broken, _ = inject(code, spec, "wrong_qubit_index")
    inner = [ln for ln in broken.splitlines() if ln.startswith(" " * 8 + "qc.")]
    assert inner == [ln for ln in code.splitlines() if ln.startswith(" " * 8 + "qc.")]


def test_the_code_model_hears_about_feed_forward_only_when_the_circuit_uses_it(example):
    from inkubit.adapters.meta_code import _spec_block
    from inkubit.adapters.prompts import FEED_FORWARD_NOTE

    assert FEED_FORWARD_NOTE in _spec_block(parse_spec(example("teleportation_feedforward")), "realistic")
    assert FEED_FORWARD_NOTE not in _spec_block(parse_spec(example("teleportation")), "realistic")


# ---------------------------------------------------------------- the rest of the app

def test_the_physical_circuit_measures_mid_circuit_and_branches(example):
    qc = physical_circuit(parse_spec(example("teleportation_feedforward")))
    ops = qc.count_ops()
    assert ops["if_else"] == 2 and ops["measure"] == 3


def test_single_state_tools_refuse_in_words(example):
    from inkubit.api.app import app

    spec = example("teleportation_feedforward")
    with pytest.raises(DynamicCircuitError):
        build_reference_circuit(parse_spec(spec))
    client = TestClient(app)
    for path, body in (("/api/state", {"spec": spec, "noise": "realistic"}),
                       ("/api/insights", {"spec": spec, "noise": "realistic"}),
                       ("/api/optimize", {"spec": spec, "ai": False})):
        r = client.post(path, json=body)
        assert r.status_code == 422, (path, r.text)
        assert "feed-forward" in r.json()["detail"], path


def test_a_feed_forward_job_runs_verifies_and_draws(example):
    from inkubit.api.jobs import JobStore, RunOptions

    store = JobStore(workers=1)
    job = store.submit(parse_spec(example("teleportation_feedforward")),
                       RunOptions(noise="realistic", explain=True, diagram=False, insights=True))
    import time

    for _ in range(600):
        if job.status in ("done", "failed"):
            break
        time.sleep(0.1)
    assert job.status == "done" and job.result["verified"]
    assert job.result["exact_diagram"]["image_b64"]
    assert job.result.get("insights") is None


# ---------------------------------------------------------------- reuse, reset and conditions on several bits

def test_what_counts_as_feed_forward():
    terminal = parse_spec(_ff([H0, M0], n=1, nc=1, measurements=[]))
    assert not terminal.is_dynamic()  # a MEASURE at the end is an ordinary terminal measurement
    other = parse_spec(_ff([H0, M0, {"gate": "H", "targets": [1]}], n=2, nc=2, measurements=[{"qubit": 1, "clbit": 1}]))
    assert not other.is_dynamic()  # later gates on other qubits do not depend on it
    for extra in ({"gate": "H", "targets": [0]}, {"gate": "RESET", "targets": [0]},
                  {"gate": "MEASURE", "targets": [0], "clbits": [1]}):
        assert parse_spec(_ff([H0, M0, extra], n=1, nc=2, measurements=[])).is_dynamic()


def test_a_reused_qubit_measured_twice_gives_two_independent_coins():
    spec = parse_spec(_ff([H0, M0, H0, {"gate": "MEASURE", "targets": [0], "clbits": [1]}], n=1, nc=2, measurements=[]))
    assert ideal_distribution(spec) == pytest.approx({"00": 0.25, "01": 0.25, "10": 0.25, "11": 0.25})


def test_reset_forgets_the_state_and_starts_from_zero():
    spec = parse_spec(_ff([{"gate": "X", "targets": [0]}, {"gate": "CX", "controls": [0], "targets": [1]},
                           {"gate": "RESET", "targets": [0]}],
                          n=2, nc=2, measurements=[{"qubit": 0, "clbit": 0}, {"qubit": 1, "clbit": 1}]))
    assert ideal_distribution(spec) == pytest.approx({"10": 1.0})  # q0 back to 0, its partner untouched


def test_a_condition_on_two_bits_reads_the_first_listed_bit_lowest():
    ops = [{"gate": "X", "targets": [0]}, {"gate": "MEASURE", "targets": [0, 1], "clbits": [0, 1]},
           {"gate": "X", "targets": [2], "conditional": {"classical_register": [0, 1], "value": 1}}]
    assert ideal_distribution(parse_spec(_ff(ops))) == pytest.approx({"101": 1.0})  # c0 = 1, c1 = 0: fires
    ops[2]["conditional"]["value"] = 2
    assert ideal_distribution(parse_spec(_ff(ops))) == pytest.approx({"001": 1.0})  # wants c1 = 1: stays quiet


@pytest.mark.parametrize("name", ["bit_flip_feedforward", "active_reset"])
def test_reuse_reset_and_two_bit_conditions_match_a_large_sample_under_heavy_noise(example, name):
    spec = parse_spec(example(name))
    stress = dataclasses.replace(get_preset("realistic"), name="stress", label="stress",
                                 p1=0.06, p2=0.12, readout_p01=0.07, readout_p10=0.1)
    exact = noisy_distribution(spec, stress)
    sampled = _sampled(spec, stress)
    assert total_variation_distance(exact, sampled) < 3 * _shot_floor(exact, 200_000)


def test_the_error_correction_cycle_code_nests_if_test_resets_and_verifies(example):
    spec = parse_spec(example("bit_flip_feedforward"))
    code = generate_code(spec, noise="realistic")
    assert "qc.reset(3)" in code
    assert "with qc.if_test((qc.clbits[0], 1)):  # op 12: only when c0 reads 1 and c1 reads 1" in code
    assert "        with qc.if_test((qc.clbits[1], 1)):" in code and "            qc.x(1)" in code
    run = run_code(code)
    assert run.ok, run.stderr
    verdict = verify_counts(spec, run.counts, "realistic")
    assert verdict.passed, verdict.reason
    qc = physical_circuit(spec)
    assert qc.count_ops()["reset"] == 1 and qc.count_ops()["if_else"] == 3


@pytest.mark.parametrize("fault", ["auto", "missing_measurement"])
def test_the_agent_repairs_a_planted_bug_in_the_error_correction_cycle(example, fault):
    result = run_agent(parse_spec(example("bit_flip_feedforward")), MockCodeModel(),
                       AgentOptions(noise="realistic", demo_fault=fault))
    assert result.verified and len(result.attempts) >= 2
    assert "qc.reset(3)" in result.final_code


# ---------------------------------------------------------------- descriptions

@pytest.mark.parametrize("text,name", [
    ("teleportation with feed-forward", "teleportation_feedforward"),
    ("bit-flip error correction with a measured syndrome", "bit_flip_feedforward"),
    ("an active reset on one qubit", "active_reset"),
])
def test_offline_descriptions_reach_the_feed_forward_circuits(example, text, name):
    from inkubit.textspec import parse_description

    spec, _ = parse_description(text)
    assert spec["operations"] == example(name)["operations"]


def test_a_text_draft_carries_mid_circuit_measurements_and_conditions_but_the_sketch_draft_does_not():
    from inkubit.spec.draft import draft_schema, draft_to_spec

    blank = {"controls": [], "params": [], "segment_id": "", "box": []}
    draft = {"title": "t", "num_qubits": 3, "num_clbits": 3, "notes": "",
             "measurements": [{"qubit": 2, "clbit": 2, "segment_id": ""}],
             "operations": [{"gate": "H", "targets": [0], "clbits": [], "condition_bits": [], "condition_value": 0, **blank},
                            {"gate": "MEASURE", "targets": [0, 1], "clbits": [0, 1], "condition_bits": [], "condition_value": 0, **blank},
                            {"gate": "X", "targets": [2], "clbits": [], "condition_bits": [0, 1], "condition_value": 3, **blank}]}
    spec = parse_spec(draft_to_spec("circuit", draft, []))
    assert spec.operations[1].gate == "MEASURE" and spec.operations[1].clbits == [0, 1]
    assert spec.operations[2].conditional.pairs() == [(0, 1), (1, 1)]
    assert "condition_bits" in str(draft_schema("circuit", text=True))
    assert "condition_bits" not in str(draft_schema("circuit"))  # sketch readings (and their cache) are unchanged


@pytest.mark.live
def test_muse_spark_writes_feed_forward_from_a_description():
    from inkubit.adapters.registry import get_models

    draft = get_models().reasoning.spec_from_text(
        "Teleport RY(pi/3)|0> from q0 to q2 with real feed-forward: measure q0 and q1 halfway, then apply X to q2 if c1 "
        "reads 1 and Z to q2 if c0 reads 1, and measure q2 into c2.")
    spec = parse_spec(draft.spec)
    assert spec.is_dynamic()
    c2_one = sum(p for k, p in ideal_distribution(spec).items() if k[0] == "1")
    assert c2_one == pytest.approx(math.sin(math.pi / 6) ** 2)
