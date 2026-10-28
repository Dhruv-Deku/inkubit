"""Questions about a finished run, answered only from that run's facts.

``ask_context`` collects the facts (spec, verdict, attempts, insights or network
metrics). Live, Muse Spark answers from them; offline, ``offline_answer`` picks
the matching facts by topic and says plainly when it cannot answer.
"""

from __future__ import annotations

import re
from typing import Any

from qcanvas.spec.models import CircuitSpec, NetworkSpec


def ask_context(spec: CircuitSpec | NetworkSpec, result: dict[str, Any]) -> dict[str, Any]:
    """The facts a question may be answered from (compact: no code, no full state vectors)."""
    drop = ({"operations": {"__all__": {"source"}}} if isinstance(spec, CircuitSpec)
            else {"nodes": {"__all__": {"source", "position"}}, "links": {"__all__": {"source"}}})
    ctx: dict[str, Any] = {"spec": spec.model_dump(mode="json", by_alias=True, exclude_none=True, exclude=drop)}
    ctx["explanation"] = (result.get("explanation") or {}).get("text")
    if isinstance(spec, CircuitSpec):
        v = result.get("verdict") or {}
        ins = result.get("insights") or {}
        ctx.update({
            "kind": "circuit", "verified": result.get("verified"), "summary": result.get("summary"),
            "noise": v.get("noise"), "verdict_reason": v.get("reason"), "metrics": v.get("metrics"),
            "ideal": v.get("ideal"), "measured": v.get("measured"), "expected_with_noise": v.get("expected"),
            "planted_fault": result.get("fault"),
            "attempts": [{"attempt": a.get("attempt"), "passed": a.get("passed"), "diagnosis": a.get("diagnosis"),
                          "fix": a.get("fix_summary")} for a in result.get("attempts", [])],
            "entanglement": (ins.get("entanglement") or {}).get("summary"),
            "entangled_pairs": (ins.get("entanglement") or {}).get("pairs"),
            "error_budget": ins.get("budget"), "hardware_sweep": (ins.get("sweep") or {}).get("summary"),
            "readout_correction": (ins.get("mitigation") or {}).get("summary"),
        })
    else:
        ctx.update({
            "kind": "network", "summary": result.get("summary"),
            "before": (result.get("before") or {}).get("end_to_end"),
            "after": (result.get("after") or {}).get("end_to_end"),
            "weakest_link": (result.get("before") or {}).get("weakest_link"),
            "links": (result.get("before") or {}).get("links"),
            "fixes_tried": [{k: c.get(k) for k in ("round", "description", "applied", "key_rate_bps", "fidelity")}
                            for c in result.get("candidates", [])],
            "sanity_checks": result.get("checks"),
        })
    return ctx


TOPICS: list[tuple[str, re.Pattern[str]]] = [
    ("repair", re.compile(r"fail|repair|fix|bug|wrong|attempt|broke|planted", re.I)),
    ("entanglement", re.compile(r"entangl|concurrence|bell|ghz|correlat", re.I)),
    ("hardware", re.compile(r"hardware|how good|better device|99|improve|scale", re.I)),
    ("budget", re.compile(r"noise|error|budget|decoher|t1|t2|gate error|cost", re.I)),
    ("readout", re.compile(r"readout|mitigat|correct", re.I)),
    ("verify", re.compile(r"verif|pass|fidelity|distance|tvd|threshold|trust|sure|prove", re.I)),
    ("bottleneck", re.compile(r"bottleneck|weakest|slow|loss|db|link", re.I)),
    ("key", re.compile(r"key|secure|qkd|qber|bbm92", re.I)),
    ("what", re.compile(r"\bexplain\b|what happen|how does (it|this|the)|what (does|did|is) (it|this|the|my) "
                        r"(circuit|network|design|run|result)|what does (it|this) (do|mean)", re.I)),
]

OFFLINE_HELP = ("Offline mode answers from this run's facts about: why an attempt failed and how it was fixed, the "
                "entanglement, the noise budget, how good the hardware must be, readout correction, the verification "
                "numbers, and for networks the bottleneck, the fixes and the key rate. With a Meta key, Muse Spark "
                "answers any question about this run.")


