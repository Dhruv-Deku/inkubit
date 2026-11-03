"""An AI scientist that learns under proof: Muse Spark proposes circuits in rounds and sees what exact physics said.

Task (as in the discovery lab): a CNOT layout that, with free single-qubit rotations around every CNOT, prepares a
target state exactly, with as few CNOTs as possible on the allowed wiring. Each round Muse Spark proposes up to four
layouts; the exact optimiser fits each one (L-BFGS on the overlap, NumPy statevector) and returns a verdict: reached
the target (infidelity below 1e-9, then proven by Qiskit's Statevector to 1e-8), how close it got otherwise, or which
pair is not wired. Three conditions with the same number of proposals:

* feedback: every earlier proposal and its verdict are in the next prompt, with the best proven count so far;
* no feedback: the same model, asked afresh each round (a numbered attempt, so no answer is reused);
* random wiring: layouts of the same lengths as the feedback run's, with random allowed pairs.

The learning curve is the fewest proven CNOTs after each round. Nothing the model says is taken on trust: a layout
counts only when the optimiser reaches the target and Qiskit confirms it.
"""

from __future__ import annotations

import json
import random
import threading
import time
import uuid
from typing import Any

import numpy as np
from pydantic import BaseModel

from inkubit.adapters.base import ModelCall
from inkubit.agent.events import EventBus
from inkubit.discovery import FIT, GOALS, MAX_CX, PROOF, Goal, _dicke, _pairs, fit, goal_target, lower_bound, prune, spec_of, to_ops

ROUNDS = 5
PER_ROUND = 4

LINE5 = [(0, 1), (1, 2), (2, 3), (3, 4)]
TARGETS: dict[str, Goal] = {
    "w4": GOALS["w4"],
    "dicke42": GOALS["dicke42"],
    "w5_line": Goal(id="w5_line", title="W state on 5 qubits in a line", num_qubits=5, coupling=LINE5,
                    blurb="One excitation shared by five qubits, each wired only to its neighbours: no textbook "
                          "circuit fits, so the layout has to be found."),
}


def target_of(goal: Goal) -> np.ndarray:
    return _dicke(5, 1) if goal.id == "w5_line" else goal_target(goal)


SCHEMA = {"type": "object", "additionalProperties": False, "required": ["ideas"], "properties": {
    "ideas": {"type": "array", "maxItems": PER_ROUND, "items": {
        "type": "object", "additionalProperties": False, "required": ["cnots", "why"], "properties": {
            "cnots": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                      "description": "Ordered [control, target] pairs."},
            "why": {"type": "string", "description": "One sentence: why this layout should work."}}}}}}
BASE = ("You design quantum circuits. Propose CNOT layouts: ordered [control, target] pairs that, with free "
        "single-qubit rotations before and after every CNOT, can prepare the target state exactly with as few CNOTs "
        "as possible. Use only the allowed pairs. Qubit 0 is the rightmost character of a ket. Return up to 4 "
        "layouts, each with a one-sentence reason. Do not compute amplitudes: an exact optimiser fits the angles.")
FEEDBACK = (" You are in a series of rounds. The user gives every layout you proposed before and what the exact "
            "optimiser found: 'reached' (the layout prepares the state, proven), the closest infidelity it got to "
            "otherwise (smaller is closer), or an unwired pair. Learn from it: look for layouts with fewer CNOTs than "
            "the best one that reached the target, repair near misses, and do not repeat a layout already tried.")


class Proposal(BaseModel):
    cnots: list[tuple[int, int]]
    why: str = ""
    count: int
    verdict: str  # reached | missed | invalid | repeat
    infidelity: float | None = None
    proof: float | None = None
    note: str = ""


class Round(BaseModel):
    round: int
    proposals: list[Proposal]
    best_so_far: int | None  # fewest proven CNOTs after this round
    seconds: float


class Run(BaseModel):
    condition: str  # feedback | fresh | random
    rounds: list[Round]
    calls: list[ModelCall] = []


