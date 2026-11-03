"""AI alone vs Inkubit: what a language model says a circuit does, against what it does.

Asked about a circuit, a chat model answers from patterns, with nothing to check itself against, so it can be
confidently wrong. Here the same model that Inkubit uses (Muse Spark) is asked to predict a circuit's measured
outcome odds on its own, with the circuit as data and no simulator, and its answer is scored against the exact
simulation Inkubit verifies every run with. The difference is the point of the app: in Inkubit the model's work
(reading the sketch, writing the code) is always run and checked before anything is shown.
"""

from __future__ import annotations

import json
import math
import random
from datetime import date
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from inkubit import EXAMPLES_DIR
from inkubit.spec.models import CircuitSpec
from inkubit.verify.expected import Distribution, ideal_distribution
from inkubit.verify.metrics import total_variation_distance

MATCH, CLOSE = 0.01, 0.05  # total variation distance
BENCH_FILE = EXAMPLES_DIR / "arena_benchmark.json"


def facts(spec: CircuitSpec) -> dict[str, Any]:
    """The circuit as the model sees it: no title or notes, which could name the answer."""
    ops = []
    for op in spec.operations:
        o: dict[str, Any] = {"gate": op.gate, "targets": op.targets}
        if op.controls:
            o["controls"] = op.controls
        if op.params:
            o["params"] = [round(p, 6) for p in op.params]
        ops.append(o)
    return {"num_qubits": spec.num_qubits, "operations": ops,
            "measured": [{"qubit": q, "clbit": c} for q, c in spec.measured_pairs()],
            "num_clbits": spec.num_clbits}


class Comparison(BaseModel):
    truth: Distribution
    guess: dict[str, float]
    guess_sum: float
    tvd: float  # half the summed absolute difference, after normalising the guess
    verdict: str  # matched | close | wrong
    impossible: list[str]  # outcomes the model gave that cannot occur at all
    missed: list[str]  # outcomes that occur (>= 1%) that the model left out


def compare(spec: CircuitSpec, guess: dict[str, float]) -> Comparison:
    truth = ideal_distribution(spec)
    total = sum(guess.values())
    norm = {k: v / total for k, v in guess.items()} if total > 0 else {}
    tvd = total_variation_distance(truth, norm) if norm else 1.0
    verdict = "matched" if tvd < MATCH and abs(total - 1) < 0.02 else "close" if tvd < CLOSE else "wrong"
    return Comparison(
        truth=truth, guess=guess, guess_sum=total, tvd=tvd, verdict=verdict,
        impossible=sorted(k for k, v in guess.items() if v > 0.005 and truth.get(k, 0.0) < 1e-9),
        missed=sorted(k for k, v in truth.items() if v >= 0.01 and guess.get(k, 0.0) < 1e-9))


class ArenaResult(BaseModel):
    comparison: Comparison
    reasoning: str
    call: dict[str, Any]


def ask_alone(spec: CircuitSpec, predict: Callable[[dict[str, Any]], Any]) -> ArenaResult:
    guess = predict(facts(spec))
    return ArenaResult(comparison=compare(spec, guess.outcomes), reasoning=guess.reasoning,
                       call=guess.call.model_dump(mode="json"))


# ---------------------------------------------------------------- the recorded benchmark

def fresh_circuits(count: int = 10, seed: int = 2026) -> list[dict[str, Any]]:
    """Circuits no textbook contains (seeded, so the benchmark is repeatable): 3 to 5 qubits, 8 to 14 gates, a mix of
    named angles (pi/k) and arbitrary ones, every qubit measured. This is what a student's own sketch looks like to a
    model: something it cannot have memorised."""
    rng = random.Random(seed)
    out = []
    for k in range(count):
        n = 3 + k % 3
        ops: list[dict[str, Any]] = []
        for _ in range(8 + rng.randrange(7)):
            kind = rng.random()
            if kind < 0.3:
                ops.append({"gate": rng.choice(["H", "X", "S", "T"]), "targets": [rng.randrange(n)]})
            elif kind < 0.55:
                a = rng.choice([math.pi / 2, math.pi / 3, math.pi / 4, 2 * math.pi / 3]) if rng.random() < 0.5 \
                    else round(rng.uniform(0.2, 2.9), 3)
                ops.append({"gate": rng.choice(["RY", "RX", "RZ"]), "targets": [rng.randrange(n)], "params": [a]})
            elif kind < 0.9:
                c, t = rng.sample(range(n), 2)
                ops.append({"gate": rng.choice(["CX", "CX", "CZ"]), "controls": [c], "targets": [t]})
            else:
                c1, c2, t = rng.sample(range(n), 3)
                ops.append({"gate": "CCX", "controls": [c1, c2], "targets": [t]})
        out.append({"kind": "circuit", "version": "1.0", "num_qubits": n, "num_clbits": n, "operations": ops,
                    "measurements": [{"qubit": q, "clbit": q} for q in range(n)],
                    "metadata": {"title": f"New circuit {k + 1} ({n} qubits, {len(ops)} gates)", "origin": "manual"}})
    return out


