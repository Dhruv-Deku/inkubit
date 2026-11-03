"""Ask Inkubit: one assistant for the whole lab, whose every number comes from an exact tool.

Muse Spark gets the question and a set of tools, each a thin wrapper over an exact engine in this repository
(circuit simulation with realistic noise, the optimizer with proofs, H2 from first principles, BB84, QAOA Max-Cut,
Shor, the quantum-network model, the error-correction lab). It decides which tools to call and with what arguments
(tool calling on Chat Completions, docs/meta-api/tool-calling.md), the tools run, their results go back, and it
answers in words. It is told never to compute a quantum result itself.

Then every number in the answer is traced: each one must match a number in a tool result (at the precision written,
or as a percentage) or in the question. The page shows how many were traced and lists any that were not, so a
number the model made up is visible instead of trusted. Offline, a keyword router stands in for the model, labelled
as such; it reaches the same tools.
"""

from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Callable

import numpy as np
from pydantic import BaseModel, Field

from inkubit.adapters.base import ModelCall

MAX_ROUNDS = 4
DEEP_ROUNDS = 6  # Muse Wonder plans longer chains of tool calls
GATES = ["H", "X", "Y", "Z", "S", "T", "SDG", "TDG", "SX", "RX", "RY", "RZ", "CX", "CZ", "CP", "SWAP", "CCX"]

SYSTEM = (
    "You are Inkubit, a quantum computing lab assistant. You never work out a quantum result yourself, not even a "
    "simple one: call the tools, which are exact simulations, and use only the numbers they return. Pick the tool "
    "that fits: circuits and algorithms (simulate_circuit, optimize_circuit), molecules (molecule_h2), secure keys "
    "and eavesdroppers (quantum_key_distribution), splitting people or tasks into two groups, scheduling and routing "
    "conflicts (max_cut), factoring (factor_with_shor), quantum networks and links (plan_quantum_link), error "
    "correction (error_correction), and reading or writing quantum notation: a ket such as (|01⟩−|10⟩)/√2, "
    "OpenQASM, Quil or Qiskit code, or 'what circuit makes this state' (translate_notation). Several tools may be called, also in parallel, for comparisons. Circuits use "
    "Qiskit conventions: qubits start in |0>, angles in radians, bitstrings with qubit 0 on the right. After the "
    "tools return, answer in 2 to 5 plain sentences for a curious student: the result, what it means, and one "
    "honest caveat when there is one. Quote numbers exactly as the tools give them (you may round, and you may say "
    "a share as a percentage). No headings, no LaTeX. If no tool fits, say what Inkubit can do instead."
)


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required}}}


_OPS = {"type": "array", "description": "Gates in order.", "items": {"type": "object", "properties": {
    "gate": {"type": "string", "enum": GATES},
    "targets": {"type": "array", "items": {"type": "integer"}},
    "controls": {"type": "array", "items": {"type": "integer"}},
    "params": {"type": "array", "items": {"type": "number"}, "description": "Angles in radians (RX, RY, RZ, CP)."},
}, "required": ["gate", "targets"]}}

