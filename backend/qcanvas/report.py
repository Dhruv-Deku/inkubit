"""A self-contained HTML report of one run, to download and share.

Everything is inline (styles, charts as embedded PNG), so the file opens
anywhere without Q-Canvas running. Every number comes from the job result.
"""

from __future__ import annotations

import base64
import html
import io
from datetime import datetime, timezone
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from qcanvas.spec.models import CircuitSpec, NetworkSpec  # noqa: E402

INK, MUTED, PANEL, LINE = "#ecebe8", "#9a9ca3", "#1b1c20", "#2f3138"
MEASURED, PREDICTED = "#3987e5", "#d95926"

CSS = """
:root { color-scheme: dark; }
body { margin: 0; background: #111214; color: #ecebe8; font: 15px/1.55 Inter, system-ui, -apple-system, 'Segoe UI', sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 32px 20px 64px; }
h1 { font-size: 30px; letter-spacing: -0.02em; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 0 0 10px; }
.sub { color: #9a9ca3; font-size: 13px; }
section { background: #1b1c20; border: 1px solid #2f3138; border-radius: 14px; padding: 18px 20px; margin-top: 16px; }
.badge { display: inline-block; padding: 4px 12px; border-radius: 999px; font-weight: 600; font-size: 14px; }
.pass { background: rgba(76,195,138,.14); color: #4cc38a; } .fail { background: rgba(229,72,77,.14); color: #e5484d; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin-top: 12px; }
.tile { background: #222328; border-radius: 11px; padding: 10px 12px; } .tile .k { font-size: 12px; color: #9a9ca3; }
.tile .v { font-size: 21px; font-weight: 600; font-variant-numeric: tabular-nums; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; } th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #2f3138; }
th { color: #9a9ca3; font-weight: 500; } td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
pre { background: #0c0d0f; border-radius: 10px; padding: 12px 14px; overflow-x: auto; font: 12.5px/1.5 'JetBrains Mono', Consolas, monospace; color: #d7d6d2; }
img { max-width: 100%; border-radius: 10px; display: block; }
p { margin: 0 0 10px; } footer { margin-top: 28px; color: #6f7279; font-size: 12px; }
"""


def _e(text: Any) -> str:
    return html.escape(str(text if text is not None else ""))


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=PANEL)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _histogram(expected: dict[str, float], measured: dict[str, float], ideal: dict[str, float]) -> str:
    keys = sorted(k for k in set(expected) | set(measured) | set(ideal)
                  if max(expected.get(k, 0), measured.get(k, 0), ideal.get(k, 0)) > 0.005)[:24]
    fig, ax = plt.subplots(figsize=(max(5, 0.7 * len(keys) + 2), 3.1))
    ax.set_facecolor(PANEL)
    x = range(len(keys))
    w = 0.38
    ax.bar([i - w / 2 for i in x], [expected.get(k, 0) for k in keys], w, facecolor=(0.85, 0.35, 0.15, 0.16),
           edgecolor=PREDICTED, linewidth=1.4, label="Predicted (exact, with noise)")
    ax.bar([i + w / 2 for i in x], [measured.get(k, 0) for k in keys], w, color=MEASURED, label="Measured")
    for i, k in enumerate(keys):
        if ideal.get(k):
            ax.hlines(ideal[k], i - 0.45, i + 0.45, colors=INK, linestyles="dashed", linewidth=1.2)
    ax.set_xticks(list(x), [f"|{k}⟩" for k in keys], color=MUTED, fontsize=9, fontfamily="monospace")
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(LINE)
    ax.grid(axis="y", color=LINE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, labelcolor=MUTED, fontsize=8.5, loc="upper right")
    return _png(fig)


def _tiles(items: list[tuple[str, str]]) -> str:
    return '<div class="tiles">' + "".join(
        f'<div class="tile"><div class="k">{_e(k)}</div><div class="v">{_e(v)}</div></div>' for k, v in items) + "</div>"


def _img(b64: str | None, alt: str) -> str:
    return f'<img alt="{_e(alt)}" src="data:image/png;base64,{b64}">' if b64 else ""


def _explanation(result: dict[str, Any]) -> str:
    exp = result.get("explanation") or {}
    if not exp.get("text"):
        return ""
    call = exp.get("call") or {}
    paras = "".join(f"<p>{_e(p)}</p>" for p in exp["text"].split("\n\n"))
    return f'<section><h2>What happened, in plain words</h2>{paras}<div class="sub">Written by {_e(call.get("model"))} ({_e(call.get("provider"))})</div></section>'


