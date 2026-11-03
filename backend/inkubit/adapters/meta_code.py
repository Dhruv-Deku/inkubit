"""CodeModel backed by Muse Spark on Meta Model API (Chat Completions + structured output)."""

from __future__ import annotations

import json
import time

from inkubit.adapters.base import CodeModel, CodeResult, ModelCall, RepairRequest, RepairResult
from inkubit.adapters.config import Settings
from inkubit.adapters.meta_client import MetaAPIError, MetaClient
from inkubit.adapters.prompts import CODE_CONTRACT, GENERATE_SYSTEM, REPAIR_SYSTEM
from inkubit.sim.noise import get_preset
from inkubit.spec.models import CircuitSpec

_CODE_SCHEMA = {
    "type": "object",
    "properties": {"notes": {"type": "string"}, "code": {"type": "string"}},
    "required": ["notes", "code"],
    "additionalProperties": False,
}

_REPAIR_SCHEMA = {
    "type": "object",
    "properties": {
        "diagnosis": {"type": "string", "description": "Root cause in one or two sentences."},
        "fix_summary": {"type": "string", "description": "What you changed, in one sentence."},
        "code": {"type": "string", "description": "The complete fixed script."},
    },
    "required": ["diagnosis", "fix_summary", "code"],
    "additionalProperties": False,
}


def _strip_fences(code: str) -> str:
    code = code.strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[1] if "\n" in code else ""
        if code.rstrip().endswith("```"):
            code = code.rstrip()[:-3]
    return code.strip() + "\n"


def _spec_block(spec: CircuitSpec, noise: str, shots: int | None = None, seed: int | None = None) -> str:
    preset = get_preset(noise).as_dict()
    parts = [f"Spec:\n{spec.model_dump_json(indent=2, exclude_none=True)}",
             f"Noise preset '{noise}' parameters (times in microseconds):\n{json.dumps(preset)}"]
    if shots is not None:
        parts.append(f"SHOTS = {shots}, SEED = {seed}")
    return "\n\n".join(parts)


class MetaCodeModel(CodeModel):
    """Writes and repairs code with a Muse model (default ``muse-spark-1.3``)."""

    def __init__(self, settings: Settings, client: MetaClient | None = None):
        self.settings = settings
        self.model = settings.code_model
        self.client = client or MetaClient(settings)

    def _call(self, role: str, system: str, user: str, schema: dict, name: str) -> tuple[dict, ModelCall]:
        start = time.perf_counter()
        content, cached = self.client.chat(
            self.model,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            schema=schema, schema_name=name, reasoning_effort="medium", max_tokens=16000,
        )
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            raise MetaAPIError(f"{self.model} returned text that is not JSON") from None
        call = ModelCall(provider="meta", model=self.model, role=role, cached=cached,
                         latency_s=time.perf_counter() - start)
        return data, call

    def generate(self, spec: CircuitSpec, noise: str, shots: int, seed: int) -> CodeResult:
        user = f"{_spec_block(spec, noise, shots, seed)}\n\n{CODE_CONTRACT}\nWrite the script."
        data, call = self._call("write code", GENERATE_SYSTEM, user, _CODE_SCHEMA, "qiskit_script")
        return CodeResult(code=_strip_fences(data["code"]), call=call, notes=data.get("notes", ""))

    def repair(self, request: RepairRequest) -> RepairResult:
        history = "\n".join(f"- attempt {h.attempt}: {h.outcome}" + (f" (fix tried: {h.fix_summary})"
                                                                      if h.fix_summary else "")
                            for h in request.history) or "- none"
        user = "\n\n".join([
            _spec_block(request.spec, request.noise),
            f"Current script:\n```python\n{request.code}\n```",
            f"Error: {request.error or 'none (the script ran)'}",
            f"Stderr tail:\n{request.stderr_tail or '(empty)'}",
            f"Verifier: {request.verdict_reason or 'not reached'}",
            f"Automatic diagnosis: {request.diagnosis}",
            f"Earlier attempts:\n{history}",
            CODE_CONTRACT,
        ])
        data, call = self._call("repair code", REPAIR_SYSTEM, user, _REPAIR_SCHEMA, "qiskit_repair")
        code = _strip_fences(data["code"])
        return RepairResult(code=code, diagnosis=data.get("diagnosis", ""), fix_summary=data.get("fix_summary", ""),
                            changed=code.strip() != request.code.strip(), call=call)
