"""Optional repair backend that drives the Muse Code agent headlessly.

Opt in with ``INKUBIT_CODE_BACKEND=muse-cli``. Each repair writes the failing
script, the spec and the evidence into a scratch workspace and runs
``muse exec --prompt-file task.txt --disable-approval --max-model-steps 12
--model <INKUBIT_CODE_MODEL>`` there (flags from docs/meta-api/muse-code_extending.md
and muse-code_configuration.md), then reads the edited ``main.py`` back.
The Inkubit verifier, not Muse Code's exit status, decides whether it worked.
Code generation still goes through the API model.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from inkubit.adapters.base import CodeModel, CodeResult, ModelCall, RepairRequest, RepairResult
from inkubit.adapters.config import Settings
from inkubit.adapters.prompts import CODE_CONTRACT

TASK = """\
main.py is a Qiskit script that fails. spec.json is the source of truth for the circuit.
evidence.txt has the error, the verifier's verdict and earlier attempts.
Fix main.py with the smallest change so it implements spec.json exactly. Do not run it,
do not create other files, and do not touch spec.json or evidence.txt.

{contract}
"""


class MuseCodeCliModel(CodeModel):
    """Repairs through ``muse exec``; generation is delegated to ``api_model``."""

    def __init__(self, settings: Settings, api_model: CodeModel, timeout_s: float = 300.0):
        self.settings = settings
        self.api_model = api_model
        self.timeout_s = timeout_s

    def generate(self, spec, noise, shots, seed) -> CodeResult:
        return self.api_model.generate(spec, noise, shots, seed)

    def repair(self, request: RepairRequest) -> RepairResult:
        exe = shutil.which("muse")
        if exe is None:
            raise RuntimeError("the Muse Code CLI ('muse') is not on PATH")
        start = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="inkubit-muse-") as tmp:
            ws = Path(tmp)
            (ws / "main.py").write_text(request.code, encoding="utf-8")
            (ws / "spec.json").write_text(request.spec.model_dump_json(indent=2), encoding="utf-8")
            history = "\n".join(f"attempt {h.attempt}: {h.outcome} / tried: {h.fix_summary}" for h in request.history)
            (ws / "evidence.txt").write_text(
                f"noise preset: {request.noise}\nerror: {request.error}\nverifier: {request.verdict_reason}\n"
                f"diagnosis: {request.diagnosis}\nstderr:\n{request.stderr_tail}\nhistory:\n{history}\n",
                encoding="utf-8")
            (ws / "task.txt").write_text(TASK.format(contract=CODE_CONTRACT), encoding="utf-8")
            proc = subprocess.run(
                [exe, "exec", "--prompt-file", "task.txt", "--disable-approval", "--max-model-steps", "12",
                 "--model", self.settings.code_model],
                cwd=ws, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=self.timeout_s,
            )
            code = (ws / "main.py").read_text(encoding="utf-8")
        call = ModelCall(provider="meta", model=f"Muse Code ({self.settings.code_model})", role="repair code",
                         latency_s=time.perf_counter() - start)
        if proc.returncode != 0:
            raise RuntimeError(f"muse exec exited with {proc.returncode}: {proc.stderr[-300:]}")
        summary = (proc.stdout.strip().splitlines() or ["edited main.py"])[-1][:300]
        return RepairResult(code=code, diagnosis=request.diagnosis, fix_summary=summary,
                            changed=code.strip() != request.code.strip(), call=call)
