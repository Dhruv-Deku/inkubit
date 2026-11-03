"""A finished mission as one self-contained HTML page, to download and keep like a lab notebook.

The goal, the plan, every step with its result, its checks and its arguments, the report with each number marked as
traced to a tool result (green) or not (amber), the model calls, and standalone Qiskit code for every circuit a step
produced. Styles are inline, so the file opens anywhere without Inkubit running; every number comes from the run.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from inkubit.copilot import _NUM
from inkubit.mission import Mission, Node, circuit_of
from inkubit.report import CSS, _e

EXTRA_CSS = """
.ok { text-decoration: underline 2px #4cc38a; text-underline-offset: 3px; }
mark.no { background: rgba(227,160,8,.18); color: #e3a008; border-radius: 3px; padding: 0 2px; }
.warn { background: rgba(227,160,8,.14); color: #e3a008; }
.headline { font-size: 17px; font-weight: 600; margin-bottom: 8px; }
ul { margin: 0 0 10px; padding-left: 20px; } li { margin: 4px 0; }
.checks li { list-style: none; margin-left: -20px; }
details summary { cursor: pointer; color: #9a9ca3; font-size: 13px; margin-top: 8px; }
code { font: 12.5px 'JetBrains Mono', Consolas, monospace; }
"""

STATUS = {"done": ("verified", "pass"), "repaired": ("repaired, verified", "pass"), "flagged": ("flagged", "warn"),
          "failed": ("failed", "fail"), "skipped": ("skipped", "fail"), "waiting": ("not run", "fail"),
          "running": ("running", "warn"), "verifying": ("verifying", "warn")}


def marked(text: str, untraced: list[str]) -> str:
    """The text with every number the tracer checks marked: green if found in a tool result (or the request), amber
    if not. Small counts and bitstrings are left plain, as the tracer leaves them unchecked."""
    out, last = [], 0
    for m in _NUM.finditer(text):
        value, pct = m.group(1), bool(m.group(2))
        out.append(_e(text[last:m.start()]))
        last = m.end()
        small = not pct and "." not in value and abs(float(value.replace(",", ""))) <= 12
        bits = not pct and len(value) >= 2 and set(value) <= {"0", "1"}
        token = m.group(0)
        if small or bits:
            out.append(_e(token))
        elif token.strip() in untraced:
            out.append(f'<mark class="no" title="not found in any tool result">{_e(token)}</mark>')
        else:
            out.append(f'<span class="ok" title="found in a tool result">{_e(token)}</span>')
    out.append(_e(text[last:]))
    return "".join(out)


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    if isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False, separators=(", ", ": "))
        return s if len(s) <= 160 else s[:157] + "…"
    return str(v)


def _facts(facts: dict[str, Any]) -> str:
    rows = []
    for k, v in facts.items():
        if isinstance(v, dict) and len(v) <= 12 and all(not isinstance(x, (dict, list)) for x in v.values()):
            rows += [(f"{k} · {k2}", v2) for k2, v2 in v.items()]
        else:
            rows.append((k, v))
    if not rows:
        return ""
    body = "".join(f"<tr><td>{_e(k)}</td><td class='num'>{_e(_fmt(v))}</td></tr>" for k, v in rows[:40])
    return f"<table><tr><th>Result</th><th class='num'>Value</th></tr>{body}</table>"


def _code(node: Node) -> str:
    raw = circuit_of(node.card)
    if not raw:
        return ""
    try:
        from inkubit.codegen.template import generate_code
        from inkubit.spec import parse_spec

        code = generate_code(parse_spec(raw), noise="realistic")
    except Exception:  # noqa: BLE001 - a circuit the template cannot write is simply left out
        return ""
    return f"<details><summary>Standalone Qiskit code for this circuit (realistic noise)</summary><pre>{_e(code)}</pre></details>"


def _step(node: Node) -> str:
    label, cls = STATUS.get(node.status, (node.status, "warn"))
    checks = "".join(
        f"<li>{'✓' if c.ok else ('·' if not c.affects else '✗')} <b>{_e(c.name)}</b>: {_e(c.detail)}"
        f"{'' if c.affects else ' <span class=sub>(grades the ML model; the step reports the exact value)</span>'}</li>"
        for c in node.checks)
    after = f" · after {', '.join(node.after)}" if node.after else ""
    model = f" · {_e(node.model)}" if node.model else ""
    return (f"<section id='{_e(node.id)}'><h2>{_e(node.id)} · {_e(node.label)} <span class='badge {cls}'>{_e(label)}</span></h2>"
            f"<p class='sub'>{_e(node.tool or '')}{after}{model} · {node.seconds:.1f} s</p>"
            + (f"<p>{_e(node.purpose)}</p>" if node.purpose else "")
            + (f"<p>{_e(node.detail)}</p>" if node.detail else "")
            + _facts(node.facts)
            + (f"<h2 style='margin-top:14px'>Checks</h2><ul class='checks'>{checks}</ul>" if checks else "")
            + (f"<details><summary>Arguments</summary><pre>{_e(json.dumps(node.args, indent=1, ensure_ascii=False))}</pre></details>" if node.args else "")
            + _code(node) + "</section>")


def render(m: Mission) -> str:
    nodes = list(m.nodes.values())
    steps = [n for n in nodes if n.lane == "step"]
    pre = [n for n in nodes if n.lane in ("perceive", "plan")]
    r = m.report
    verified = sum(n.status in ("done", "repaired") for n in steps)
    tiles = [("Steps verified", f"{verified} of {len(steps)}"), ("Repaired", str(sum(n.status == "repaired" for n in steps))),
             ("Flagged", str(sum(n.status == "flagged" for n in steps)))]
    if r:
        traced = r.trace.get("traced", 0) + r.trace.get("given", 0)
        tiles += [("Numbers traced", f"{traced} of {r.trace.get('checked', 0)}"), ("Time", f"{r.seconds:.0f} s"),
                  ("Planned by", "Muse Spark" if r.router == "muse" else "offline planner")]
    tile_html = "".join(f"<div class='tile'><div class='k'>{_e(k)}</div><div class='v'>{_e(v)}</div></div>" for k, v in tiles)
    report = ""
    if r:
        untraced = [str(u) for u in r.trace.get("untraced", [])]
        findings = "".join(f"<li>{marked(f, untraced)}</li>" for f in r.findings)
        report = (f"<section><h2>Report</h2><p class='headline'>{marked(r.headline, untraced)}</p><ul>{findings}</ul>"
                  + (f"<p class='sub'>{marked(r.next, untraced)}</p>" if r.next else "")
                  + "<p class='sub'><span class='ok'>Underlined green</span>: found in a tool result (or the request). "
                  + (f"<mark class='no'>Amber</mark>: not found in any ({len(untraced)})." if untraced else "No number was left untraced.")
                  + "</p></section>")
    plan_rows = "".join(
        f"<tr><td><a href='#{_e(n.id)}' style='color:inherit'>{_e(n.id)}</a></td><td>{_e(n.tool or '')}</td><td>{_e(n.purpose or n.label)}</td>"
        f"<td>{_e(', '.join(n.after))}</td><td>{_e(STATUS.get(n.status, (n.status,))[0])}</td><td class='num'>{n.seconds:.1f}</td></tr>"
        for n in steps)
    plan = (f"<section><h2>Plan</h2>"
            + "".join(f"<p class='sub'>{_e(n.label)}: {_e(n.detail)}</p>" for n in pre)
            + f"<table><tr><th>Step</th><th>Tool</th><th>Purpose</th><th>After</th><th>Status</th><th class='num'>Seconds</th></tr>{plan_rows}</table></section>")
    calls = ""
    if r and r.calls:
        rows = "".join(f"<tr><td>{_e(c.model)}</td><td>{_e(c.role)}</td><td>{'cached' if c.cached else 'live'}</td>"
                       f"<td class='num'>{(c.latency_s or 0):.1f}</td></tr>" for c in r.calls)
        calls = f"<section><h2>Model calls</h2><table><tr><th>Model</th><th>Job</th><th>Call</th><th class='num'>Seconds</th></tr>{rows}</table></section>"
    status = {"done": ("Finished", "pass"), "failed": ("Failed", "fail")}.get(m.status, (m.status, "warn"))
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>Mission report: {_e(m.goal[:60])}</title><style>{CSS}{EXTRA_CSS}</style></head><body><main>"
            f"<p class='sub'>Inkubit mission report · {when}</p><h1>{_e(m.goal)}</h1>"
            f"<span class='badge {status[1]}'>{_e(status[0])}</span>"
            + (f"<p class='sub' style='margin-top:8px'>{_e(m.error)}</p>" if m.error else "")
            + f"<div class='tiles'>{tile_html}</div>{report}{plan}"
            + "".join(_step(n) for n in steps) + calls
            + f"<footer>Generated by Inkubit from mission {_e(m.id)}. Every number comes from the run; each step passed "
              "the physics checks listed under it, and circuits were also re-run by a second, independent simulator. "
              "The Qiskit code for each circuit runs on its own (pip install qiskit qiskit-aer).</footer></main></body></html>")