def bigger_circuits(count: int = 6, seed: int = 4242) -> list[dict[str, Any]]:
    """Bigger new circuits: 6 to 8 qubits, all put in superposition first so every gate matters, then 18 to 26
    entangling and rotation gates with arbitrary angles; only q0-q3 are measured, so the answer stays a short list but
    working it out by hand means tracking up to 256 amplitudes."""
    rng = random.Random(seed)
    out = []
    for k in range(count):
        n = 6 + k // 2
        ops: list[dict[str, Any]] = [{"gate": "H", "targets": list(range(n))}]
        for _ in range(18 + rng.randrange(9)):
            kind = rng.random()
            if kind < 0.4:
                ops.append({"gate": rng.choice(["RY", "RX", "RZ"]), "targets": [rng.randrange(n)],
                            "params": [round(rng.uniform(0.2, 2.9), 3)]})
            elif kind < 0.85:
                c, t = rng.sample(range(n), 2)
                ops.append({"gate": rng.choice(["CX", "CX", "CZ"]), "controls": [c], "targets": [t]})
            else:
                c1, c2, t = rng.sample(range(n), 3)
                ops.append({"gate": "CCX", "controls": [c1, c2], "targets": [t]})
        out.append({"kind": "circuit", "version": "1.0", "num_qubits": n, "num_clbits": 4, "operations": ops,
                    "measurements": [{"qubit": q, "clbit": q} for q in range(4)],
                    "metadata": {"title": f"Bigger circuit {k + 1} ({n} qubits, {len(ops)} gates)", "origin": "manual"}})
    return out


class BenchRow(BaseModel):
    id: str
    set: str = "textbook"  # textbook | new | bigger
    title: str
    qubits: int
    gates: int
    tvd: float | None  # None when the model gave no usable answer
    verdict: str  # matched | close | wrong | no answer
    impossible: int
    missed: int
    seconds: float


class SetSummary(BaseModel):
    count: int
    matched: int
    close: int
    wrong: int
    no_answer: int
    mean_tvd: float  # over the answers given


class Benchmark(BaseModel):
    model: str
    date: str
    rows: list[BenchRow]
    textbook: SetSummary
    new: SetSummary
    bigger: SetSummary
    verifier: str  # what the planted-fault benchmark says about Inkubit's own checks


def _set(rows: list[BenchRow]) -> SetSummary:
    given = [r.tvd for r in rows if r.tvd is not None]
    return SetSummary(count=len(rows), matched=sum(r.verdict == "matched" for r in rows),
                      close=sum(r.verdict == "close" for r in rows), wrong=sum(r.verdict == "wrong" for r in rows),
                      no_answer=sum(r.verdict == "no answer" for r in rows),
                      mean_tvd=sum(given) / len(given) if given else 0.0)


def summarise(model: str, rows: list[BenchRow], verifier: str) -> Benchmark:
    return Benchmark(model=model, date=date.today().isoformat(), rows=rows,
                     textbook=_set([r for r in rows if r.set == "textbook"]),
                     new=_set([r for r in rows if r.set == "new"]),
                     bigger=_set([r for r in rows if r.set == "bigger"]), verifier=verifier)


def load_benchmark(path: Path = BENCH_FILE) -> Benchmark | None:
    try:
        return Benchmark.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None
