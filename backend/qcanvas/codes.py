"""Code lab: Muse Spark designs quantum error-correcting codes; exact checks prove what each one can correct.

A stabilizer code on n qubits is given by Pauli generators (strings of I, X, Y, Z, qubit 0 leftmost). Every proposal
is checked exactly, in the binary symplectic picture (X part | Z part):

* the generators must commute pairwise and be independent over GF(2); then the code encodes k = n - rank qubits;
* the distance d is the smallest weight of a Pauli that commutes with every generator but is not itself in the
  stabilizer group (an undetectable logical error), found by brute force from weight 1 up, every X/Y/Z choice;
* dZ and dX are the same with only Z (only X) errors allowed: what matters when one kind of noise dominates;
* CSS: every generator is all-X or all-Z.

The search runs in rounds like the learning loop: each round Muse Spark proposes up to three codes for a target and
sees every earlier verdict. Known codes (the five-qubit perfect code, Steane, Shor, the rotated surface code and its
XZZX version) are scored by the same checker, so every number on the page, ours or a textbook's, is computed here.
"""

from __future__ import annotations

import itertools
import json
from typing import Any

import numpy as np
from pydantic import BaseModel

from qcanvas.adapters.base import ModelCall

MAX_N = 11
ROUNDS = 4
PER_ROUND = 3


class Target(BaseModel):
    id: str
    title: str
    n: int
    k: int
    goal: str  # what to maximise, in words for the model
    css: bool = False
    objective: str = "d"  # d | dz (with d >= 3)


TARGETS = {
    "five": Target(id="five", title="One logical qubit in 5 physical qubits", n=5, k=1,
                   goal="maximise the distance d (the code should correct any error on one qubit)"),
    "seven_css": Target(id="seven_css", title="A CSS code: 1 logical qubit in 7", n=7, k=1, css=True,
                        goal="maximise the distance d using only all-X and all-Z generators (a CSS code)"),
    "biased": Target(id="biased", title="Biased noise: 1 logical qubit in 9", n=9, k=1, objective="dz",
                     goal="keep the distance d at least 3 and maximise dZ, the distance against Z errors alone "
                          "(for hardware where phase flips are far more common than bit flips)"),
}


def _vec(p: str) -> np.ndarray:
    x = [c in "XY" for c in p]
    z = [c in "ZY" for c in p]
    return np.array(x + z, dtype=np.uint8)


def _rank(m: np.ndarray) -> int:
    a = m.copy() % 2
    r = 0
    for c in range(a.shape[1]):
        piv = next((i for i in range(r, a.shape[0]) if a[i, c]), None)
        if piv is None:
            continue
        a[[r, piv]] = a[[piv, r]]
        for i in range(a.shape[0]):
            if i != r and a[i, c]:
                a[i] ^= a[r]
        r += 1
        if r == a.shape[0]:
            break
    return r


def _anticommute(a: np.ndarray, b: np.ndarray, n: int) -> int:
    return int((a[:n] @ b[n:] + a[n:] @ b[:n]) % 2)


class Verdict(BaseModel):
    generators: list[str]
    valid: bool
    note: str = ""
    n: int = 0
    k: int = 0
    d: int | None = None
    dx: int | None = None
    dz: int | None = None
    css: bool = False
    logical: str | None = None  # a minimum-weight logical operator, as a Pauli string


