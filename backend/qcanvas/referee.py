"""The AI referee: Muse Spark makes claims about a circuit, Muse Wonder tries to break them, exact simulation decides.

Three kinds of claim, each checkable exactly: the probability of an outcome (within 0.02), which outcome is the most
likely (any of the tied maxima counts), and whether two qubits are entangled just before measurement (negativity of
their reduced state, from the exact statevector). The protocol:

1. The referee asks the same three questions about every circuit: which outcome is the most likely, the probability
   of the second most likely outcome (chosen from the exact odds so the question is never trivial; the models are not
   told why), and whether two given qubits are entangled. Muse Spark sees the circuit (operations, measurements; no
   title) and answers each as a precise claim.
2. Muse Wonder sees the circuit and the claims and agrees with or disputes each, giving its own value and a reason.
3. Muse Spark sees the disputes and stands by or concedes each disputed claim (conceding adopts Wonder's value).
4. Exact simulation grades every position: Spark's first claim, Wonder's verdict and the final answer.

Neither model runs code; the point is what a debate between models can and cannot settle, and that only the
simulator knows which side is right.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

import numpy as np
from pydantic import BaseModel

from qcanvas.adapters.base import ModelCall
from qcanvas.arena import facts
from qcanvas.spec.models import CircuitSpec

TOLERANCE = 0.02
CONVENTIONS = ("Qiskit conventions: every qubit starts in |0>, angles in radians, gates applied in order. Bitstrings "
               "follow Qiskit order: the rightmost character is classical bit 0. Nobody can run a simulator here.")

_CLAIM = {"type": "object", "additionalProperties": False, "required": ["kind", "bits", "qubits", "probability", "entangled", "statement"],
          "properties": {
              "kind": {"type": "string", "enum": ["probability", "most_likely", "entangled"]},
              "bits": {"type": "string", "description": "The outcome bitstring (probability, most_likely); empty otherwise."},
              "qubits": {"type": "array", "items": {"type": "integer"}, "description": "Two qubits (entangled); empty otherwise."},
              "probability": {"type": "number", "description": "The probability (probability); -1 otherwise."},
              "entangled": {"type": "boolean", "description": "Whether the two qubits are entangled (entangled); false otherwise."},
              "statement": {"type": "string", "description": "The claim in one plain sentence."}}}
CLAIMS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["claims"],
                 "properties": {"claims": {"type": "array", "minItems": 3, "maxItems": 3, "items": _CLAIM}}}
CHALLENGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["responses"], "properties": {"responses": {
    "type": "array", "minItems": 3, "maxItems": 3, "items": {
        "type": "object", "additionalProperties": False, "required": ["agree", "probability", "bits", "entangled", "reason"],
        "properties": {"agree": {"type": "boolean"},
                       "probability": {"type": "number", "description": "If disputing a probability claim: your value; else -1."},
                       "bits": {"type": "string", "description": "If disputing a most-likely claim: your outcome; else empty."},
                       "entangled": {"type": "boolean", "description": "If disputing an entanglement claim: your answer; else false."},
                       "reason": {"type": "string", "description": "One or two sentences."}}}}}}
REPLY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["replies"], "properties": {"replies": {
    "type": "array", "minItems": 3, "maxItems": 3, "items": {
        "type": "object", "additionalProperties": False, "required": ["stand", "reason"],
        "properties": {"stand": {"type": "boolean", "description": "true: keep your claim; false: accept the challenge."},
                       "reason": {"type": "string"}}}}}}

PROPOSE = ("You are a quantum computing expert answering three questions about a circuit with precise, checkable "
           "claims. " + CONVENTIONS + " Answer the questions in order, one claim each, keeping the kind, the outcome "
           "and the qubits the question names: the most likely measured outcome, the probability of the named outcome, "
           "and whether the named two qubits are entangled just before measurement.")
CHALLENGE = ("You are a sceptical quantum computing expert refereeing another model's claims about a circuit. " + CONVENTIONS +
             " Work through the circuit yourself. For each of the three claims, in order, agree if it is right; if it "
             "is wrong, dispute it and give the correct value. Do not dispute a claim you cannot show is wrong.")
REPLY = ("You made three claims about a circuit and a referee model disputed some of them. " + CONVENTIONS +
         " For each claim, in order: stand by it if you still think it is right, or concede if the challenge is right. "
         "For claims that were not disputed, stand.")


class Position(BaseModel):
    text: str
    correct: bool


class Debate(BaseModel):
    circuit: dict[str, Any]
    claims: list[dict[str, Any]]  # each: claim, truth, challenge, reply, final, and who was right
    spark_first: int  # Spark's claims that were right as first stated
    final_right: int  # answers that were right after the debate
    caught: int  # wrong claims Wonder disputed with the right answer
    false_alarms: int  # right claims Wonder disputed
    talked_out: int  # right claims Spark conceded
    calls: list[ModelCall]
    seconds: float


def truth(spec: CircuitSpec) -> tuple[dict[str, float], np.ndarray]:
    from qiskit.quantum_info import Statevector

    from qcanvas.verify.expected import build_reference_circuit, ideal_distribution

    return dict(ideal_distribution(spec)), Statevector(build_reference_circuit(spec)).data


def negativity(psi: np.ndarray, a: int, b: int, n: int) -> float:
    """Negativity of the two-qubit reduced state of qubits a and b (Qiskit order: qubit 0 is the last tensor factor)."""
    t = psi.reshape([2] * n)
    ax_a, ax_b = n - 1 - a, n - 1 - b
    rest = [k for k in range(n) if k not in (ax_a, ax_b)]
    m = np.transpose(t, [ax_a, ax_b] + rest).reshape(4, -1)
    rho = m @ m.conj().T
    pt = rho.reshape(2, 2, 2, 2).transpose(0, 3, 2, 1).reshape(4, 4)  # partial transpose on the second qubit
    ev = np.linalg.eigvalsh((pt + pt.conj().T) / 2)
    return max(0.0, float(-ev[ev < 0].sum()))  # never a negative zero


def check(claim: dict[str, Any], probs: dict[str, float], psi: np.ndarray, n: int) -> tuple[bool, str]:
    """Is the claim right? And what is the truth, in words."""
    kind = claim.get("kind")
    if kind == "probability":
        bits = str(claim.get("bits", "")).replace(" ", "")
        p = probs.get(bits, 0.0)
        return abs(p - float(claim.get("probability", -1))) <= TOLERANCE, f"P({bits}) = {p:.4f}"
    if kind == "most_likely":
        bits = str(claim.get("bits", "")).replace(" ", "")
        top = max(probs.values()) if probs else 0.0
        best = sorted(k for k, v in probs.items() if v >= top - 1e-9)
        return bits in best, f"most likely: {', '.join(best)} ({top:.4f})"
    if kind == "entangled":
        qs = [int(q) for q in claim.get("qubits") or []][:2]
        if len(qs) != 2 or qs[0] == qs[1] or not all(0 <= q < n for q in qs):
            return False, "not two valid qubits"
        neg = negativity(psi, qs[0], qs[1], n)
        ent = neg > 1e-9
        return bool(claim.get("entangled")) == ent, f"qubits {qs[0]} and {qs[1]} {'are' if ent else 'are not'} entangled (negativity {neg:.4f})"
    return False, "unknown kind of claim"


def _counter(claim: dict[str, Any], resp: dict[str, Any]) -> dict[str, Any]:
    """Wonder's position as a claim of the same kind."""
    c = dict(claim)
    if claim.get("kind") == "probability":
        c["probability"] = float(resp.get("probability", -1))
    elif claim.get("kind") == "most_likely":
        c["bits"] = str(resp.get("bits", ""))
    else:
        c["entangled"] = not bool(claim.get("entangled"))
    return c


