"""Offline CodeModel: template codegen plus the rule-based repairer."""

from __future__ import annotations

from qcanvas.adapters.base import CodeModel, CodeResult, ModelCall, RepairRequest, RepairResult
from qcanvas.agent.repair_rules import rule_based_repair
from qcanvas.codegen.template import generate_code
from qcanvas.spec.models import CircuitSpec

MOCK_CODE_MODEL = "template-codegen + rule-based repairer"


class MockCodeModel(CodeModel):
    """Deterministic stand-in for the Muse Spark code model."""

    def generate(self, spec: CircuitSpec, noise: str, shots: int, seed: int) -> CodeResult:
        code = generate_code(spec, noise=noise, shots=shots, seed=seed)
        return CodeResult(code=code, call=ModelCall(provider="mock", model="template-codegen", role="write code"),
                          notes="Deterministic template.")

    def repair(self, request: RepairRequest) -> RepairResult:
        code, changes = rule_based_repair(request.code, request.spec, request.noise, request.diagnosis_category)
        call = ModelCall(provider="mock", model="rule-based repairer", role="repair code")
        if not changes:
            return RepairResult(code=request.code, changed=False, call=call,
                                diagnosis=f"No repair rule covers this failure ({request.diagnosis_category}).",
                                fix_summary="")
        return RepairResult(code=code, changed=True, call=call, diagnosis=request.diagnosis,
                            fix_summary="; ".join(changes))
