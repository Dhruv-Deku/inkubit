"""Offline reading of a plain-language description into a spec.

Muse Spark reads any description in live mode. Offline, this deterministic
parser understands named algorithms ("GHZ on 4 qubits", "Grover search",
"Bernstein-Vazirani with secret 1011", "QFT on 3 qubits"), explicit gate lists
("h 0; cx 0 1; rz pi/4 1") and simple networks ("300 km of fiber with 2
repeaters", "satellite link"). It never guesses beyond that: anything else is
an honest error that says what it understands.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from inkubit import EXAMPLES_DIR


class UnknownTextError(ValueError):
    """The offline parser does not understand the description."""


HELP = ("Offline mode understands named algorithms (Bell pair, GHZ on 4 qubits, Grover, Bernstein-Vazirani "
        "with secret 1011, Deutsch-Jozsa, phase estimation, superdense coding sending 10, Toffoli, QFT on 3 qubits, "
        "superposition on 3 qubits), gate lists such as 'h 0; cx 0 1; rz pi/4 1', and networks such as "
        "'300 km of fiber with 2 repeaters' or 'satellite link'. With a Meta key, Muse Spark reads any description.")

NETWORK_WORDS = re.compile(r"\b(satellite|fib(?:er|re)|repeaters?|ground stations?|km|kilomet|network|cities|city)\b", re.I)

_GATE_WORDS = {
    "h": "H", "x": "X", "y": "Y", "z": "Z", "s": "S", "t": "T", "sdg": "SDG", "tdg": "TDG", "sx": "SX",
    "rx": "RX", "ry": "RY", "rz": "RZ", "cx": "CX", "cnot": "CX", "cz": "CZ", "cp": "CP", "swap": "SWAP",
    "ccx": "CCX", "toffoli": "CCX", "measure": "MEASURE", "barrier": "BARRIER",
}
_ARITY = {"CX": (1, 1), "CZ": (1, 1), "CP": (1, 1), "CCX": (2, 1)}


def looks_like_network(text: str) -> bool:
    return bool(NETWORK_WORDS.search(text))


def _example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES_DIR / "specs" / f"{name}.json").read_text(encoding="utf-8"))


def _circuit(n: int, ops: list[dict[str, Any]], title: str, notes: str, measure: list[int] | None = None) -> dict[str, Any]:
    qubits = list(range(n)) if measure is None else measure
    return {"kind": "circuit", "version": "1.0", "num_qubits": n, "num_clbits": len(qubits), "operations": ops,
            "measurements": [{"qubit": q, "clbit": c} for c, q in enumerate(qubits)],
            "metadata": {"title": title, "notes": notes, "origin": "text"}}


def _with_origin(spec: dict[str, Any]) -> dict[str, Any]:
    spec.setdefault("metadata", {})["origin"] = "text"
    return spec


def _angle(token: str) -> float:
    t = token.lower().replace("π", "pi").replace(" ", "")
    m = re.fullmatch(r"(-?)(\d*\.?\d*)\*?pi(?:/(\d+(?:\.\d+)?))?", t)
    if m:
        k = float(m.group(2)) if m.group(2) else 1.0
        return (-1 if m.group(1) else 1) * k * math.pi / (float(m.group(3)) if m.group(3) else 1.0)
    return float(t)


def _number_after(text: str, words: str, default: int) -> int:
    m = re.search(rf"(\d+)\s*(?:-|\s)?(?:{words})|(?:{words})\D{{0,12}}?(\d+)", text, re.I)
    if not m:
        return default
    return int(m.group(1) or m.group(2))


def _qft_ops(qubits: list[int]) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    n = len(qubits)
    for j in reversed(range(n)):
        ops.append({"gate": "H", "targets": [qubits[j]]})
        for k in reversed(range(j)):
            ops.append({"gate": "CP", "controls": [qubits[k]], "targets": [qubits[j]],
                        "params": [math.pi / 2 ** (j - k)]})
    for i in range(n // 2):
        ops.append({"gate": "SWAP", "targets": [qubits[i], qubits[n - 1 - i]]})
    return ops


def _named_circuit(text: str) -> tuple[dict[str, Any], str] | None:
    t = text.lower()
    # feed-forward first: "teleportation with feed-forward" must not fall through to a plain Bell pair
    ff = bool(re.search(r"feed.?forward|mid.?circuit|classical(?:ly)?.control|dynamic circuit|if.?test|syndrome", t))
    qec = bool(re.search(r"bit.?flip|error.?correct|syndrome|repetition code", t))
    if ff and "teleport" in t:
        return _with_origin(_example("teleportation_feedforward")), "teleportation with feed-forward"
    if ff and qec:
        return _with_origin(_example("bit_flip_feedforward")), "a bit-flip code with a measured syndrome and feed-forward correction"
    if "active reset" in t or (ff and "reset" in t):
        return _with_origin(_example("active_reset")), "an active reset (measure, then flip back if it read 1)"
    if re.search(r"\bbell\b|epr pair", t):
        return _with_origin(_example("bell")), "a Bell pair"
    if "ghz" in t or "cat state" in t:
        n = max(2, min(12, _number_after(t, "qubits?|qubit|-qubit", 3)))
        ops = [{"gate": "H", "targets": [0]}] + [{"gate": "CX", "controls": [q], "targets": [q + 1]} for q in range(n - 1)]
        return _circuit(n, ops, f"GHZ-{n}", f"{n} qubits that are all 0 or all 1 together."), f"a GHZ state on {n} qubits"
    if "shor" in t or re.search(r"\bfactor(ing|ise|ize)?\b.*\b(15|fifteen)\b", t):
        from inkubit.shor import COPRIME, shor_spec

        m = re.search(r"\b(?:a|base)\s*(?:=|is|of)?\s*(\d{1,2})\b", t)
        a = int(m.group(1)) if m and int(m.group(1)) in COPRIME else 7
        return _with_origin(shor_spec(a)), f"Shor's algorithm factoring 15 with a = {a}"
    if "grover" in t:
        return _with_origin(_example("grover2")), "Grover search over 2 qubits (marked item 11)"
    if "bernstein" in t or re.search(r"\bbv\b", t):
        m = re.search(r"\b([01]{1,10})\b", t)
        secret = m.group(1) if m else "101"
        n = len(secret)
        anc = n
        ops: list[dict[str, Any]] = [{"gate": "X", "targets": [anc]}, {"gate": "H", "targets": list(range(n + 1))}]
        # secret written most significant first, like a bitstring: its last character is qubit 0
        ops += [{"gate": "CX", "controls": [q], "targets": [anc]} for q in range(n) if secret[n - 1 - q] == "1"]
        ops.append({"gate": "H", "targets": list(range(n))})
        return (_circuit(n + 1, ops, f"Bernstein-Vazirani (secret {secret})",
                         f"Reads the hidden string {secret} in one query; q{anc} is the helper qubit.", list(range(n))),
                f"Bernstein-Vazirani with secret {secret}")
    if "deutsch" in t:
        if "constant" in t:
            ops = [{"gate": "X", "targets": [2]}, {"gate": "H", "targets": [0, 1, 2]}, {"gate": "H", "targets": [0, 1]}]
            return (_circuit(3, ops, "Deutsch-Jozsa (constant)", "A constant oracle: the inputs read 00.", [0, 1]),
                    "Deutsch-Jozsa with a constant oracle")
        return _with_origin(_example("deutsch_jozsa")), "Deutsch-Jozsa with a balanced oracle"
    if "phase estimation" in t or re.search(r"\bqpe\b", t):
        return _with_origin(_example("phase_estimation")), "phase estimation of the T gate"
    if "superdense" in t or "dense coding" in t:
        m = re.search(r"\b([01]{2})\b", t)
        bits = m.group(1) if m else "11"
        ops = [{"gate": "H", "targets": [0]}, {"gate": "CX", "controls": [0], "targets": [1]}]
        # Qiskit order: the message reads c1 c0; Bob's decoding puts Alice's Z on q0 and her X on q1
        if bits[1] == "1":
            ops.append({"gate": "Z", "targets": [0]})
        if bits[0] == "1":
            ops.append({"gate": "X", "targets": [0]})
        ops += [{"gate": "CX", "controls": [0], "targets": [1]}, {"gate": "H", "targets": [0]}]
        return (_circuit(2, ops, f"Superdense coding (sends {bits})", f"Two classical bits ({bits}) sent with one qubit."),
                f"superdense coding sending {bits}")
    if "toffoli" in t or "quantum and" in t:
        return _with_origin(_example("toffoli_and")), "a Toffoli acting as a quantum AND"
    if re.search(r"\bqft\b|fourier", t):
        n = max(1, min(8, _number_after(t, "qubits?|qubit|-qubit", 3)))
        m = re.search(r"\bof\s+(\d+)\b", t)
        value = int(m.group(1)) % (2 ** n) if m else 1
        prep = [{"gate": "X", "targets": [q]} for q in range(n) if value >> q & 1]
        return (_circuit(n, prep + _qft_ops(list(range(n))), f"QFT on {n} qubits (input {value})",
                         f"Quantum Fourier transform of |{value}⟩: equal probabilities, information in the phases."),
                f"a quantum Fourier transform of {value} on {n} qubits")
    if "superposition" in t or "uniform" in t or "hadamard" in t:
        n = max(1, min(12, _number_after(t, "qubits?|qubit|-qubit", 2)))
        return (_circuit(n, [{"gate": "H", "targets": list(range(n))}], f"Uniform superposition ({n} qubits)",
                         f"Every one of the {2 ** n} outcomes equally likely."), f"a uniform superposition of {n} qubits")
    return None


def _gate_list(text: str) -> tuple[dict[str, Any], str] | None:
    parts = [p.strip() for p in re.split(r"[;\n]|,(?=\s*[a-z])", text.strip(), flags=re.I) if p.strip()]
    if not parts:
        return None
    ops: list[dict[str, Any]] = []
    measure: list[int] | None = None
    highest = -1
    for part in parts:
        tokens = re.split(r"[\s,()]+", part.strip().lower())
        tokens = [t for t in tokens if t and t not in ("on", "q", "qubit", "qubits", "and", "->", "to")]
        if not tokens or tokens[0] not in _GATE_WORDS:
            return None
        gate = _GATE_WORDS[tokens[0]]
        rest = tokens[1:]
        if gate == "MEASURE":
            if rest and rest[0] != "all":
                measure = [int(x.lstrip("q")) for x in rest]
            continue
        params = []
        if gate in ("RX", "RY", "RZ", "CP"):
            if not rest:
                return None
            params = [_angle(rest[0])]
            rest = rest[1:]
        try:
            qs = [int(x.lstrip("q")) for x in rest]
        except ValueError:
            return None
        if not qs and gate != "BARRIER":
            return None
        highest = max([highest, *qs])
        if gate in _ARITY:
            nc, nt = _ARITY[gate]
            if len(qs) != nc + nt:
                return None
            ops.append({"gate": gate, "controls": qs[:nc], "targets": qs[nc:], "params": params})
        elif gate == "SWAP":
            ops.append({"gate": "SWAP", "targets": qs})
        else:
            ops.append({"gate": gate, "targets": qs, "params": params})
    if not ops:
        return None
    n = max(highest + 1, max(measure or [0]) + 1)
    return _circuit(n, ops, "From your gate list", "Typed as a gate list.", measure), f"a gate list of {len(ops)} operations"


def _network(text: str) -> tuple[dict[str, Any], str] | None:
    t = text.lower()
    if "satellite" in t:
        return _with_origin(_example("network_satellite")), "the satellite downlink preset (Micius-like geometry)"
    km = re.search(r"(\d+(?:\.\d+)?)\s*(?:km|kilomet)", t)
    if not km:
        return None
    total = float(km.group(1))
    reps = _number_after(t, "repeaters?|relays?|nodes?", 0) if re.search(r"repeater|relay", t) else 0
    medium = "free_space" if re.search(r"free[- ]space|laser|optical link", t) else "fiber"
    ids = ["a"] + [f"r{i}" for i in range(1, reps + 1)] + ["b"]
    nodes = [{"id": i, "type": "ground_station" if i in ("a", "b") else "repeater",
              "label": {"a": "Station A", "b": "Station B"}.get(i, f"Repeater {i[1:]}"),
              **({"memory_t2_ms": 100.0} if i not in ("a", "b") else {})} for i in ids]
    span = round(total / (reps + 1), 1)
    links = [{"from": ids[k], "to": ids[k + 1], "medium": medium, "length_km": span} for k in range(len(ids) - 1)]
    title = f"{total:g} km of {medium.replace('_', ' ')}" + (f" with {reps} repeater{'s' if reps != 1 else ''}" if reps else "")
    spec = {"kind": "network", "version": "1.0", "nodes": nodes, "links": links, "source": "a", "destination": "b",
            "metadata": {"title": title, "notes": "Equal spans; repeaters get 100 ms memories.", "origin": "text"}}
    return spec, title


def parse_description(text: str) -> tuple[dict[str, Any], str]:
    """(spec dict, how it was read) for a description, or UnknownTextError."""
    text = text.strip()
    if not text:
        raise UnknownTextError("Describe a circuit or a network first.")
    for reader in ((_network, _named_circuit, _gate_list) if looks_like_network(text)
                   else (_gate_list, _named_circuit, _network)):
        found = reader(text)
        if found:
            return found
    raise UnknownTextError(f"Could not read that offline. {HELP}")
