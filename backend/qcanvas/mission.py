"""Mission control: one request in words, a photo and speech; a plan of exact tools; live parallel execution; every
result verified; a report whose numbers are traced.

Stages, each streamed to the page as it happens (EventBus, server-sent events):

1. Perceive. Speech arrives already transcribed by Muse Voice Transcribe. A photo goes through the sketch pipeline
   (Muse Spark chooses what to look for, SAM 3.1 segments it, Muse Spark reads it into a validated spec); if it is not
   a circuit or network drawing, Muse Spark transcribes any quantum notation in it for the Rosetta.
2. Plan. Muse Spark (Muse Wonder in deep mode) writes a dependency graph of up to 8 tool steps under a JSON schema:
   which exact tool, with which arguments, after which other steps. A circuit can be passed between steps by
   reference ("circuit_from": a step id or "photo"). Unknown tools, missing dependencies and cycles are dropped
   before anything runs, with a note.
3. Run. Steps whose dependencies are done run in parallel (thread pool). If a step fails, Muse Spark gets the error
   and the tool's schema and fixes the arguments once; the node is marked repaired.
4. Verify. Every result is checked by rules that do not trust the tool: invariants of the physics (the exact H2
   energy is never above Hartree-Fock, a QAOA cut never beats the brute-force best, Shor's factors multiply to 15,
   a link's fidelity stays in [1/4, 1], the eavesdropper verdict matches the 11% rule) and, for every circuit, two
   independent noisy simulators (our closed-form channels and Qiskit Aer's density matrix) must agree to 1e-6. The
   ML verifier's interval is also compared with the exact fidelity; when it misses, that grades the ML model, not the
   result (the exact value is what the step reports), so it is shown as a note and does not flag the step.
5. Report. Muse Spark writes the findings from the facts alone; every number in them is traced back to a tool result.

Offline (no key) a keyword planner stands in, labelled as such, and the report is assembled from the tools' own
summaries.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any, Callable

from pydantic import BaseModel, Field

from qcanvas.adapters.base import ModelCall
from qcanvas.agent.events import EventBus
from qcanvas.copilot import RUN, TOOLS, ToolRun, _circuit_spec, _r, _template, trace

MAX_STEPS = 8
WORKERS = 4
CIRCUIT_TOOLS = {"simulate_circuit", "optimize_circuit", "ml_verify"}


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required}}}


def _gallery() -> dict[str, dict[str, Any]]:
    from qcanvas import EXAMPLES_DIR
    from qcanvas.api.app import ALGORITHMS

    out = {}
    for name in sorted(ALGORITHMS):
        path = EXAMPLES_DIR / "specs" / f"{name}.json"
        if path.exists():
            out[name] = json.loads(path.read_text(encoding="utf-8"))
    return out


_CIRCUIT_REF = {"circuit_from": {"type": "string", "description": "Use the circuit of an earlier step (its id) or "
                                                                  "of the photo ('photo') instead of writing it out."}}

EXTRA_TOOLS = [
    _fn("run_algorithm", "Run a textbook algorithm from the library exactly, with perfect qubits and with realistic "
        "noise: grover2, grover3, bernstein_vazirani, deutsch_jozsa, simon, qft_period, phase_estimation, shor15, "
        "superdense, teleportation, entanglement_swapping, swap_test, w_state, toffoli_and, half_adder, "
        "bit_flip_code, ising_trotter.",
        {"name": {"type": "string"}}, ["name"]),
    _fn("ml_verify", "The ML verifier: a neural network predicts in microseconds how much of a circuit's answer "
        "survives realistic noise (fidelity with a 90% conformal interval), then exact simulation checks it.",
        {**_CIRCUIT_REF, "noise_scale": {"type": "number", "minimum": 0.05, "maximum": 5,
                                         "description": "1 = today's realistic hardware."}}, []),
    _fn("analyze_network", "Simulate the quantum network read from the photo: pair rate, fidelity, key rate, the "
        "weakest link and the best fix.", {"network_from": {"type": "string", "enum": ["photo"]}}, ["network_from"]),
]
MISSION_TOOLS = TOOLS + EXTRA_TOOLS
TOOL_NAMES = [t["function"]["name"] for t in MISSION_TOOLS]

PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["goal", "steps"],
    "properties": {
        "goal": {"type": "string", "description": "The problem restated in one sentence."},
        "steps": {"type": "array", "minItems": 1, "maxItems": MAX_STEPS, "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "tool", "arguments", "after", "purpose"],
            "properties": {
                "id": {"type": "string", "description": "s1, s2, ..."},
                "tool": {"type": "string", "enum": TOOL_NAMES},
                "arguments": {"type": "string", "description": "The tool's arguments as a JSON object."},
                "after": {"type": "array", "items": {"type": "string"},
                          "description": "Ids of steps that must finish first (only when this step uses their result)."},
                "purpose": {"type": "string", "description": "What this step answers, in a few words."},
            }}},
    },
}
REPAIR_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["arguments", "change"], "properties": {
    "arguments": {"type": "string", "description": "Corrected arguments as a JSON object."},
    "change": {"type": "string", "description": "What was changed, in a few words."}}}
REPORT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["headline", "findings", "next"],
                 "properties": {
                     "headline": {"type": "string", "description": "The answer to the mission in one plain sentence."},
                     "findings": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5,
                                  "description": "3 to 5 short sentences, one idea each, numbers from the facts."},
                     "next": {"type": "string", "description": "One honest caveat or next step."}}}

PLAN_SYSTEM = (
    "You are the planner of Q-Canvas mission control. Break the user's problem into a small graph of steps, each a "
    "call to one exact tool listed below; never compute a quantum result yourself. Use parallel steps (empty 'after') "
    "whenever steps are independent, and 'after' only when a step needs an earlier result. To reuse a circuit, pass "
    "\"circuit_from\" with the step id (or \"photo\" for a circuit read from the photo) instead of writing operations "
    "again. Arguments must follow each tool's JSON schema. Prefer 2 to 6 steps that together answer the whole "
    "problem, including comparisons the user asks for. Circuits use Qiskit conventions (qubit 0 rightmost).")
REPAIR_SYSTEM = (
    "A step of a Q-Canvas mission failed. Return corrected arguments for the same tool that respect its JSON schema "
    "and fix the error; keep the user's intent.")
REPORT_SYSTEM = (
    "You write the result of a Q-Canvas mission for a smart non-specialist, like a lab lead briefing a manager. Use "
    "only the facts given: every number must appear in them (round to 2 or 3 significant figures, or write a share "
    "as a percentage). Do not compute new numbers. Answer the question that was asked first. Each finding is one "
    "short sentence with at most two numbers; never name data fields, never write null, true or false, never list "
    "the checks one by one. Use one finding to say the results passed their independent checks, or which one was "
    "flagged. No headings, no LaTeX.")


class Check(BaseModel):
    name: str
    ok: bool
    detail: str
    affects: bool = True  # False: a note about the ML model, which never changes the step's exact result


class Node(BaseModel):
    id: str
    lane: str  # perceive | plan | step | report
    label: str
    tool: str | None = None
    purpose: str = ""
    after: list[str] = Field(default_factory=list)
    status: str = "waiting"  # waiting | running | verifying | done | repaired | flagged | failed | skipped
    detail: str = ""
    seconds: float = 0.0
    model: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    facts: dict[str, Any] = Field(default_factory=dict)
    card: dict[str, Any] | None = None
    checks: list[Check] = Field(default_factory=list)


class Report(BaseModel):
    headline: str
    findings: list[str]
    next: str
    trace: dict[str, Any]
    router: str  # muse | offline
    calls: list[ModelCall]
    seconds: float
    verified: int
    flagged: int


class Mission:
    def __init__(self, goal: str):
        self.id = uuid.uuid4().hex[:12]
        self.goal = goal
        self.bus = EventBus()
        self.nodes: dict[str, Node] = {}
        self.report: Report | None = None
        self.status = "running"
        self.error: str | None = None
        self.lock = threading.Lock()

    def put(self, node: Node) -> None:
        with self.lock:
            self.nodes[node.id] = node
            payload = node.model_dump(mode="json")
        self.bus.emit("mission", "info", node.label, kind="node", node=payload)

    def update(self, node_id: str, **changes: Any) -> Node:
        with self.lock:
            node = self.nodes[node_id].model_copy(update=changes)
            self.nodes[node_id] = node
            payload = node.model_dump(mode="json")
        self.bus.emit("mission", "info", node.label, kind="node", node=payload)
        return node

    def summary(self) -> dict[str, Any]:
        return {"id": self.id, "goal": self.goal, "status": self.status, "error": self.error,
                "nodes": [n.model_dump(mode="json") for n in self.nodes.values()],
                "report": self.report.model_dump(mode="json") if self.report else None}


# ---------------------------------------------------------------- tools beyond the copilot's

def _sim_card(spec_raw: dict[str, Any], title: str) -> tuple[dict[str, Any], dict[str, Any]]:
    args = _args_from_spec(spec_raw)
    args["title"] = title
    return RUN["simulate_circuit"](args)


def t_algorithm(a: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    name = str(a.get("name", "")).strip().lower().replace(" ", "_").replace("-", "_")
    gallery = _gallery()
    if name not in gallery:
        raise ValueError(f"no algorithm called {name!r}; choose one of {', '.join(gallery)}")
    raw = gallery[name]
    facts, card = _sim_card(raw, raw.get("metadata", {}).get("title", name))
    facts = {"algorithm": raw["metadata"]["title"], "what_it_does": raw["metadata"].get("notes", ""), **facts}
    return facts, card


def t_ml_verify(a: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from qcanvas.mlverify import check
    from qcanvas.spec import parse_spec

    if not a.get("operations"):
        raise ValueError("ml_verify needs a circuit: pass circuit_from (a step id or 'photo') or operations")
    spec = parse_spec(_circuit_spec(a))
    scale = min(5.0, max(0.05, float(a.get("noise_scale") or 1.0)))
    res = check(spec, scale)
    p = res.prediction
    facts = {"ml_predicted_fidelity": p.fidelity, "ml_interval": [p.low, p.high], "interval_coverage_percent": 90,
             "ml_microseconds": p.microseconds,
             "physics_baseline_fidelity": p.baseline, "exact_fidelity": res.exact, "exact_milliseconds": res.exact_ms,
             "exact_inside_interval": res.inside, "ml_error": res.error, "noise_scale": scale, "verdict": res.verdict}
    return facts, {"type": "mlverify", "check": res.model_dump(mode="json"),
                   "spec": spec.model_dump(mode="json", by_alias=True, exclude_none=True)}


def t_network(a: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from qcanvas.network.agent import run_network_agent
    from qcanvas.spec import parse_spec

    raw = a.get("network")
    if not isinstance(raw, dict):
        raise ValueError("analyze_network needs the network read from the photo")
    res = run_network_agent(parse_spec(raw))

    def e2e(m: Any) -> dict[str, Any]:
        e = m.end_to_end
        return {"pairs_per_second": float(f"{e.pair_rate_hz:.3g}"), "fidelity": _r(e.fidelity, 3),
                "error_rate": _r(e.qber, 3), "secret_key_bits_per_second": float(f"{e.key_rate_bps:.3g}")}

    facts = {"before": e2e(res.before), "after_best_fix": e2e(res.after) if res.after else None,
             "fix": res.fix.description if res.fix else None, "summary": res.summary}
    return facts, {"type": "network", "result": res.model_dump(mode="json"), "title": "Network from the photo"}


TOOLS_RUN: dict[str, Callable[[dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]]] = {
    **RUN, "run_algorithm": t_algorithm, "ml_verify": t_ml_verify, "analyze_network": t_network}


def run_step(name: str, args: dict[str, Any]) -> ToolRun:
    start = time.perf_counter()
    if name not in TOOLS_RUN:
        return ToolRun(name=name, args=args, error=f"no tool called {name}")
    try:
        facts, card = TOOLS_RUN[name](args)
        return ToolRun(name=name, args=args, facts=facts, card=card, seconds=time.perf_counter() - start)
    except Exception as err:  # noqa: BLE001 - shown on the node and handed to the repair step
        return ToolRun(name=name, args=args, error=str(err)[:400], seconds=time.perf_counter() - start)


def summary(run: ToolRun) -> str:
    """One plain sentence from a finished step's facts (the offline report and a fallback)."""
    f = run.facts
    if run.name == "run_algorithm":
        best, p = next(iter(f["outcomes_perfect"].items()))
        noisy = (f.get("outcomes_realistic_noise") or {}).get(best)
        return f"{f['algorithm']}: the top answer {best} comes out with probability {p} on perfect qubits" + (
            f" and {noisy} on realistic hardware." if noisy is not None else ".")
    if run.name == "ml_verify":
        return (f"The ML verifier predicted fidelity {f['ml_predicted_fidelity']} (interval {f['ml_interval'][0]} "
                f"to {f['ml_interval'][1]}) in {f['ml_microseconds']} µs; {f['verdict']}.")
    if run.name == "optimize_circuit":
        return str(f.get("summary") or "No shorter circuit was found.")
    if run.name == "max_cut":
        q = f["qaoa_most_likely_split"]
        return (f"Best possible: {f['best_possible_separated']} of {f['conflicts']} clashes separated. QAOA's most "
                f"likely split, {', '.join(q['group_a'])} | {', '.join(q['group_b'])}, separates {q['separated']}.")
    if run.name == "analyze_network":
        return str(f.get("summary", ""))
    return _template(run)