def judge(goal: Goal, target: np.ndarray, skel: list[tuple[int, int]], rng: np.random.Generator,
          seen: set[tuple[tuple[int, int], ...]]) -> Proposal:
    """The exact verdict on one layout: fit, prune, then an independent Qiskit proof."""
    n = goal.num_qubits
    cplx = bool(np.max(np.abs(np.imag(target))) > 1e-12 or np.any(np.real(target) < -1e-12))
    ok = set(_pairs(goal))
    key = tuple(skel)
    if not skel or len(skel) > MAX_CX:
        return Proposal(cnots=skel, count=len(skel), verdict="invalid", note=f"needs 1 to {MAX_CX} CNOTs")
    bad = next((p for p in skel if p not in ok or not all(0 <= q < n for q in p)), None)
    if bad is not None:
        return Proposal(cnots=skel, count=len(skel), verdict="invalid", note=f"pair {list(bad)} is not wired")
    if key in seen:
        return Proposal(cnots=skel, count=len(skel), verdict="repeat", note="already tried")
    seen.add(key)
    err, x = fit(target, skel, n, cplx, rng, restarts=4)
    if err >= FIT or x is None:
        return Proposal(cnots=skel, count=len(skel), verdict="missed", infidelity=float(err))
    x = prune(target, skel, n, cplx, x)
    from qiskit.quantum_info import Statevector

    from inkubit.spec import parse_spec
    from inkubit.verify.expected import build_reference_circuit

    qc = build_reference_circuit(parse_spec(spec_of(to_ops(x, skel, n, cplx), n, "learned")))
    overlap = float(abs(np.vdot(target, Statevector(qc).data)) ** 2)
    if overlap < 1 - PROOF:
        return Proposal(cnots=skel, count=len(skel), verdict="missed", infidelity=1 - overlap, note="failed the Qiskit proof")
    return Proposal(cnots=skel, count=len(skel), verdict="reached", infidelity=float(err), proof=overlap)


def _verdict_text(p: Proposal) -> str:
    if p.verdict == "reached":
        return "reached the target (proven)"
    if p.verdict == "missed":
        return f"missed: closest infidelity {p.infidelity:.2g}"
    return p.note


def _ask(goal: Goal, target: np.ndarray, reasoning: Any, history: list[Proposal] | None, attempt: int,
         model: str | None) -> tuple[list[tuple[list[tuple[int, int]], str]], ModelCall]:
    from inkubit.notation import dirac

    n = goal.num_qubits
    allowed = sorted({tuple(sorted(p)) for p in _pairs(goal)})
    user: dict[str, Any] = {"target_state": dirac(target, n).text, "num_qubits": n,
                            "allowed_pairs_either_direction": allowed, "at_least_cnots": lower_bound(target, n)}
    if history is None:
        user["attempt"] = attempt
        system = BASE
    else:
        best = min((p.count for p in history if p.verdict == "reached"), default=None)
        user |= {"round": attempt, "best_proven_cnots_so_far": best,
                 "earlier_proposals": [{"cnots": [list(c) for c in p.cnots], "count": p.count, "result": _verdict_text(p)}
                                       for p in history]}
        system = BASE + FEEDBACK
    for attempt, budget in enumerate((12000, 32000)):  # a long answer can be cut off; retry with more room
        try:
            data, call = reasoning.structured(system, json.dumps(user | ({"retry": 1} if attempt else {}), ensure_ascii=False),
                                              SCHEMA, "circuit_ideas", effort="medium", max_tokens=budget, model=model)
            break
        except Exception:  # noqa: BLE001
            if attempt:
                raise
    out = []
    for idea in (data.get("ideas") or [])[:PER_ROUND]:
        skel = [(int(p[0]), int(p[1])) for p in idea.get("cnots") or [] if isinstance(p, list) and len(p) == 2]
        out.append((skel, str(idea.get("why", ""))[:200]))
    return out, call


