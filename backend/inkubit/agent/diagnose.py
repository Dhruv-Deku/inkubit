"""Turn a failed run or a failed verdict into a plain-language diagnosis."""

from __future__ import annotations

from dataclasses import dataclass

from inkubit.sim.runner import RunResult
from inkubit.spec.models import CircuitSpec
from inkubit.verify.verdict import Verdict, describe


@dataclass(frozen=True)
class Diagnosis:
    """What went wrong, for people and for the repairer."""

    category: str
    summary: str  # one sentence, starts lower-case, used after "Attempt N failed: "
    hint: str  # the suspected cause


def _bit_one_prob(dist: dict[str, float], nc: int, clbit: int) -> float:
    idx = nc - 1 - clbit
    return sum(p for k, p in dist.items() if k[idx] == "1")


def _correlation(dist: dict[str, float], nc: int, a: int, b: int) -> float:
    """<Z_a Z_b> over the distribution (+1 always equal, -1 always opposite)."""
    ia, ib = nc - 1 - a, nc - 1 - b
    return sum(p * (1 if k[ia] == k[ib] else -1) for k, p in dist.items())


def diagnose_run(run: RunResult) -> Diagnosis:
    """Diagnose a run that did not produce counts."""
    et, msg = run.error_type or "", run.error_message or ""
    if run.timed_out:
        return Diagnosis("timeout", f"the script {run.short_error()}", "it probably loops forever")
    if et in ("ModuleNotFoundError", "ImportError"):
        hint = "an import path is wrong"
        if "qiskit.providers.aer" in msg:
            hint = "AerSimulator moved from qiskit.providers.aer to the qiskit_aer package in Qiskit 1.0"
        return Diagnosis("import_error", f"the script crashed on import ({et}: {msg})", hint)
    if et == "SyntaxError":
        return Diagnosis("syntax_error", f"the script does not parse ({msg})", "a typo in the code")
    if et == "SafetyError":
        return Diagnosis("safety", f"the script was blocked before running ({msg})",
                         "it uses a module or call outside the simulation sandbox")
    if "No counts" in msg:
        return Diagnosis("no_counts", "the script ran but recorded no counts",
                         "the measurements look missing")
    if et == "MissingResult":
        return Diagnosis("missing_result", "the script ran but never printed its result line",
                         "the INKUBIT_RESULT print was removed or never reached")
    return Diagnosis("runtime_error", f"the script crashed ({run.short_error()})", "a runtime error in the code")


def diagnose_verdict(spec: CircuitSpec, verdict: Verdict) -> Diagnosis:
    """Diagnose a run whose counts do not match the spec."""
    nc = spec.num_clbits
    exp, got = verdict.ideal, verdict.measured
    summary = f"expected ~{describe(exp)}, got {describe(got)}"
    clbits = sorted(c for _, c in spec.measured_pairs())

    if len(got) == 1 and len(verdict.expected) > 1 and verdict.metrics.shots > 50:
        return Diagnosis("suspicious_result", summary,
                         "every shot gave the same answer even though noise should spread them; "
                         "the counts look hard-coded rather than simulated")
    for i, a in enumerate(clbits):
        for b in clbits[i + 1:]:
            ce, cg = _correlation(exp, nc, a, b), _correlation(got, nc, a, b)
            if abs(ce) > 0.8 and abs(cg) < 0.4:
                return Diagnosis("lost_entanglement", summary,
                                 f"bits c{a} and c{b} should agree every time but come out independent; "
                                 "the entangling gate looks missing or points the wrong way")
    for c in clbits:
        pe, pg = _bit_one_prob(exp, nc, c), _bit_one_prob(got, nc, c)
        if abs(pe - pg) > 0.25:
            return Diagnosis("wrong_marginal", summary,
                             f"bit c{c} reads 1 in {round(pg * 100)}% of shots, the spec expects "
                             f"{round(pe * 100)}%; a gate may act on the wrong qubit")
    return Diagnosis("mismatch", summary, "the circuit in the code differs from the drawing")