TOOLS = [
    _fn("simulate_circuit", "Run a quantum circuit exactly: outcome probabilities with perfect qubits and with "
        "realistic superconducting noise, and whether the qubits end entangled.",
        {"num_qubits": {"type": "integer", "minimum": 1, "maximum": 10}, "operations": _OPS,
         "measure": {"type": "array", "items": {"type": "integer"}, "description": "Qubits to measure; default all."},
         "title": {"type": "string", "description": "A short name for the circuit."}},
        ["num_qubits", "operations"]),
    _fn("optimize_circuit", "Find a shorter circuit with exactly the same measured odds (rewrite rules and the "
        "Qiskit compiler, each result proven by exact simulation).",
        {"num_qubits": {"type": "integer", "minimum": 1, "maximum": 8}, "operations": _OPS,
         "measure": {"type": "array", "items": {"type": "integer"}}}, ["num_qubits", "operations"]),
    _fn("molecule_h2", "The hydrogen molecule from first principles at a bond length: exact energy, the "
        "Hartree-Fock approximation, and VQE on a quantum computer with realistic noise, raw and mitigated.",
        {"bond_length_angstrom": {"type": "number", "minimum": 0.3, "maximum": 3.0}}, ["bond_length_angstrom"]),
    _fn("quantum_key_distribution", "BB84 secret-key exchange with an eavesdropper who measures a share of the "
        "photons: error rate, whether she is caught (abort above 11%), and the secret key length.",
        {"eavesdrop_share": {"type": "number", "minimum": 0, "maximum": 1},
         "channel_noise": {"type": "number", "minimum": 0, "maximum": 0.2, "description": "Default 0.01."},
         "photons": {"type": "integer", "minimum": 100, "maximum": 100000, "description": "Default 4000."}},
        ["eavesdrop_share"]),
    _fn("max_cut", "Split people (or tasks) into two groups so that as many conflicting pairs as possible are "
        "separated, with QAOA on a quantum computer and the exact best answer for comparison. 3 to 8 names.",
        {"names": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8},
         "conflicts": {"type": "array", "items": {"type": "array", "items": {"type": "string"}, "minItems": 2,
                                                    "maxItems": 2}, "description": "Pairs of names that clash."}},
        ["names", "conflicts"]),
    _fn("factor_with_shor", "Shor's algorithm factoring 15 with a chosen base a (2 to 14): period, the odds a run "
        "succeeds with perfect and with noisy qubits, and the factors.",
        {"a": {"type": "integer", "minimum": 2, "maximum": 14}}, ["a"]),
    _fn("plan_quantum_link", "A quantum network link between two stations: entangled-pair rate, fidelity and key "
        "rate, the weakest part, and the best fix found by re-simulating candidate fixes.",
        {"distance_km": {"type": "number", "minimum": 1, "maximum": 5000},
         "medium": {"type": "string", "enum": ["fiber", "free_space", "satellite"]},
         "repeaters": {"type": "integer", "minimum": 0, "maximum": 6}}, ["distance_km", "medium"]),
    _fn("error_correction", "The three-qubit bit-flip code against a bare qubit: the physical error rate above "
        "which the code starts to help (break-even), for gates of a given quality.",
        {"gate_quality": {"type": "number", "minimum": 0.05, "maximum": 10,
                          "description": "1 = today's realistic gates, 0.1 = ten times better, 2 = twice as noisy."}},
        ["gate_quality"]),
    _fn("translate_notation", "Quantum Rosetta: read quantum notation exactly (a Dirac ket like (|01⟩−|10⟩)/√2 or "
        "cos(π/8)|0⟩+sin(π/8)|1⟩, named states |Φ+⟩ |GHZ⟩ |W⟩, OpenQASM, Quil, or Qiskit calls like qc.h(0)) and "
        "return the state in Dirac notation, which qubits are entangled, a circuit proven to prepare it, and code in "
        "eight languages.",
        {"text": {"type": "string", "description": "The notation, copied exactly."}}, ["text"]),
]


class ToolRun(BaseModel):
    name: str
    args: dict[str, Any]
    facts: dict[str, Any] = Field(default_factory=dict)
    card: dict[str, Any] | None = None
    error: str | None = None
    seconds: float = 0.0


class Trace(BaseModel):
    checked: int
    traced: int
    given: int
    untraced: list[str]


class Reply(BaseModel):
    answer: str
    tools: list[ToolRun]
    trace: Trace
    calls: list[ModelCall]
    router: str  # "muse" or "offline"


def _r(x: float, k: int = 4) -> float:
    return float(round(x, k))


# ---------------------------------------------------------------- the tools

def _circuit_spec(a: dict[str, Any]) -> dict[str, Any]:
    n = int(a["num_qubits"])
    ops = []
    for o in a.get("operations") or []:
        ops.append({"gate": str(o.get("gate", "")).upper(), "targets": [int(t) for t in o.get("targets") or []],
                    "controls": [int(c) for c in o.get("controls") or []],
                    "params": [float(p) for p in o.get("params") or []]})
    measure = a.get("measure") or list(range(n))
    return {"kind": "circuit", "version": "1.0", "num_qubits": n, "num_clbits": len(measure), "operations": ops,
            "measurements": [{"qubit": int(q), "clbit": i} for i, q in enumerate(measure)],
            "metadata": {"title": str(a.get("title") or "Circuit from Ask Inkubit")[:80], "origin": "text"}}