def run_condition(goal: Goal, target: np.ndarray, condition: str, reasoning: Any = None, model: str | None = None,
                  rounds: int = ROUNDS, lengths: list[list[int]] | None = None, seed: int = 7,
                  on_round: Any = None) -> Run:
    """One condition: 'feedback', 'fresh' (no feedback) or 'random' (needs ``lengths`` per round)."""
    rng = np.random.default_rng(seed)
    pick = random.Random(seed)
    seen: set[tuple[tuple[int, int], ...]] = set()
    history: list[Proposal] = []
    out: list[Round] = []
    calls: list[ModelCall] = []
    best: int | None = None
    pairs = _pairs(goal)
    for r in range(1, rounds + 1):
        t0 = time.perf_counter()
        if condition == "random":
            ideas = [([pick.choice(pairs) for _ in range(k)], "random allowed pairs") for k in (lengths or [[]])[r - 1]]
        else:
            ideas, call = _ask(goal, target, reasoning, history if condition == "feedback" else None, r, model)
            calls.append(call)
        props = [judge(goal, target, skel, rng, seen).model_copy(update={"why": why}) for skel, why in ideas]
        history += props
        reached = [p.count for p in props if p.verdict == "reached"]
        if reached:
            best = min(reached + ([best] if best is not None else []))
        rd = Round(round=r, proposals=props, best_so_far=best, seconds=round(time.perf_counter() - t0, 1))
        out.append(rd)
        if on_round:
            on_round(condition, rd)
    return Run(condition=condition, rounds=out, calls=calls)


def summary(goal: Goal, runs: dict[str, Run], target: np.ndarray) -> dict[str, Any]:
    def curve(run: Run) -> list[int | None]:
        return [r.best_so_far for r in run.rounds]

    def works(run: Run) -> float:
        props = [p for r in run.rounds for p in r.proposals]
        return sum(p.verdict == "reached" for p in props) / len(props) if props else 0.0

    fb = runs["feedback"]
    first = next((r.best_so_far for r in fb.rounds if r.best_so_far is not None), None)
    final = fb.rounds[-1].best_so_far
    return {"goal": goal.model_dump(), "lower_bound": lower_bound(target, goal.num_qubits),
            "curves": {k: curve(v) for k, v in runs.items()},
            "reach_rate": {k: round(works(v), 3) for k, v in runs.items()},
            "first_proven": first, "final_proven": final,
            "runs": {k: v.model_dump(mode="json") for k, v in runs.items()}}


def run_all(goal: Goal, reasoning: Any, model: str | None = None, rounds: int = ROUNDS, on_round: Any = None) -> dict[str, Any]:
    target = target_of(goal)
    fb = run_condition(goal, target, "feedback", reasoning, model, rounds, on_round=on_round)
    fresh = run_condition(goal, target, "fresh", reasoning, model, rounds, on_round=on_round)
    lengths = [[p.count for p in r.proposals if p.count] for r in fb.rounds]
    rnd = run_condition(goal, target, "random", rounds=rounds, lengths=lengths, on_round=on_round)
    return summary(goal, {"feedback": fb, "fresh": fresh, "random": rnd}, target)


class Session:
    def __init__(self, goal: Goal):
        self.id = uuid.uuid4().hex[:12]
        self.goal = goal
        self.bus = EventBus()
        self.status = "running"
        self.error: str | None = None
        self.result: dict[str, Any] | None = None


def launch(s: Session, models: Any, rounds: int = ROUNDS) -> None:
    st = models.settings
    if not (st.provider == "meta" and st.has_key):
        raise ValueError("the learning loop needs the live model (Muse Spark); the recorded benchmark is shown instead")

    def go() -> None:
        try:
            def on_round(condition: str, rd: Round) -> None:
                s.bus.emit("learning", "info", f"{condition} round {rd.round}", kind="round", condition=condition,
                           round=rd.model_dump(mode="json"))

            s.result = run_all(s.goal, models.reasoning, rounds=rounds, on_round=on_round)
            s.status = "done"
            s.bus.emit("learning", "ok", "done", kind="result", result=s.result)
        except Exception as err:  # noqa: BLE001 - shown on the page
            s.status, s.error = "failed", str(err)[:400]
            s.bus.emit("learning", "fail", s.error, kind="error")
        finally:
            s.bus.close()

    threading.Thread(target=go, name=f"learning-{s.id}", daemon=True).start()


class Store:
    def __init__(self, keep: int = 10):
        self._items: dict[str, Session] = {}
        self._lock = threading.Lock()
        self.keep = keep

    def add(self, s: Session) -> None:
        with self._lock:
            self._items[s.id] = s
            while len(self._items) > self.keep:
                self._items.pop(next(iter(self._items)))

    def get(self, key: str) -> Session | None:
        with self._lock:
            return self._items.get(key)


sessions = Store()
