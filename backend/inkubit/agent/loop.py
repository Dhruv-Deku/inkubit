"""The self-checking agent loop: generate -> run -> verify -> diagnose -> repair -> retry."""

from __future__ import annotations

import difflib
import time
from typing import Any

from pydantic import BaseModel, Field

from inkubit.adapters.base import AttemptSummary, CodeModel, ModelCall, RepairRequest
from inkubit.agent.diagnose import Diagnosis, diagnose_run, diagnose_verdict
from inkubit.agent.events import EventBus
from inkubit.agent.faults import inject
from inkubit.codegen.template import DEFAULT_SEED, DEFAULT_SHOTS
from inkubit.sim.noise import get_preset
from inkubit.sim.runner import DEFAULT_TIMEOUT_S, RunResult, run_code
from inkubit.spec.models import CircuitSpec
from inkubit.verify.verdict import Verdict, verify_counts

MAX_ATTEMPTS = 4


class AgentOptions(BaseModel):
    """Knobs for one agent run."""

    noise: str = "realistic"
    shots: int = Field(default=DEFAULT_SHOTS, ge=16, le=100_000)
    seed: int = DEFAULT_SEED
    demo_fault: str | None = None  # None, "auto" or a fault name from agent.faults.FAULTS
    max_attempts: int = Field(default=MAX_ATTEMPTS, ge=1, le=8)
    timeout_s: float = DEFAULT_TIMEOUT_S
    pace_s: float = 0.0  # small pauses between steps so a live audience can follow


class AttemptRecord(BaseModel):
    """Everything about one attempt."""

    attempt: int
    code: str
    diff_from_previous: str = ""
    run: RunResult
    verdict: Verdict | None = None
    diagnosis: dict[str, str] | None = None
    fix_summary: str | None = None
    repair_call: ModelCall | None = None
    passed: bool = False


class AgentResult(BaseModel):
    """Final outcome of an agent run."""

    status: str  # "verified" | "failed"
    verified: bool
    summary: str
    attempts: list[AttemptRecord]
    final_code: str
    counts: dict[str, int] | None
    verdict: Verdict | None
    fault: dict[str, str] | None = None
    calls: list[ModelCall] = Field(default_factory=list)


def code_diff(old: str, new: str, a: str, b: str) -> str:
    """Unified diff between two scripts."""
    return "\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(), a, b, lineterm="", n=1))


def _sentence(text: str) -> str:
    text = text.strip()
    return (text[0].upper() + text[1:]).rstrip(".") + "." if text else ""


def _trim(run: RunResult) -> RunResult:
    return run.model_copy(update={"stdout": run.stdout[-4000:], "stderr": run.stderr[-4000:]})