def _circuit(spec: CircuitSpec, r: dict[str, Any]) -> str:
    v = r.get("verdict") or {}
    m = v.get("metrics") or {}
    ok = r.get("verified")
    out = [f'<section><span class="badge {"pass" if ok else "fail"}">{"Verified" if ok else "Not verified"}</span>'
           f'<p style="margin-top:10px">{_e(r.get("summary"))}</p>']
    if m:
        out.append(_tiles([("Distance from prediction (TVD)", f"{m['tvd']:.3f} (limit {m['tvd_threshold']:.3f})"),
                           ("Match to prediction", f"{m['fidelity']:.4f}"),
                           ("Match to noiseless ideal", f"{m['fidelity_vs_ideal']:.3f}"),
                           ("Attempts", str(len(r.get("attempts", []))))]))
    out.append("</section>")
    if v:
        out.append(f'<section><h2>Outcomes</h2><p class="sub">{_e(v.get("reason"))}</p>'
                   f'{_img(_histogram(v["expected"], v["measured"], v["ideal"]), "Predicted vs measured")}'
                   '<div class="sub">Dashed line: the noiseless ideal. Bitstrings in Qiskit order (rightmost = bit 0).</div></section>')
    out.append(_explanation(r))
    ins = r.get("insights") or {}
    rows = []
    for key, title in (("entanglement", "Entanglement"), ("budget", "Error budget"), ("sweep", "Hardware needed"),
                       ("mitigation", "Readout correction")):
        if (ins.get(key) or {}).get("summary"):
            rows.append(f"<tr><th>{title}</th><td>{_e(ins[key]['summary'])}</td></tr>")
    if ins.get("layout_summary"):
        rows.append(f"<tr><th>Chip layouts</th><td>{_e(ins['layout_summary'])}</td></tr>")
    if rows:
        out.append(f"<section><h2>Analyses</h2><table>{''.join(rows)}</table></section>")
    att = [a for a in r.get("attempts", []) if not a.get("passed")]
    if att:
        lis = "".join(f"<tr><td>Attempt {a['attempt']}</td><td>{_e((a.get('diagnosis') or {}).get('summary'))}</td>"
                      f"<td>{_e(a.get('fix_summary') or '')}</td></tr>" for a in att)
        out.append(f"<section><h2>What the agent repaired</h2><table><tr><th>Run</th><th>Why it failed</th>"
                   f"<th>Fix</th></tr>{lis}</table></section>")
    if (r.get("exact_diagram") or {}).get("image_b64"):
        out.append(f"<section><h2>Circuit</h2>{_img(r['exact_diagram']['image_b64'], 'Circuit diagram')}</section>")
    out.append(f"<section><h2>Code</h2><pre>{_e(r.get('final_code'))}</pre></section>")
    return "".join(out)


def _network(spec: NetworkSpec, r: dict[str, Any]) -> str:
    b, a = (r.get("before") or {}).get("end_to_end") or {}, (r.get("after") or {}).get("end_to_end") or {}
    out = [f'<section><span class="badge {"pass" if r.get("fix") else "fail"}">'
           f'{"Bottleneck fixed" if r.get("fix") else "No better design found"}</span>'
           f'<p style="margin-top:10px">{_e(r.get("summary"))}</p></section>']

    def row(label: str, key: str, fmt: str) -> str:
        after = format(a[key], fmt) if a else "—"
        return f"<tr><td>{label}</td><td class='num'>{format(b.get(key, 0), fmt)}</td><td class='num'>{after}</td></tr>"
    out.append("<section><h2>Before and after</h2><table><tr><th></th><th class='num'>Before</th>"
               "<th class='num'>After</th></tr>" + row("Entangled pairs per second", "pair_rate_hz", ".3g")
               + row("End-to-end fidelity", "fidelity", ".3f") + row("Error rate (QBER)", "qber", ".3f")
               + row("Secret key rate, bit/s (BBM92)", "key_rate_bps", ".3g") + "</table></section>")
    cands = r.get("candidates") or []
    if cands:
        rows = "".join(f"<tr><td>{c['round']}</td><td>{_e(c['description'])}{' <b>(applied)</b>' if c.get('applied') else ''}"
                       f"</td><td class='num'>{c['key_rate_bps']:.3g}</td></tr>" for c in cands)
        out.append(f"<section><h2>Fixes the agent tried</h2><table><tr><th>Round</th><th>Fix</th>"
                   f"<th class='num'>Key rate, bit/s</th></tr>{rows}</table></section>")
    out.append(_explanation(r))
    checks = r.get("checks") or []
    if checks:
        rows = "".join(f"<tr><td>{'✓' if c['passed'] else '✗'} {_e(c['name'])}</td><td class='sub'>{_e(c['detail'])}</td></tr>"
                       for c in checks)
        out.append(f"<section><h2>Physics sanity checks</h2><table>{rows}</table></section>")
    if (r.get("diagram") or {}).get("image_b64"):
        out.append(f"<section><h2>Network</h2>{_img(r['diagram']['image_b64'], 'Network diagram')}</section>")
    return "".join(out)


def render_report(spec: CircuitSpec | NetworkSpec, result: dict[str, Any]) -> str:
    title = spec.metadata.title or ("Quantum circuit" if isinstance(spec, CircuitSpec) else "Quantum network")
    body = _circuit(spec, result) if isinstance(spec, CircuitSpec) else _network(spec, result)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    spec_json = _e(spec.model_dump_json(by_alias=True, exclude_none=True, indent=2))
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width, initial-scale=1'><title>{_e(title)} · Q-Canvas report</title>"
            f"<style>{CSS}</style></head><body><main><h1>{_e(title)}</h1>"
            f"<div class='sub'>Q-Canvas report · {stamp}</div>{body}"
            f"<section><h2>Spec</h2><pre>{spec_json}</pre></section>"
            f"<footer>Generated by Q-Canvas. Verification compares each run with an exact prediction computed from "
            f"the spec, never from the generated code.</footer></main></body></html>")