def _describe(c: dict[str, Any]) -> str:
    if c.get("kind") == "probability":
        return f"P({c.get('bits')}) = {float(c.get('probability', -1)):.4g}"
    if c.get("kind") == "most_likely":
        return f"most likely: {c.get('bits')}"
    qs = c.get("qubits") or []
    return f"qubits {', '.join(map(str, qs))} {'entangled' if c.get('entangled') else 'not entangled'}"


def questions(spec: CircuitSpec, probs: dict[str, float]) -> list[dict[str, Any]]:
    """The same three questions for every circuit, none of them trivial."""
    import random

    ranked = sorted(probs, key=lambda k: -probs[k])
    width = len(ranked[0]) if ranked else spec.num_clbits
    second = ranked[1] if len(ranked) > 1 else ranked[0][:-1] + ("1" if ranked[0][-1] == "0" else "0")
    measured = sorted({q for q, _ in spec.measured_pairs()}) or list(range(spec.num_qubits))
    pick = random.Random(json.dumps(facts(spec), sort_keys=True))
    pair = sorted(pick.sample(measured, 2)) if len(measured) >= 2 else [0, 1]
    return [{"kind": "most_likely", "question": "Which measured outcome is the most likely?"},
            {"kind": "probability", "bits": second.zfill(width), "question": f"What is the probability of outcome {second.zfill(width)}?"},
            {"kind": "entangled", "qubits": pair, "question": f"Are qubits {pair[0]} and {pair[1]} entangled just before measurement?"}]