def run_agent(spec: CircuitSpec, code_model: CodeModel, options: AgentOptions | None = None,
              bus: EventBus | None = None) -> AgentResult:
    """Run the full loop for a circuit spec and return an honest result."""
    opts = options or AgentOptions()
    bus = bus or EventBus()
    preset = get_preset(opts.noise)
    title = spec.metadata.title or "your circuit"
    calls: list[ModelCall] = []

    def pause() -> None:
        if opts.pace_s:
            time.sleep(opts.pace_s)

    n_ops = len(spec.operations)
    bus.emit("plan", "info",
             f"Plan: write Qiskit code for '{title}' ({spec.num_qubits} qubit{'s' if spec.num_qubits != 1 else ''}, "
             f"{n_ops} operation{'s' if n_ops != 1 else ''}), run it with {opts.shots} shots under "
             f"{preset.label.lower()} noise, and check the counts against an independent simulation "
             f"of the spec. Up to {opts.max_attempts} attempts.",
             noise=preset.as_dict(), shots=opts.shots)
    pause()

    bus.emit("generate", "running", "Writing the Qiskit script…")
    gen = code_model.generate(spec, opts.noise, opts.shots, opts.seed)
    calls.append(gen.call)
    code = gen.code
    fallback = " (mock fallback: the live model call failed)" if gen.call.provider == "mock-fallback" else ""
    bus.emit("generate", "ok", f"Script ready: {len(code.splitlines())} lines from {gen.call.model}{fallback}.",
             call=gen.call.model_dump(), code=code)
    pause()

    fault_info: dict[str, str] | None = None
    try:
        planted = inject(code, spec, opts.demo_fault) if opts.demo_fault else None
    except ValueError as err:
        planted = None
        bus.emit("inject", "warn", f"Demo mode: no fault planted ({err}); running the script as written.")
    if planted:
        broken, fault = planted
        fault_info = {"name": fault.name, "label": fault.label, "description": fault.description}
        bus.emit("inject", "warn",
                 f"Demo mode: attempt 1 was broken on purpose. Fault: {fault.label} ({fault.description}). "
                 "Watch the agent catch it.",
                 fault=fault_info, diff=code_diff(code, broken, "generated", "attempt 1"))
        code = broken
        pause()

    attempts: list[AttemptRecord] = []
    history: list[AttemptSummary] = []
    previous_code = code
    verdict: Verdict | None = None
    run: RunResult | None = None

    for n in range(1, opts.max_attempts + 1):
        bus.emit("run", "running", f"Attempt {n}: running the script in a sandboxed subprocess…", attempt=n)
        run = run_code(code, timeout_s=opts.timeout_s)
        verdict = None
        diag: Diagnosis
        if run.ok and run.counts is not None:
            bus.emit("run", "ok", f"Attempt {n} ran in {run.duration_s:.1f} s and returned "
                                  f"{sum(run.counts.values())} shots.", attempt=n, counts=run.counts)
            pause()
            bus.emit("verify", "running", f"Checking attempt {n} against the exact distribution the spec "
                                          f"predicts under '{opts.noise}' noise…", attempt=n)
            verdict = verify_counts(spec, run.counts, opts.noise)
            if verdict.passed:
                record = AttemptRecord(attempt=n, code=code, run=_trim(run), verdict=verdict, passed=True,
                                       diff_from_previous=code_diff(previous_code, code, f"attempt {n - 1}",
                                                                    f"attempt {n}") if n > 1 else "")
                attempts.append(record)
                bus.emit("verify", "ok", f"Attempt {n} passed. {verdict.reason}", attempt=n,
                         verdict=verdict.model_dump())
                break
            bus.emit("verify", "fail", f"Attempt {n} does not match the spec: {verdict.reason}", attempt=n,
                     verdict=verdict.model_dump())
            diag = diagnose_verdict(spec, verdict)
        else:
            bus.emit("run", "fail", f"Attempt {n} failed to run: {run.short_error()}.", attempt=n,
                     error_type=run.error_type, stderr=run.stderr[-1500:])
            diag = diagnose_run(run)
        pause()

        record = AttemptRecord(attempt=n, code=code, run=_trim(run), verdict=verdict,
                               diagnosis={"category": diag.category, "summary": diag.summary, "hint": diag.hint},
                               diff_from_previous=code_diff(previous_code, code, f"attempt {n - 1}",
                                                            f"attempt {n}") if n > 1 else "")
        attempts.append(record)
        last = n == opts.max_attempts
        bus.emit("diagnose", "fail",
                 f"Attempt {n} failed: {diag.summary}. {_sentence(diag.hint)}"
                 + ("" if last else " Repairing…"),
                 attempt=n, category=diag.category)
        if last:
            break
        pause()

        bus.emit("repair", "running", "Asking the repairer for a fix (spec, code, error, verdict and attempt "
                                      "history attached)…", attempt=n)
        repair = code_model.repair(RepairRequest(
            spec=spec, noise=opts.noise, code=code, error=None if run.ok else run.short_error(),
            stderr_tail=run.stderr[-1500:], verdict_reason=verdict.reason if verdict else None,
            diagnosis=f"{diag.summary}; {diag.hint}", diagnosis_category=diag.category, history=history,
        ))
        calls.append(repair.call)
        record.fix_summary = repair.fix_summary
        record.repair_call = repair.call
        history.append(AttemptSummary(attempt=n, outcome=diag.summary, fix_summary=repair.fix_summary))
        if not repair.changed:
            bus.emit("repair", "fail", f"{repair.call.model} could not find a fix: {repair.diagnosis} "
                                       "Stopping instead of re-running the same code.",
                     attempt=n, call=repair.call.model_dump())
            break
        fb = " (mock fallback)" if repair.call.provider == "mock-fallback" else ""
        bus.emit("repair", "ok", f"Fix from {repair.call.model}{fb}: {_sentence(repair.fix_summary)}",
                 attempt=n, call=repair.call.model_dump(), diagnosis=repair.diagnosis,
                 diff=code_diff(code, repair.code, f"attempt {n}", f"attempt {n + 1}"))
        previous_code, code = code, repair.code
        pause()

    final = attempts[-1]
    verified = final.passed
    repairs = sum(1 for a in attempts if a.fix_summary)
    if verified and verdict is not None:
        noise_cost = 1 - verdict.metrics.fidelity_vs_ideal
        summary = (f"Verified on attempt {final.attempt}"
                   + (f" after {repairs} repair{'s' if repairs != 1 else ''}" if repairs else "")
                   + f". Fidelity to the noiseless ideal: {verdict.metrics.fidelity_vs_ideal:.3f}"
                   + (f" (noise cost {noise_cost * 100:.1f}%)." if noise_cost > 0.0005 else "."))
        bus.emit("done", "ok", summary, attempt=final.attempt)
    else:
        problem = final.diagnosis["summary"] if final.diagnosis else "unknown"
        summary = (f"Not verified: stopped after {len(attempts)} attempt{'s' if len(attempts) != 1 else ''}. "
                   f"Last problem: {problem}. The code and counts shown are the last attempt and are NOT verified.")
        bus.emit("done", "fail", summary, attempt=final.attempt)

    return AgentResult(
        status="verified" if verified else "failed", verified=verified, summary=summary,
        attempts=attempts, final_code=final.code,
        counts=final.run.counts, verdict=final.verdict, fault=fault_info, calls=calls,
    )


def result_payload(result: AgentResult) -> dict[str, Any]:
    """JSON-ready dict of a result."""
    return result.model_dump(mode="json")