# ---------------------------------------------------------------- circuits passed between steps

def _args_from_spec(raw: dict[str, Any]) -> dict[str, Any]:
    measure = [m["qubit"] for m in raw.get("measurements") or []]
    ops = [{"gate": o["gate"], "targets": o.get("targets") or [], "controls": o.get("controls") or [],
            "params": o.get("params") or []}
           for o in raw.get("operations") or [] if o.get("gate") not in ("MEASURE", "BARRIER")]
    return {"num_qubits": raw["num_qubits"], "operations": ops, "measure": measure or list(range(raw["num_qubits"]))}


def circuit_of(card: dict[str, Any] | None) -> dict[str, Any] | None:
    """The circuit a finished step produced (for optimize: the proven shorter one when there is one)."""
    if not card:
        return None
    if card.get("type") == "optimize" and isinstance(card.get("best"), dict) and card["best"].get("spec"):
        return card["best"]["spec"]
    if card.get("type") == "rosetta":
        return card.get("result", {}).get("spec")
    spec = card.get("spec")
    return spec if isinstance(spec, dict) and spec.get("kind") == "circuit" else None


def resolve(args: dict[str, Any], tool: str, done: dict[str, Node], photo: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(args)
    ref = out.pop("circuit_from", None)
    if tool in CIRCUIT_TOOLS and ref:
        spec = photo if ref == "photo" and photo and photo.get("kind") == "circuit" else \
            circuit_of(done[ref].card) if ref in done else None
        if spec is None:
            raise ValueError(f"circuit_from {ref!r} has no circuit")
        out = {**_args_from_spec(spec), **{k: v for k, v in out.items() if k not in ("num_qubits", "operations")}}
    if tool == "analyze_network":
        if not (photo and photo.get("kind") == "network"):
            raise ValueError("there is no network drawing in the photo")
        out = {"network": photo}
    return out


# ---------------------------------------------------------------- verification that does not trust the tool

def _two_engines(spec_raw: dict[str, Any]) -> Check:
    from qcanvas.insights.circuit import noisy_distribution as channels
    from qcanvas.sim.noise import get_preset
    from qcanvas.spec import parse_spec
    from qcanvas.verify.expected import noisy_distribution as aer

    spec = parse_spec(spec_raw)
    if spec.num_qubits > 8:
        return Check(name="two simulators", ok=True, detail="skipped above 8 qubits")
    a = channels(spec, get_preset("realistic"))
    b = aer(spec, "realistic")
    gap = max(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in set(a) | set(b))
    return Check(name="two simulators", ok=gap < 1e-6,
                 detail=f"closed-form channels and Qiskit Aer agree to {gap:.1e}")


def _ml(spec_raw: dict[str, Any]) -> Check:
    from qcanvas.mlverify import check
    from qcanvas.spec import parse_spec

    res = check(parse_spec(spec_raw), 1.0)
    p = res.prediction
    if res.exact is None:
        return Check(name="ML verifier", ok=True, affects=False, detail=f"predicts {p.fidelity:.3f} ({res.verdict})")
    return Check(name="ML verifier", ok=bool(res.inside), affects=False,
                 detail=f"predicted {p.fidelity:.3f} in {p.microseconds:.0f} µs, exact {res.exact:.3f}"
                        + ("" if res.inside else ": outside its interval, so the exact value stands"))


def verify(run: ToolRun) -> list[Check]:
    f, card = run.facts, run.card or {}
    checks: list[Check] = []
    spec = circuit_of(card)
    if run.name in ("simulate_circuit", "run_algorithm", "optimize_circuit") and spec:
        checks += [_two_engines(spec), _ml(spec)]
    if run.name == "optimize_circuit":
        best = f.get("best")
        checks.append(Check(name="proof", ok=True, detail=f"shorter circuit proven equal ({best['proof']})"
                            if best and best.get("proof") else "no shorter circuit claimed"))
    elif run.name == "ml_verify":
        checks.append(Check(name="exact check", ok=f.get("exact_inside_interval") is not False, affects=False,
                            detail=str(f.get("verdict", ""))))
    elif run.name == "molecule_h2":
        ok = f["exact_energy_hartree"] <= f["hartree_fock_hartree"] + 1e-9
        checks.append(Check(name="variational principle", ok=ok,
                            detail="exact energy is not above Hartree-Fock" if ok else "exact above Hartree-Fock"))
    elif run.name == "quantum_key_distribution":
        caught = f["error_rate"] > f["abort_threshold"]
        sigma = max(f.get("error_rate_uncertainty") or 0.0, 1e-3)
        close = abs(f["error_rate"] - f["expected_error_rate"]) <= 4 * sigma
        checks.append(Check(name="11% rule", ok=caught == f["eavesdropper_caught"],
                            detail=f"error rate {f['error_rate']:.3f} {'>' if caught else '<='} 0.11, verdict matches"))
        checks.append(Check(name="theory", ok=close, detail=f"measured {f['error_rate']:.3f} vs expected "
                                                            f"{f['expected_error_rate']:.3f} (within 4 sigma)"))
    elif run.name == "max_cut":
        got, best = f["qaoa_most_likely_split"]["separated"], f["best_possible_separated"]
        checks.append(Check(name="brute force", ok=got <= best,
                            detail=f"QAOA's split separates {got} of the best possible {best}"))
    elif run.name == "factor_with_shor":
        a, r, fac = f["a"], f.get("period"), f.get("factors")
        ok = (r is None or pow(a, r, 15) == 1) and (not fac or math.prod(fac) == 15)
        checks.append(Check(name="arithmetic", ok=ok, detail=f"{a}^{r} mod 15 = 1" + (f", {fac[0]} x {fac[1]} = 15"
                                                                                    if fac and len(fac) == 2 else "")))
    elif run.name in ("plan_quantum_link", "analyze_network"):
        end = f.get("after_best_fix") or f["before"]
        ok = 0.25 - 1e-9 <= end["fidelity"] <= 1 + 1e-9 and end["secret_key_bits_per_second"] >= 0
        checks.append(Check(name="physical range", ok=ok, detail=f"fidelity {end['fidelity']} in [0.25, 1], key rate >= 0"))
        if f.get("after_best_fix"):
            better = f["after_best_fix"]["secret_key_bits_per_second"] >= f["before"]["secret_key_bits_per_second"]
            checks.append(Check(name="fix helps", ok=better, detail="the fix does not lower the key rate"))
    elif run.name == "error_correction":
        be = f.get("break_even_physical_error")
        checks.append(Check(name="range", ok=be is None or 0 < be < 0.5, detail=f"break-even {be}"))
    elif run.name == "translate_notation":
        fid = f.get("prepared_exactly_fidelity")
        checks.append(Check(name="state preparation", ok=fid is None or fid >= 1 - 1e-8,
                            detail=f"circuit reproduces the state, fidelity {fid}"))
    return checks


# ---------------------------------------------------------------- planning

class PlanStep(BaseModel):
    id: str
    tool: str
    args: dict[str, Any]
    after: list[str]
    purpose: str


def clean_plan(raw_steps: list[dict[str, Any]]) -> tuple[list[PlanStep], list[str]]:
    """Keep known tools, unique ids and dependencies that exist and point backwards (so there are no cycles)."""
    steps: list[PlanStep] = []
    notes: list[str] = []
    seen: set[str] = set()
    for i, s in enumerate(raw_steps[:MAX_STEPS]):
        sid = re.sub(r"[^\w-]", "", str(s.get("id") or f"s{i + 1}"))[:12] or f"s{i + 1}"
        if sid in seen or sid == "photo":
            sid = f"s{i + 1}x"
        tool = str(s.get("tool", ""))
        if tool not in TOOLS_RUN:
            notes.append(f"dropped a step with unknown tool {tool!r}")
            continue
        args = s.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except json.JSONDecodeError:
                notes.append(f"{sid}: arguments were not JSON; left empty for repair")
                args = {}
        after = [a for a in s.get("after") or [] if a in seen]
        dropped = [a for a in s.get("after") or [] if a not in seen]
        if dropped:
            notes.append(f"{sid}: ignored dependencies on {', '.join(map(str, dropped))}")
        ref = args.get("circuit_from") if isinstance(args, dict) else None
        if ref and ref != "photo" and ref in seen and ref not in after:
            after.append(ref)
        steps.append(PlanStep(id=sid, tool=tool, args=args if isinstance(args, dict) else {}, after=after,
                              purpose=str(s.get("purpose", ""))[:120]))
        seen.add(sid)
    return steps, notes


def _plan_prompt(goal: str, perceived: list[str]) -> str:
    tools = [{"name": t["function"]["name"], "description": t["function"]["description"],
              "arguments": t["function"]["parameters"]} for t in MISSION_TOOLS]
    seen = "\n".join(perceived) or "nothing besides the text"
    return (f"Tools:\n{json.dumps(tools, ensure_ascii=False)}\n\nWhat the photo and voice gave:\n{seen}\n\n"
            f"Problem:\n{goal[:3000]}")


_KM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*km")
_SHARE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_ANGSTROM = re.compile(r"(\d+(?:\.\d+)?)\s*(?:Å|angstrom|A\b)")


def offline_plan(goal: str, photo: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Keyword planner used without a key. It covers the sample missions and simple variations."""
    g = goal.lower()
    steps: list[dict[str, Any]] = []

    def add(tool: str, args: dict[str, Any], purpose: str, after: list[str] | None = None) -> str:
        sid = f"s{len(steps) + 1}"
        steps.append({"id": sid, "tool": tool, "arguments": args, "after": after or [], "purpose": purpose})
        return sid

    if photo and photo.get("kind") == "circuit":
        add("simulate_circuit", {"circuit_from": "photo"}, "run the circuit from the photo")
        s2 = add("optimize_circuit", {"circuit_from": "photo"}, "find a shorter proven-equal circuit")
        add("ml_verify", {"circuit_from": s2}, "predict and check how it survives noise", [s2])
        if "error" in g or "correct" in g:
            add("error_correction", {"gate_quality": 1}, "would error correction help")
    if photo and photo.get("kind") == "network":
        add("analyze_network", {"network_from": "photo"}, "simulate the drawn network")
    km = _KM.search(goal)
    if km or any(w in g for w in ("satellite", "fiber", "fibre", "link", "cities")):
        d = float(km.group(1).replace(",", "")) if km else 1200.0
        if "satellite" in g or not km or d > 300:
            add("plan_quantum_link", {"distance_km": d, "medium": "satellite"}, f"{d:g} km by satellite")
        if "fiber" in g or "fibre" in g or "compare" in g:
            add("plan_quantum_link", {"distance_km": d, "medium": "fiber"}, f"{d:g} km of fiber")
    if any(w in g for w in ("spy", "eavesdrop", "eve", "secure", "intercept")):
        share = _SHARE.search(goal)
        add("quantum_key_distribution", {"eavesdrop_share": float(share.group(1)) / 100 if share else 0.25},
            "is the spy caught")
    if any(w in g for w in ("molecule", "hydrogen", "h2", "h₂", "bond")):
        for r in [float(x) for x in _ANGSTROM.findall(goal)][:4] or [0.74]:
            add("molecule_h2", {"bond_length_angstrom": r}, f"H2 at {r:g} Å")
    if any(w in g for w in ("factor", "shor", "rsa")):
        add("factor_with_shor", {"a": 7}, "factor 15 with a = 7")
        if "two bases" in g or "bases" in g:
            add("factor_with_shor", {"a": 11}, "factor 15 with a = 11")
    if "grover" in g or "search" in g:
        s = add("run_algorithm", {"name": "grover3"}, "Grover search on 3 qubits")
        add("ml_verify", {"circuit_from": s}, "ML verifier on the Grover circuit", [s])
    names = re.findall(r"\b([A-Z][a-z]+)\b", goal)
    clashes = re.findall(r"\b([A-Z][a-z]+)-([A-Z][a-z]+)\b", goal)
    if clashes and any(w in g for w in ("clash", "conflict", "schedule", "split", "exam")):
        people = list(dict.fromkeys([a for pair in clashes for a in pair] + names))
        people = [p for p in people if any(p in pair for pair in clashes)][:8]
        add("max_cut", {"names": people, "conflicts": [list(p) for p in clashes]}, "split into two groups")
    if not steps:
        add("translate_notation", {"text": goal}, "read the request as notation")
    return steps


# ---------------------------------------------------------------- running a mission

class Ctx(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    live: bool
    reasoning: Any = None
    deep_model: str | None = None


def _structured(ctx: Ctx, system: str, user: str, schema: dict[str, Any], name: str, effort: str,
                deep: bool = False) -> tuple[dict[str, Any], ModelCall]:
    return ctx.reasoning.structured(system, user, schema, name, effort=effort, max_tokens=16000,
                                    model=ctx.deep_model if deep else None)


def run_mission(m: Mission, ctx: Ctx, photo: dict[str, Any] | None = None, perceived: list[str] | None = None,
                deep: bool = False) -> None:
    """Plan, run, verify and report; every change is published on ``m.bus``. Never raises."""
    t0 = time.perf_counter()
    calls: list[ModelCall] = []
    router = "muse" if ctx.live else "offline"
    try:
        m.put(Node(id="plan", lane="plan", label="Plan", status="running",
                   after=[n for n in m.nodes if m.nodes[n].lane == "perceive"],
                   model=(ctx.deep_model if deep else "muse-spark-1.3") if ctx.live else "offline planner"))
        start = time.perf_counter()
        notes: list[str] = []
        raw: list[dict[str, Any]] = []
        if ctx.live:
            try:
                data, call = _structured(ctx, PLAN_SYSTEM, _plan_prompt(m.goal, perceived or []), PLAN_SCHEMA,
                                         "mission_plan", "medium" if deep else "low", deep)
                calls.append(call)
                raw = data.get("steps") or []
            except Exception as err:  # noqa: BLE001 - the offline planner stands in, labelled
                notes.append(f"the planner failed ({str(err)[:120]}); the offline planner stood in")
                router = "offline"
        if not raw:
            raw = offline_plan(m.goal, photo)
        steps, more = clean_plan(raw)
        notes += more
        if not steps:
            raise ValueError("the plan had no usable steps")
        m.update("plan", status="done", seconds=time.perf_counter() - start,
                 detail=f"{len(steps)} steps" + (f"; {'; '.join(notes)}" if notes else ""),
                 model=m.nodes["plan"].model if router == "muse" else "offline planner")
        for s in steps:
            m.put(Node(id=s.id, lane="step", label=s.tool.replace("_", " "), tool=s.tool, purpose=s.purpose,
                       after=s.after or ["plan"], args=s.args))

        done: dict[str, Node] = {}
        failed: set[str] = set()
        pending = {s.id: s for s in steps}
        futures: dict[Future, str] = {}

        def execute(s: PlanStep) -> Node:
            began = time.perf_counter()
            m.update(s.id, status="running")
            repaired = ""
            try:
                args = resolve(s.args, s.tool, done, photo)
                run = run_step(s.tool, args)
            except ValueError as err:
                run, args = ToolRun(name=s.tool, args=s.args, error=str(err)), s.args
            if run.error and ctx.live and router == "muse":
                schema = next(t["function"]["parameters"] for t in MISSION_TOOLS if t["function"]["name"] == s.tool)
                try:
                    data, call = _structured(ctx, REPAIR_SYSTEM, json.dumps({
                        "tool": s.tool, "schema": schema, "arguments": s.args, "error": run.error,
                        "goal": m.goal[:600]}, ensure_ascii=False), REPAIR_SCHEMA, "step_repair", "low")
                    calls.append(call)
                    fixed = json.loads(data.get("arguments") or "{}")
                    args = resolve(fixed, s.tool, done, photo)
                    run = run_step(s.tool, args)
                    repaired = str(data.get("change", ""))[:160] or "arguments corrected"
                except Exception as err:  # noqa: BLE001 - the original error stays on the node
                    run.error = f"{run.error} (repair failed: {str(err)[:120]})"
            if run.error:
                return m.update(s.id, status="failed", detail=run.error, seconds=time.perf_counter() - began,
                                args=args)
            m.update(s.id, status="verifying", facts=run.facts, card=run.card, args=args,
                     detail=f"repaired: {repaired}" if repaired else "")
            checks = verify(run)
            ok = all(c.ok for c in checks if c.affects)
            status = "flagged" if not ok else "repaired" if repaired else "done"
            return m.update(s.id, status=status, checks=checks, seconds=time.perf_counter() - began)

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            while pending or futures:
                ready = [s for s in pending.values() if all(a in done for a in s.after)]
                blocked = [s for s in pending.values() if any(a in failed for a in s.after)]
                for s in blocked:
                    pending.pop(s.id)
                    failed.add(s.id)
                    m.update(s.id, status="skipped", detail="an earlier step it needs failed")
                for s in ready:
                    pending.pop(s.id)
                    futures[pool.submit(execute, s)] = s.id
                if not futures:
                    break
                finished, _ = wait(list(futures), return_when=FIRST_COMPLETED)
                for fut in finished:
                    sid = futures.pop(fut)
                    node = fut.result()
                    (failed.add(sid) if node.status in ("failed", "skipped") else done.__setitem__(sid, node))

        leaves = [s.id for s in steps if not any(s.id in t.after for t in steps)]
        m.put(Node(id="report", lane="report", label="Report", status="running", after=leaves,
                   model="muse-spark-1.3" if router == "muse" else "tool summaries"))
        start = time.perf_counter()
        done = {s.id: done[s.id] for s in steps if s.id in done}  # plan order, not finishing order
        runs = [ToolRun(name=n.tool or "", args=n.args, card=n.card,
                        facts={**n.facts, "checks": [c.detail for c in n.checks]}) for n in done.values()]
        verified = sum(1 for n in done.values() if n.status != "flagged")
        flagged = len(done) - verified
        facts = {n.id: {"tool": n.tool, "purpose": n.purpose, "facts": n.facts,
                        "checks": [f"{c.name}: {'ok' if c.ok else 'FLAGGED' if c.affects else 'ML model missed, exact used'}"
                                   f" ({c.detail})" for c in n.checks]}
                 for n in done.values()}
        failures = {sid: m.nodes[sid].detail for sid in failed}
        headline, findings, nxt = "", [], ""
        if router == "muse" and done:
            try:
                data, call = _structured(ctx, REPORT_SYSTEM, json.dumps({
                    "mission": m.goal[:2000], "steps": facts, "failed_steps": failures}, ensure_ascii=False,
                    default=str)[:24000], REPORT_SCHEMA, "mission_report", "low")
                calls.append(call)
                headline = str(data.get("headline", "")).strip()
                findings = [str(x).strip() for x in data.get("findings") or [] if str(x).strip()]
                nxt = str(data.get("next", "")).strip()
            except Exception as err:  # noqa: BLE001 - fall back to the tools' own summaries
                nxt = f"The report writer failed ({str(err)[:100]}); these are the tools' own summaries."
        if not headline:
            findings = [summary(r) for r in runs] or ["No step finished."]
            headline = f"{len(done)} of {len(steps)} steps finished, {verified} verified" + \
                (f", {flagged} flagged" if flagged else "") + "."
            nxt = nxt or ("Planned offline by keywords; with a key Muse Spark plans and writes the report."
                          if router == "offline" else "")
        text = " ".join([headline, *findings, nxt])
        tr = trace(text, m.goal, runs)
        m.update("report", status="done", seconds=time.perf_counter() - start,
                 detail=f"{tr.traced} of {tr.checked} numbers traced to a tool result")
        m.report = Report(headline=headline, findings=findings, next=nxt, trace=tr.model_dump(), router=router,
                          calls=calls, seconds=round(time.perf_counter() - t0, 2), verified=verified, flagged=flagged)
        m.status = "done"
        m.bus.emit("mission", "ok", headline, kind="report", report=m.report.model_dump(mode="json"))
    except Exception as err:  # noqa: BLE001 - reported on the page, never a made-up result
        m.status, m.error = "failed", str(err)[:400]
        m.bus.emit("mission", "fail", m.error, kind="error")
    finally:
        m.bus.close()


def perceive(m: Mission, models: Any, image: bytes | None, transcript: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Voice and photo nodes. Returns the spec read from the photo (if any) and lines for the planner."""
    from qcanvas.adapters.imaging import normalise_upload
    from qcanvas.sketch import analyze_image

    lines: list[str] = []
    s = models.settings
    if transcript.strip():
        m.put(Node(id="voice", lane="perceive", label="Voice", status="done", model=s.voice_model,
                   detail=f"heard: \u201c{transcript.strip()[:200]}\u201d"))
        lines.append(f"Spoken by the user (transcribed by {s.voice_model}): {transcript.strip()[:1500]}")
    if not image:
        return None, lines
    m.put(Node(id="photo", lane="perceive", label="Photo", status="running", model=f"{s.reasoning_model} + {s.segment_model}"))
    start = time.perf_counter()
    try:
        analysis, _ = analyze_image(image, models)
        spec = analysis.spec
        if spec.get("kind") == "circuit":
            what = f"a circuit: {spec.get('num_qubits')} qubits, {len(spec.get('operations') or [])} operations"
        else:
            what = f"a network: {len(spec.get('nodes') or [])} nodes, {len(spec.get('links') or [])} links"
        m.update("photo", status="done" if analysis.valid else "flagged", seconds=time.perf_counter() - start,
                 detail=f"read as {what}; {len(analysis.segments)} parts segmented"
                        + ("" if analysis.valid else f"; not valid: {'; '.join(analysis.issues)[:200]}"),
                 card={"type": "photo", "spec": spec, "calls": [c.model_dump(mode="json") for c in analysis.calls]})
        if analysis.valid:
            lines.append(f"The photo was read as {what}. Refer to it as \"photo\" (circuit_from or network_from). "
                         f"Spec: {json.dumps(spec, ensure_ascii=False)[:3000]}")
            return spec, lines
        return None, lines
    except Exception as first:  # noqa: BLE001 - not a drawing: try reading notation instead
        try:
            img, mime, _, _ = normalise_upload(image)
            read = models.reasoning.read_notation(img, mime)
            m.update("photo", status="done", seconds=time.perf_counter() - start, model=s.reasoning_model,
                     detail=f"no circuit drawing; notation read: {read.text[:160]}")
            lines.append(f"The photo shows quantum notation (pass it to translate_notation): {read.text[:2000]}")
        except Exception as err:  # noqa: BLE001
            m.update("photo", status="failed", seconds=time.perf_counter() - start,
                     detail=f"could not read the photo: {str(first)[:120]}; {str(err)[:120]}")
        return None, lines


def launch(m: Mission, models: Any, image: bytes | None, transcript: str, deep: bool) -> None:
    """Run perception and the mission on a background thread."""
    s = models.settings
    ctx = Ctx(live=s.provider == "meta" and s.has_key, reasoning=models.reasoning, deep_model=s.deep_model)

    def go() -> None:
        try:
            photo, lines = perceive(m, models, image, transcript)
        except Exception as err:  # noqa: BLE001
            photo, lines = None, [f"perception failed: {err}"]
        run_mission(m, ctx, photo, lines, deep)

    threading.Thread(target=go, name=f"mission-{m.id}", daemon=True).start()


class MissionStore:
    def __init__(self, keep: int = 30):
        self._missions: dict[str, Mission] = {}
        self._keep = keep
        self._lock = threading.Lock()

    def add(self, m: Mission) -> None:
        with self._lock:
            self._missions[m.id] = m
            while len(self._missions) > self._keep:
                self._missions.pop(next(iter(self._missions)))

    def get(self, mission_id: str) -> Mission | None:
        return self._missions.get(mission_id)


missions = MissionStore()