def analyse(gens: list[str], n: int | None = None) -> Verdict:
    """Commutation, independence, k, and the exact distances of a stabilizer code."""
    gens = [g.strip().upper().replace(" ", "") for g in gens if g and g.strip()]
    n = n or (len(gens[0]) if gens else 0)
    base = Verdict(generators=gens, valid=False, n=n)
    if not gens or not 1 <= n <= MAX_N:
        return base.model_copy(update={"note": f"needs 1 to {MAX_N} qubits"})
    if any(len(g) != n or set(g) - set("IXYZ") for g in gens):
        return base.model_copy(update={"note": f"every generator must be {n} characters of I, X, Y, Z"})
    m = np.array([_vec(g) for g in gens])
    for i, j in itertools.combinations(range(len(gens)), 2):
        if _anticommute(m[i], m[j], n):
            return base.model_copy(update={"note": f"generators {i + 1} and {j + 1} anticommute"})
    r = _rank(m)
    if r < len(gens):
        return base.model_copy(update={"note": f"the generators are not independent (rank {r} of {len(gens)})"})
    k = n - r
    if k < 1:
        return base.model_copy(update={"note": "no logical qubit left (k = 0)"})
    css = all(set(g) <= {"I", "X"} or set(g) <= {"I", "Z"} for g in gens)
    # the stabilizer group, as integers over the 2n bits
    weights = 1 << np.arange(2 * n, dtype=np.int64)
    rows = (m.astype(np.int64) * weights).sum(1)
    group = {0}
    for row in rows:
        group |= {g ^ int(row) for g in group}
    best: dict[str, tuple[int, str] | None] = {"all": None, "x": None, "z": None}
    for w in range(1, n + 1):
        for support in itertools.combinations(range(n), w):
            for paulis in itertools.product("XYZ", repeat=w):
                kinds = set(paulis)
                todo = [key for key in ("all", "x", "z") if best[key] is None
                        and (key == "all" or kinds == {key.upper()})]
                if not todo:
                    continue
                v = np.zeros(2 * n, dtype=np.uint8)
                for q, p in zip(support, paulis):
                    v[q] = p in "XY"
                    v[n + q] = p in "ZY"
                if ((m[:, :n] @ v[n:] + m[:, n:] @ v[:n]) % 2).any():
                    continue  # detected
                if int((v.astype(np.int64) * weights).sum()) in group:
                    continue  # a stabilizer: harmless
                s = ["I"] * n
                for q, p in zip(support, paulis):
                    s[q] = p
                for key in todo:
                    best[key] = (w, "".join(s))
        if all(best[key] is not None for key in ("all", "x", "z")):
            break
    d = best["all"]
    return Verdict(generators=gens, valid=True, n=n, k=k, d=d[0] if d else None, logical=d[1] if d else None,
                   dx=best["x"][0] if best["x"] else None, dz=best["z"][0] if best["z"] else None, css=css)


