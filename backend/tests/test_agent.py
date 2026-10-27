"""P4: the self-checking agent loop, fault injection and the rule-based repairer."""

from __future__ import annotations

import pytest

from qcanvas.adapters.base import CodeModel, CodeResult, ModelCall, RepairRequest, RepairResult
from qcanvas.adapters.mock_code import MockCodeModel
from qcanvas.agent import FAULTS, AgentOptions, EventBus, run_agent
from qcanvas.agent.codeparse import extract_calls
from qcanvas.agent.faults import inject, pick_demo_fault
from qcanvas.agent.repair_rules import align_with_spec
from qcanvas.codegen.template import generate_code
from qcanvas.spec import parse_spec

pytestmark = pytest.mark.slow


def test_clean_pass_on_first_attempt(example):
    bus = EventBus()
    result = run_agent(parse_spec(example("ghz3")), MockCodeModel(), AgentOptions(noise="realistic"), bus)
    assert result.verified and len(result.attempts) == 1
    steps = [e.step for e in bus.events()]
    assert steps[0] == "plan" and steps[-1] == "done"
    assert {"generate", "run", "verify"} <= set(steps)
    assert [e.seq for e in bus.events()] == list(range(len(steps)))
    assert result.verdict.passed and result.counts


@pytest.mark.parametrize("fault", ["wrong_import", "missing_measurement", "wrong_qubit_index",
                                   "swapped_control_target", "missing_cnot"])
def test_every_injected_fault_is_repaired(example, fault):
    bus = EventBus()
    result = run_agent(parse_spec(example("bell")), MockCodeModel(),
                       AgentOptions(noise="realistic", demo_fault=fault), bus)
    assert result.verified, result.summary
    assert len(result.attempts) == 2
    first = result.attempts[0]
    assert not first.passed and first.diagnosis and first.fix_summary
    assert result.attempts[1].diff_from_previous.startswith("--- attempt 1")
    messages = " ".join(e.message for e in bus.events())
    assert "Attempt 1 failed:" in messages and "Repairing" in messages
    assert result.fault["name"] == fault


def test_missing_cnot_log_reads_well(example):
    bus = EventBus()
    run_agent(parse_spec(example("bell")), MockCodeModel(), AgentOptions(demo_fault="missing_cnot"), bus)
    diag = next(e for e in bus.events() if e.step == "diagnose")
    assert diag.message.startswith("Attempt 1 failed: expected ~50% |00⟩ and 50% |11⟩, got")
    assert "entangling gate looks missing" in diag.message


def test_ghz_faults_are_repaired(example):
    for fault in ("swapped_control_target", "wrong_qubit_index"):
        result = run_agent(parse_spec(example("ghz3")), MockCodeModel(), AgentOptions(demo_fault=fault))
        assert result.verified, (fault, result.summary)


def test_unrepairable_fault_ends_in_honest_failure(example):
    bus = EventBus()
    result = run_agent(parse_spec(example("bell")), MockCodeModel(), AgentOptions(demo_fault="fake_result"), bus)
    assert not result.verified and result.status == "failed"
    assert "NOT verified" in result.summary
    assert result.verdict is not None and not result.verdict.passed
    assert bus.events()[-1].status == "fail"
    assert any(e.step == "repair" and e.status == "fail" for e in bus.events())


class _AlwaysWrongRepairer(CodeModel):
    """Changes the code every time but never fixes it."""

    def __init__(self) -> None:
        self.repairs = 0

    def generate(self, spec, noise, shots, seed):
        return MockCodeModel().generate(spec, noise, shots, seed)

    def repair(self, request: RepairRequest) -> RepairResult:
        self.repairs += 1
        code = request.code + f"\n# attempt {self.repairs}: still wrong\n"
        return RepairResult(code=code, diagnosis="guess", fix_summary="tweaked a comment", changed=True,
                            call=ModelCall(provider="mock", model="stub", role="repair code"))


def test_stops_after_max_attempts(example):
    repairer = _AlwaysWrongRepairer()
    result = run_agent(parse_spec(example("bell")), repairer,
                       AgentOptions(noise="ideal", demo_fault="missing_cnot", max_attempts=3))
    assert not result.verified and len(result.attempts) == 3 and repairer.repairs == 2


def test_pick_demo_fault(example):
    bell = parse_spec(example("bell"))
    sup = parse_spec(example("superposition"))
    assert pick_demo_fault(generate_code(bell), bell).name == "missing_cnot"
    assert pick_demo_fault(generate_code(sup), sup).name == "wrong_qubit_index"
    with pytest.raises(ValueError, match="does not apply"):
        inject(generate_code(sup), sup, "missing_cnot")


@pytest.mark.parametrize("name", sorted(FAULTS))
def test_faults_change_the_code(example, name):
    spec = parse_spec(example("ghz3"))
    code = generate_code(spec, "realistic")
    broken, _ = inject(code, spec, name)
    assert broken != code


def test_align_removes_extra_gate(example):
    spec = parse_spec(example("bell"))
    code = generate_code(spec).replace("    return qc", "    qc.x(1)\n    return qc", 1)
    fixed, changes = align_with_spec(code, spec, "ideal")
    assert any("removed qc.x(1)" in c for c in changes)
    assert [c.key for c in extract_calls(fixed)] == [c.key for c in extract_calls(generate_code(spec))]


def test_repair_keeps_the_scripts_variable_name(example):
    spec = parse_spec(example("bell"))
    code = generate_code(spec).replace("qc", "circuit")
    broken, _ = inject(code, spec, "missing_cnot")
    fixed, changes = align_with_spec(broken, spec, "ideal")
    assert changes and "circuit.cx(0, 1)" in fixed and "qc." not in fixed


def test_demo_mode_without_a_plantable_fault_runs_as_written(example):
    spec = parse_spec(example("superposition"))
    bus = EventBus()
    result = run_agent(spec, MockCodeModel(), AgentOptions(noise="ideal", demo_fault="missing_cnot"), bus)
    assert result.verified and result.fault is None
    assert any(e.step == "inject" and "no fault planted" in e.message for e in bus.events())