def t_simulate(a: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from inkubit.insights.circuit import MAX_NOISY_QUBITS
    from inkubit.spec import parse_spec
    from inkubit.verify.expected import build_reference_circuit, ideal_distribution, noisy_distribution
    from qiskit.quantum_info import Statevector, entropy, partial_trace

    spec = parse_spec(_circuit_spec(a))
    ideal = ideal_distribution(spec)
    noisy = noisy_distribution(spec, "realistic") if spec.num_qubits <= MAX_NOISY_QUBITS else None
    sv = Statevector.from_instruction(build_reference_circuit(spec))
    ent = [q for q in range(spec.num_qubits) if spec.num_qubits > 1 and
           entropy(partial_trace(sv, [k for k in range(spec.num_qubits) if k != q]), base=2) > 1e-6]
    top = sorted(ideal.items(), key=lambda kv: -kv[1])[:8]
    facts = {"outcomes_perfect": {k: _r(v) for k, v in top},
             "outcomes_realistic_noise": {k: _r(noisy.get(k, 0.0)) for k, _ in top} if noisy else None,
             "realistic_noise_share_lost": _r(1 - sum(noisy.get(k, 0.0) for k in ideal), 4) if noisy else None,
             "entangled_qubits": ent, "gates": len(spec.operations)}
    card = {"type": "circuit", "spec": spec.model_dump(mode="json", by_alias=True, exclude_none=True),
            "ideal": ideal, "noisy": noisy}
    return facts, card


def t_optimize(a: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from inkubit.optimize import optimize
    from inkubit.spec import parse_spec

    spec = parse_spec(_circuit_spec(a))
    res = optimize(spec, None, "")
    best = res.candidates[res.best] if res.best is not None else None
    facts = {"original": {"gates": res.original.gates, "two_qubit": res.original.two_qubit, "depth": res.original.depth},
             "best": ({"by": best.label, "gates": best.cost.gates, "two_qubit": best.cost.two_qubit,
                       "depth": best.cost.depth, "proof": best.proof.level if best.proof else None}
                      if best and best.cost else None),
             "summary": res.summary}
    card = {"type": "optimize", "original": res.original.model_dump(), "best": best.model_dump(mode="json") if best else None,
            "summary": res.summary, "spec": spec.model_dump(mode="json", by_alias=True, exclude_none=True)}
    return facts, card


def t_molecule(a: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from inkubit.chem import chem_lab

    r = min(3.0, max(0.3, round(float(a["bond_length_angstrom"]), 2)))
    lab = chem_lab(round(r, 2))
    facts = {"bond_length_angstrom": lab.r, "exact_energy_hartree": _r(lab.exact), "hartree_fock_hartree": _r(lab.hf),
             "hartree_fock_error_mhartree": _r((lab.hf - lab.exact) * 1000, 1),
             "vqe_raw_hartree": _r(lab.vqe), "vqe_raw_error_mhartree": _r((lab.vqe - lab.exact) * 1000, 1),
             "vqe_mitigated_hartree": _r(lab.mitigated), "vqe_mitigated_error_mhartree": _r(abs(lab.mitigated - lab.exact) * 1000, 1),
             "chemical_accuracy_mhartree": 1.6, "antibonding_share": _r(lab.weight_u, 3),
             "noise": lab.noise_label, "shots_per_term": lab.shots,
             "note": "minimal basis: exactly solvable on a laptop; this shows the method"}
    return facts, {"type": "chem", "lab": lab.model_dump(mode="json")}


def t_qkd(a: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from inkubit.qkd import bb84

    lab = bb84(int(a.get("photons") or 4000), float(a["eavesdrop_share"]), float(a.get("channel_noise", 0.01) or 0.0), 7)
    facts = {"photons": lab.photons, "kept_after_basis_check": lab.sifted, "bits_revealed_to_check": lab.checked,
             "error_rate": _r(lab.qber), "error_rate_uncertainty": _r(lab.qber_err), "expected_error_rate": _r(lab.expected_qber),
             "abort_threshold": 0.11, "eavesdropper_caught": lab.caught, "secret_key_bits": lab.key_bits,
             "eavesdropper_guessed_share_of_kept_bits": _r(lab.eve_knows, 3), "eavesdrop_share": lab.eve}
    return facts, {"type": "qkd", "lab": lab.model_dump(mode="json")}


def t_maxcut(a: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from inkubit.qaoa import qaoa_lab

    names = [str(x).strip()[:12] for x in a["names"]][:8]
    index = {n.lower(): i for i, n in enumerate(names)}
    edges = []
    for pair in a.get("conflicts") or []:
        if len(pair) == 2 and str(pair[0]).strip().lower() in index and str(pair[1]).strip().lower() in index:
            edges.append((index[str(pair[0]).strip().lower()], index[str(pair[1]).strip().lower()]))
    lab = qaoa_lab(len(names), edges, "realistic", names)
    d3 = lab.depths[-1]
    best = d3.top[0]
    facts = {"conflicts": len(lab.edges), "best_possible_separated": lab.max_cut, "ways_to_reach_best": lab.optimal_count,
             "qaoa_most_likely_split": {"group_a": [names[i] for i, t in enumerate(best.teams) if t == 0],
                                        "group_b": [names[i] for i, t in enumerate(best.teams) if t == 1],
                                        "separated": best.cut, "probability": _r(best.prob, 3)},
             "qaoa_by_layers": [{"layers": d.p, "expected_share_of_best": _r(d.ratio, 3), "chance_of_a_best_split": _r(d.p_best, 3),
                                 "chance_with_realistic_noise": _r(d.p_best_noisy or 0, 3)} for d in lab.depths],
             "random_split_expected_share": _r(lab.random_ratio, 3),
             "note": "small enough to check every split by brute force; this shows the method, not a speedup"}
    return facts, {"type": "maxcut", "lab": lab.model_dump(mode="json"), "names": names}


def t_shor(a: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from inkubit.shor import shor_lab

    lab = shor_lab(int(a["a"]))
    good = [o for o in lab.outcomes if o.ok]
    facts = {"a": lab.a, "shares_a_factor_with_15": not lab.coprime, "gcd_shortcut": lab.shortcut, "period": lab.period,
             "factors": good[0].factors if good else None,
             "success_per_run_perfect": _r(lab.success_ideal, 3), "success_per_run_noisy": _r(lab.success_noisy, 3),
             "note": "factoring 15 classically is instant; this shows the mechanism"}
    return facts, {"type": "shor", "lab": lab.model_dump(mode="json")}


def t_link(a: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from inkubit.network.agent import run_network_agent
    from inkubit.spec import parse_spec
    from inkubit.textspec import _network

    medium = a.get("medium", "fiber")
    dist = float(a["distance_km"])
    reps = int(a.get("repeaters") or 0)
    text = "satellite link" if medium == "satellite" else \
        f"{dist:g} km of {'free-space laser' if medium == 'free_space' else 'fiber'}" + (f" with {reps} repeaters" if reps else "")
    found = _network(text)
    if found is None:
        raise ValueError("could not build that link")
    spec = parse_spec(found[0])
    res = run_network_agent(spec)

    def e2e(m: Any) -> dict[str, Any]:
        e = m.end_to_end
        return {"pairs_per_second": float(f"{e.pair_rate_hz:.3g}"), "fidelity": _r(e.fidelity, 3), "error_rate": _r(e.qber, 3),
                "secret_key_bits_per_second": float(f"{e.key_rate_bps:.3g}")}
    facts = {"link": found[1], "before": e2e(res.before), "after_best_fix": e2e(res.after) if res.after else None,
             "fix": res.fix.description if res.fix else None,
             "summary": res.summary}
    return facts, {"type": "network", "result": res.model_dump(mode="json"), "title": found[1]}


def t_qec(a: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from inkubit.qec import repetition_lab

    q = min(10.0, max(0.05, float(a["gate_quality"])))
    lab = repetition_lab(float(f"{q:.3g}"))
    be = lab.bit.break_even
    facts = {"gate_quality": q, "break_even_physical_error": _r(be, 5) if be is not None else None,
             "summary": lab.summary}
    return facts, {"type": "qec", "lab": lab.model_dump(mode="json")}


def t_translate(a: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from inkubit.rosetta import statevector, translate
    from inkubit.spec import parse_spec

    res = translate(str(a["text"]), None, with_languages=False)
    spec = parse_spec(res.spec)
    sv = statevector(spec)  # type: ignore[arg-type]
    n = spec.num_qubits
    probs = np.abs(sv) ** 2
    top = sorted((i for i in range(len(sv)) if probs[i] > 1e-10), key=lambda i: -probs[i])[:8]
    ops = [o for o in spec.operations if o.gate not in ("MEASURE", "BARRIER")]  # type: ignore[union-attr]
    facts = {"read_as": res.source.label, "state_dirac": res.state.text, "entangled_groups": res.state.groups,
             "product_state": res.state.product, "num_qubits": n, "gates": len(ops),
             "two_qubit_gates": sum(1 for o in ops if o.controls or o.gate == "SWAP"),
             "amplitudes": {format(i, f"0{n}b"): {"probability": _r(float(probs[i])), "size": _r(float(abs(sv[i])))}
                            for i in top},
             "prepared_exactly_fidelity": res.preparation.fidelity if res.preparation else None,
             "preparation_method": res.preparation.method if res.preparation else None,
             "languages": ["Qiskit", "OpenQASM 2", "OpenQASM 3", "Cirq", "PennyLane", "Q#", "Quil", "Amazon Braket"]}
    return facts, {"type": "rosetta", "result": res.model_dump(mode="json")}


RUN: dict[str, Callable[[dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]]] = {
    "simulate_circuit": t_simulate, "optimize_circuit": t_optimize, "molecule_h2": t_molecule,
    "quantum_key_distribution": t_qkd, "max_cut": t_maxcut, "factor_with_shor": t_shor,
    "plan_quantum_link": t_link, "error_correction": t_qec, "translate_notation": t_translate,
}


def run_tool(name: str, args: dict[str, Any]) -> ToolRun:
    start = time.perf_counter()
    if name not in RUN:
        return ToolRun(name=name, args=args, error=f"no tool called {name}")
    try:
        facts, card = RUN[name](args)
        return ToolRun(name=name, args=args, facts=facts, card=card, seconds=time.perf_counter() - start)
    except Exception as err:  # noqa: BLE001 - the model gets the error and can correct its arguments
        return ToolRun(name=name, args=args, error=str(err)[:400], seconds=time.perf_counter() - start)


# ---------------------------------------------------------------- tracing every number

_NUM = re.compile(r"(?<![\w.\-])(-?\d+(?:,\d{3})*(?:\.\d+)?)(\s*%)?(?![\w])")


def _numbers(obj: Any, out: list[float]) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, str):
        out.extend(float(m.group(1).replace(",", "")) for m in _NUM.finditer(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers(v, out)


def _matches(value: float, decimals: int, pct: bool, pool: list[float]) -> bool:
    tol = 0.5 * 10 ** -decimals + 1e-9
    for v in pool:
        for cand in ((v * 100, v) if pct else (v, v * 100, v * 1000, abs(v), abs(v) * 1000)):
            if abs(round(cand, decimals) - value) <= tol or abs(cand - value) <= tol:
                return True
    return False


def trace(answer: str, question: str, runs: list[ToolRun]) -> Trace:
    """Which numbers in the answer come from a tool result (or the question)? Small counts (whole numbers up to 12
    without a percent sign) and bitstrings are not checked: they are 'two tables', '3 layers' or an outcome label."""
    pool: list[float] = []
    for r in runs:
        _numbers(r.facts, pool)
    given: list[float] = []
    _numbers(question, given)
    checked = traced = from_q = 0
    untraced = []
    for m in _NUM.finditer(answer):
        text, pct = m.group(1), bool(m.group(2))
        if not pct and len(text) >= 2 and set(text) <= {"0", "1"}:
            continue  # a bitstring such as 0110 is an outcome label, not a number
        value = float(text.replace(",", ""))
        decimals = len(text.split(".")[1]) if "." in text else 0
        if not pct and decimals == 0 and abs(value) <= 12:
            continue
        checked += 1
        if _matches(value, decimals, pct, pool):
            traced += 1
        elif _matches(value, decimals, pct, given):
            from_q += 1
        else:
            untraced.append(m.group(0).strip())
    return Trace(checked=checked, traced=traced, given=from_q, untraced=untraced)


# ---------------------------------------------------------------- the live loop and the offline router

def ask_live(question: str, history: list[dict[str, str]], tool_chat: Callable[..., tuple[dict[str, Any], ModelCall]],
             rounds: int = MAX_ROUNDS) -> Reply:
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM}]
    messages += [{"role": h["role"], "content": h["content"][:2000]} for h in history[-6:]
                 if h.get("role") in ("user", "assistant") and h.get("content")]
    messages.append({"role": "user", "content": question[:2000]})
    runs: list[ToolRun] = []
    calls: list[ModelCall] = []
    answer = ""
    for _ in range(rounds + 1):
        msg, call = tool_chat(messages, TOOLS)
        calls.append(call)
        tcs = msg.get("tool_calls") or []
        if not tcs:
            answer = (msg.get("content") or "").strip()
            break
        messages.append({k: v for k, v in msg.items() if v is not None})
        for tc in tcs:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            run = run_tool(fn.get("name", ""), args if isinstance(args, dict) else {})
            runs.append(run)
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                             "content": json.dumps({"error": run.error} if run.error else run.facts)[:6000]})
    if not answer:
        answer = "I ran the tools but did not finish an answer; the results are below."
    return Reply(answer=answer, tools=runs, trace=trace(answer, question, runs), calls=calls, router="muse")


def _num(text: str, default: float) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else default


def ask_offline(question: str) -> Reply:
    """Without the live model: route by keywords to the same tools and fill a template answer."""
    from inkubit.textspec import UnknownTextError, parse_description

    q = question.lower()
    runs: list[ToolRun] = []
    notation = _notation_in(question)
    if notation:
        runs.append(run_tool("translate_notation", {"text": notation}))
    elif re.search(r"\bh2\b|h₂|hydrogen|molecule|bond", q):
        r = re.search(r"(\d+(?:\.\d+)?)\s*(?:å|angstrom|a\b)", q)
        runs.append(run_tool("molecule_h2", {"bond_length_angstrom": float(r.group(1)) if r else 0.74}))
    elif re.search(r"spy|eve|eavesdrop|bb84|qkd|secret key|intercept|photons?", q):
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", q)
        runs.append(run_tool("quantum_key_distribution", {"eavesdrop_share": float(m.group(1)) / 100 if m else 0.5}))
    elif re.search(r"shor|factor", q):
        m = re.search(r"\ba\s*=\s*(\d+)", q)
        runs.append(run_tool("factor_with_shor", {"a": int(m.group(1)) if m else 7}))
    elif re.search(r"error correction|bit[- ]flip code|break[- ]even", q):
        runs.append(run_tool("error_correction", {"gate_quality": 1.0}))
    elif re.search(r"satellite|fiber|fibre|km|repeater|network|link", q):
        medium = "satellite" if "satellite" in q else "free_space" if "free space" in q or "laser" in q else "fiber"
        reps = re.search(r"(\d+)\s*repeaters?", q)
        runs.append(run_tool("plan_quantum_link", {"distance_km": _num(q, 300), "medium": medium,
                                                   "repeaters": int(reps.group(1)) if reps else 0}))
    else:
        try:
            spec, how = parse_description(question)
        except UnknownTextError:
            spec = None
        if spec and spec.get("kind") == "circuit":
            ops = [{k: o[k] for k in ("gate", "targets", "controls", "params") if k in o} for o in spec["operations"]]
            measure = [m["qubit"] for m in spec.get("measurements", [])] or None
            runs.append(run_tool("simulate_circuit", {"num_qubits": spec["num_qubits"], "operations": ops,
                                                      "measure": measure, "title": spec.get("metadata", {}).get("title")}))
    if not runs:
        answer = ("Offline I route by keywords, and that question did not match one. Try a molecule (H2 at 1.5 Å), a "
                  "spy (Eve on 30% of photons), Shor (factor 15 with a = 7), a link (500 km of fiber with 2 repeaters) "
                  "or a named circuit (GHZ on 4 qubits). With the live model, ask anything.")
    else:
        answer = _template(runs[0])
    call = ModelCall(provider="mock", model="offline keyword router", role="route question")
    return Reply(answer=answer, tools=runs, trace=trace(answer, question, runs), calls=[call], router="offline")


_EDGE = set("()√0123456789./*+-−^{}πi ")


def _notation_in(text: str) -> str | None:
    """The quantum notation inside a question, for the offline router: OpenQASM, or a ket expression."""
    from inkubit.notation import looks_like_ket

    if "OPENQASM" in text.upper():
        return text[text.upper().index("OPENQASM"):]
    if not looks_like_ket(text):
        return None
    i = text.index("|")
    j = max(text.rfind("⟩"), text.rfind(">"))
    while i > 0 and text[i - 1] in _EDGE:
        i -= 1
    j += 1
    while j < len(text) and (text[j] in _EDGE - {" "} or text[j:j + 4] == "sqrt"):
        j += 4 if text[j:j + 4] == "sqrt" else 1
    return text[i:j].strip() or None


def _template(run: ToolRun) -> str:
    f = run.facts
    if run.error:
        return f"The {run.name} tool could not run that: {run.error}"
    if run.name == "molecule_h2":
        return (f"At {f['bond_length_angstrom']} Å the exact energy of H2 is {f['exact_energy_hartree']} Ha. Hartree-Fock "
                f"gives {f['hartree_fock_hartree']} Ha, {f['hartree_fock_error_mhartree']} mHa too high. VQE with "
                f"realistic noise reads {f['vqe_raw_hartree']} Ha raw and {f['vqe_mitigated_hartree']} Ha with the "
                "calibrated noise undone.")
    if run.name == "quantum_key_distribution":
        verdict = "they abort: the spy is caught" if f["eavesdropper_caught"] else f"they keep {f['secret_key_bits']} secret bits"
        return (f"With the eavesdropper on {f['eavesdrop_share'] * 100:.0f}% of photons, the error rate is "
                f"{f['error_rate'] * 100:.1f}%, against an 11% limit, so {verdict}.")
    if run.name == "factor_with_shor":
        if f["shares_a_factor_with_15"]:
            return f"a = {f['a']} already shares a factor with 15 (gcd {f['gcd_shortcut']}), so no quantum step is needed."
        return (f"With a = {f['a']} the period is {f['period']}; a perfect run gives the factors "
                f"{f['factors']} with probability {f['success_per_run_perfect']}, a noisy one {f['success_per_run_noisy']}.")
    if run.name == "error_correction":
        return f["summary"]
    if run.name == "plan_quantum_link":
        return f["summary"]
    if run.name == "translate_notation":
        kind = ("entangled: no qubit can be described on its own" if f["entangled_groups"] and not f["product_state"]
                else "a product state: each qubit is on its own")
        made = (f" A circuit of {f['gates']} gates ({f['two_qubit_gates']} two-qubit) prepares it exactly, fidelity "
                f"{f['prepared_exactly_fidelity']}." if f.get("prepared_exactly_fidelity") is not None else "")
        return f"Read as {f['read_as']}: the state is {f['state_dirac']}, {kind}.{made}"
    if run.name == "simulate_circuit":
        top = ", ".join(f"{k} with probability {v}" for k, v in list(f["outcomes_perfect"].items())[:4])
        return f"With perfect qubits it reads {top}." + (
            f" On realistic hardware {f['realistic_noise_share_lost'] * 100:.1f}% of the probability leaks to wrong outcomes."
            if f.get("realistic_noise_share_lost") is not None else "")
    return "Done; the results are below."