def _pct(x: float | None) -> str:
    return "unknown" if x is None else f"{x * 100:.1f}%"


def offline_answer(question: str, ctx: dict[str, Any]) -> str:
    """Answer from the facts by topic; never invents anything."""
    for topic, pattern in TOPICS:
        if not pattern.search(question):
            continue
        text = _answer(topic, ctx)
        if text:
            return text
    return f"I can't answer that offline. {OFFLINE_HELP}"


def _answer(topic: str, c: dict[str, Any]) -> str | None:
    if c["kind"] == "circuit":
        m = c.get("metrics") or {}
        if topic == "repair":
            failed = [a for a in c.get("attempts", []) if not a.get("passed")]
            if not failed:
                return (f"Nothing failed: the first attempt matched the prediction ({c.get('summary')}). "
                        "Turn on Demo mode to plant a bug and watch the agent repair it.")
            parts = []
            fault = c.get("planted_fault")
            if fault:
                parts.append(f"Demo mode planted a bug on purpose: {fault.get('label')} ({fault.get('description')}).")
            for a in failed:
                d = a.get("diagnosis") or {}
                line = f"Attempt {a['attempt']} failed: {d.get('summary', 'it did not match')}"
                if d.get("hint"):
                    line += f"; {d['hint']}"
                if a.get("fix"):
                    line += f". The fix: {a['fix']}"
                parts.append(line + ".")
            parts.append(c.get("summary") or "")
            return " ".join(p for p in parts if p)
        if topic == "entanglement" and c.get("entanglement"):
            return c["entanglement"]
        if topic == "hardware" and c.get("hardware_sweep"):
            return c["hardware_sweep"]
        if topic == "budget" and c.get("error_budget"):
            b = c["error_budget"]
            rows = "; ".join(f"{i['label'][0].lower()}{i['label'][1:]} {_pct(i['fidelity_loss'])}" for i in b.get("items", []))
            return f"{b.get('summary')} Each source alone: {rows}."
        if topic == "readout" and c.get("readout_correction"):
            return c["readout_correction"]
        if topic == "verify" and m:
            return (f"{c.get('verdict_reason')}. The run is compared with an exact prediction computed from the spec "
                    f"under the same noise, never from the code. Distance {m.get('tvd', 0):.3f} against a limit of "
                    f"{m.get('tvd_threshold', 0):.3f} set by shot noise for {m.get('shots')} shots; match to the "
                    f"prediction {m.get('fidelity', 0):.4f}; match to the noiseless ideal "
                    f"{m.get('fidelity_vs_ideal', 0):.3f}.")
        if topic == "what" and c.get("explanation"):
            return c["explanation"].split("\n\n")[0]
        return None
    before, after = c.get("before") or {}, c.get("after") or {}
    if topic in ("bottleneck", "what") and c.get("weakest_link"):
        w = c["weakest_link"]
        return f"The bottleneck is {w['from']} → {w['to']}: {w['reason']}."
    if topic in ("repair", "hardware", "budget"):
        applied = [f["description"] for f in c.get("fixes_tried", []) if f.get("applied")]
        if applied:
            return f"The agent applied: {'; then '.join(applied)}. {c.get('summary')}"
        return "No candidate fix improved this network, so the design was left as it was."
    if topic == "key" and before:
        text = (f"Before: {before.get('key_rate_bps', 0):.3g} bit/s of secret key at an error rate of "
                f"{_pct(before.get('qber'))}")
        if after:
            text += f"; after the fixes: {after.get('key_rate_bps', 0):.3g} bit/s at {_pct(after.get('qber'))}"
        return text + ". BBM92 gives no key above about 11% errors."
    if topic == "verify" and c.get("sanity_checks"):
        ok = sum(1 for s in c["sanity_checks"] if s.get("passed"))
        return f"{ok} of {len(c['sanity_checks'])} physics sanity checks passed: " + "; ".join(
            f"{s['name']} ({s['detail']})" for s in c["sanity_checks"]) + "."
    if topic == "what" and c.get("explanation"):
        return c["explanation"].split("\n\n")[0]
    return None