def _surface(xz_swap_odd: bool = False) -> list[str]:
    from qcanvas.decoder import X_CHECKS, Z_CHECKS

    out = []
    for checks, p in ((X_CHECKS, "X"), (Z_CHECKS, "Z")):
        for c in checks:
            s = ["I"] * 9
            for q in c:
                odd = (q // 3 + q % 3) % 2 == 1
                s[q] = ({"X": "Z", "Z": "X"}[p]) if (xz_swap_odd and odd) else p
            out.append("".join(s))
    return out


REFERENCES = {
    "Five-qubit perfect code": ["XZZXI", "IXZZX", "XIXZZ", "ZXIXZ"],
    "Steane code": ["IIIXXXX", "IXXIIXX", "XIXIXIX", "IIIZZZZ", "IZZIIZZ", "ZIZIZIZ"],
    "Shor code": ["ZZIIIIIII", "IZZIIIIII", "IIIZZIIII", "IIIIZZIII", "IIIIIIZZI", "IIIIIIIZZ", "XXXXXXIII", "IIIXXXXXX"],
    "Rotated surface code, d = 3": _surface(),
    "XZZX surface code, d = 3": _surface(xz_swap_odd=True),
}


def references() -> list[dict[str, Any]]:
    return [{"name": name} | analyse(g).model_dump() for name, g in REFERENCES.items()]


SCHEMA = {"type": "object", "additionalProperties": False, "required": ["codes"], "properties": {
    "codes": {"type": "array", "maxItems": PER_ROUND, "items": {
        "type": "object", "additionalProperties": False, "required": ["generators", "why"], "properties": {
            "generators": {"type": "array", "items": {"type": "string"},
                           "description": "n - k Pauli strings of I, X, Y, Z, each n characters, qubit 0 leftmost."},
            "why": {"type": "string", "description": "One sentence: the idea behind this code."}}}}}}
SYSTEM = ("You design quantum stabilizer codes. Give each code as n - k independent, pairwise commuting Pauli "
          "generators, each a string of n characters from I, X, Y, Z (qubit 0 leftmost). Propose up to three codes per "
          "round with a one-sentence idea each. Do not compute distances: exact checks do, and you will see every "
          "earlier code and its verdict (invalid and why, or its exact distances). Learn from them: fix what failed, "
          "improve on the best, and do not repeat a code.")


def score(t: Target, v: Verdict) -> float | None:
    """Higher is better; None when the code does not meet the target's rules."""
    if not v.valid or v.n != t.n or v.k != t.k or (t.css and not v.css) or v.d is None:
        return None
    if t.objective == "dz":
        return (v.dz or 0) + 0.001 * v.d if v.d >= 3 else None
    return float(v.d)


def _describe(t: Target, v: Verdict) -> str:
    if not v.valid:
        return f"invalid: {v.note}"
    base = f"valid [[{v.n},{v.k},{v.d}]], dX = {v.dx}, dZ = {v.dz}{', CSS' if v.css else ''}"
    if v.n != t.n or v.k != t.k:
        return base + f" (but the target is n = {t.n}, k = {t.k})"
    if t.css and not v.css:
        return base + " (but not CSS)"
    return base


class CodeRound(BaseModel):
    round: int
    codes: list[dict[str, Any]]
    best: dict[str, Any] | None


def run(t: Target, reasoning: Any, rounds: int = ROUNDS, on_round: Any = None) -> dict[str, Any]:
    history: list[dict[str, Any]] = []
    out: list[CodeRound] = []
    calls: list[ModelCall] = []
    best: dict[str, Any] | None = None
    seen: set[tuple[str, ...]] = set()
    for r in range(1, rounds + 1):
        user = {"target": {"n": t.n, "k": t.k, "aim": t.goal}, "round": r,
                "best_so_far": None if best is None else {"generators": best["generators"], "verdict": best["verdict"]},
                "earlier_codes": [{"generators": h["generators"], "verdict": h["verdict"]} for h in history]}
        data = {}
        for attempt, budget in enumerate((16000, 32000)):  # a long answer can be cut off; retry with more room
            try:
                data, call = reasoning.structured(SYSTEM, json.dumps(user | ({"retry": 1} if attempt else {})), SCHEMA,
                                                  "codes", effort="medium", max_tokens=budget)
                calls.append(call)
                break
            except Exception:  # noqa: BLE001
                if attempt:
                    raise
        codes = []
        for c in (data.get("codes") or [])[:PER_ROUND]:
            gens = [str(g) for g in c.get("generators") or []]
            key = tuple(g.strip().upper() for g in gens)
            v = analyse(gens) if key not in seen else Verdict(generators=gens, valid=False, note="already proposed")
            seen.add(key)
            sc = score(t, v)
            entry = {"generators": v.generators, "why": str(c.get("why", ""))[:200], "verdict": _describe(t, v),
                     "score": sc} | v.model_dump(exclude={"generators"})
            codes.append(entry)
            history.append(entry)
            if sc is not None and (best is None or sc > best["score"]):
                best = entry
        rd = CodeRound(round=r, codes=codes, best=best)
        out.append(rd)
        if on_round:
            on_round(t.id, rd)
    return {"target": t.model_dump(), "rounds": [x.model_dump() for x in out],
            "curve": [None if x.best is None else (x.best["dz"] if t.objective == "dz" else x.best["d"]) for x in out],
            "best": best, "calls": [c.model_dump(mode="json") for c in calls]}