def _ask(reasoning: Any, system: str, user: dict[str, Any], schema: dict[str, Any], name: str, model: str | None,
         calls: list[ModelCall]) -> dict[str, Any]:
    """One structured call, retried once if the model's output is not valid JSON."""
    for attempt in range(2):  # a long answer can be cut off; the retry gets twice the room
        try:
            data, call = reasoning.structured(system, json.dumps(user | ({"retry": attempt} if attempt else {})), schema, name,
                                              effort="medium", max_tokens=16000 if attempt == 0 else 32000, model=model)
            calls.append(call)
            return data
        except Exception:  # noqa: BLE001 - one retry, then the error is reported
            if attempt:
                raise
    return {}


def debate(spec: CircuitSpec, reasoning: Any, wonder_model: str, on_step: Any = None) -> Debate:
    t0 = time.perf_counter()
    f = facts(spec)
    calls: list[ModelCall] = []
    probs, psi = truth(spec)
    qs = questions(spec, probs)
    data = _ask(reasoning, PROPOSE, {"circuit": f, "questions": [q["question"] for q in qs]}, CLAIMS_SCHEMA, "claims", None, calls)
    claims = []
    for q, c in zip(qs, (data.get("claims") or [])[:3]):
        c = dict(c) | {"kind": q["kind"]}  # the question fixes what is being claimed; the model gives the value
        if "bits" in q:
            c["bits"] = q["bits"]
        if "qubits" in q:
            c["qubits"] = q["qubits"]
        claims.append(c)
    if on_step:
        on_step("claims", claims)
    data = _ask(reasoning, CHALLENGE, {"circuit": f, "claims": claims}, CHALLENGE_SCHEMA, "challenge", wonder_model, calls)
    responses = (data.get("responses") or [])[:len(claims)]
    responses += [{"agree": True, "reason": "no response"}] * (len(claims) - len(responses))
    if on_step:
        on_step("challenge", responses)
    disputed = [{"claim": c, "challenge": r} for c, r in zip(claims, responses)]
    data = _ask(reasoning, REPLY, {"circuit": f, "your_claims_and_the_challenges": disputed}, REPLY_SCHEMA, "replies", None, calls)
    replies = (data.get("replies") or [])[:len(claims)]
    replies += [{"stand": True, "reason": "no reply"}] * (len(claims) - len(replies))
    n = spec.num_qubits
    rows, first = [], 0
    final_right = caught = false_alarms = talked_out = 0
    for c, r, rep in zip(claims, responses, replies):
        ok, actual = check(c, probs, psi, n)
        first += ok
        agree = bool(r.get("agree", True))
        counter = None if agree else _counter(c, r)
        counter_ok = None if counter is None else check(counter, probs, psi, n)[0]
        final = c if (agree or bool(rep.get("stand", True))) else counter
        final_ok = check(final, probs, psi, n)[0]
        final_right += final_ok
        caught += (not ok) and (not agree) and bool(counter_ok)
        false_alarms += ok and not agree
        talked_out += ok and not agree and not bool(rep.get("stand", True))
        rows.append({"question": next((q["question"] for q in qs if q["kind"] == c.get("kind")), ""),
                     "claim": c, "claim_text": _describe(c), "truth": actual, "claim_right": ok,
                     "challenge": {"agree": agree, "reason": str(r.get("reason", ""))[:400],
                                   "counter": None if counter is None else _describe(counter), "right": counter_ok},
                     "reply": {"stand": bool(rep.get("stand", True)), "reason": str(rep.get("reason", ""))[:400]},
                     "final": _describe(final), "final_right": final_ok})
    return Debate(circuit=f, claims=rows, spark_first=first, final_right=final_right, caught=caught,
                  false_alarms=false_alarms, talked_out=talked_out, calls=calls, seconds=round(time.perf_counter() - t0, 1))


class Session:
    def __init__(self, spec: CircuitSpec, title: str):
        self.id = uuid.uuid4().hex[:12]
        self.spec, self.title = spec, title
        self.status = "running"
        self.error: str | None = None
        self.steps: list[dict[str, Any]] = []
        self.result: dict[str, Any] | None = None


def launch(s: Session, models: Any) -> None:
    st = models.settings
    if not (st.provider == "meta" and st.has_key):
        raise ValueError("a debate needs the live models (Muse Spark and Muse Wonder); the recorded benchmark is shown instead")

    def go() -> None:
        try:
            d = debate(s.spec, models.reasoning, st.deep_model, on_step=lambda k, v: s.steps.append({"step": k, "data": v}))
            s.result = d.model_dump(mode="json") | {"title": s.title}
            s.status = "done"
        except Exception as err:  # noqa: BLE001 - shown on the page
            s.status, s.error = "failed", str(err)[:400]

    threading.Thread(target=go, name=f"referee-{s.id}", daemon=True).start()


_sessions: dict[str, Session] = {}
_lock = threading.Lock()


def add(s: Session) -> None:
    with _lock:
        _sessions[s.id] = s
        while len(_sessions) > 10:
            _sessions.pop(next(iter(_sessions)))


def get(key: str) -> Session | None:
    with _lock:
        return _sessions.get(key)
