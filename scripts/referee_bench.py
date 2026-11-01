"""The AI referee benchmark: Muse Spark claims, Muse Wonder challenges, exact simulation decides (backend/qcanvas/referee.py).

    .venv/Scripts/python scripts/referee_bench.py

Eight circuits no textbook contains: the six bigger ones (6 to 8 qubits) from the AI-alone benchmark, where Muse Spark
alone was weakest, and two smaller new ones. Three claims each. Live calls are billed (Muse Wonder costs more than
Muse Spark; about 24 calls in all); responses are cached, so a re-run is free. Writes examples/referee_benchmark.json
and docs/REFEREE.md.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("QCANVAS_MODEL_PROVIDER", "meta")
os.environ["QCANVAS_ALLOW_FALLBACK"] = "0"

from qcanvas.adapters.registry import get_models  # noqa: E402
from qcanvas.arena import bigger_circuits, fresh_circuits  # noqa: E402
from qcanvas.referee import debate  # noqa: E402
from qcanvas.spec import parse_spec  # noqa: E402


def circuits() -> list[tuple[str, dict]]:
    out = [(f"Bigger circuit {k + 1}", d) for k, d in enumerate(bigger_circuits())]
    out += [(f"New circuit {k + 1}", d) for k, d in enumerate(fresh_circuits()[:2])]
    return out


def main() -> None:
    models = get_models()
    s = models.settings
    if not (s.provider == "meta" and s.has_key):
        sys.exit("needs META_API_KEY in .env (live Muse Spark and Muse Wonder)")
    t0 = time.time()
    rows = []
    for title, raw in circuits():
        spec = parse_spec(raw)
        try:
            d = debate(spec, models.reasoning, s.deep_model)
        except Exception as err:  # noqa: BLE001 - a failed debate is recorded, not hidden
            print(f"{title}: no debate ({str(err)[:100]})", flush=True)
            rows.append({"title": title, "error": str(err)[:300], "qubits": spec.num_qubits})
            continue
        rows.append(d.model_dump(mode="json") | {"title": title, "qubits": spec.num_qubits, "gates": len(spec.operations)})
        print(f"{title}: Spark right {d.spark_first}/3 at first, {d.final_right}/3 after the debate; Wonder caught {d.caught}, "
              f"false alarms {d.false_alarms}, talked out {d.talked_out} ({d.seconds} s)", flush=True)
    ok = [r for r in rows if "error" not in r]
    total = 3 * len(ok)
    summary = {k: sum(r[k] for r in ok) for k in ("spark_first", "final_right", "caught", "false_alarms", "talked_out")}
    wrong_first = total - summary["spark_first"]
    out = {"spark": s.reasoning_model, "wonder": s.deep_model, "claims": total, "debates": len(ok), "summary": summary,
           "wrong_at_first": wrong_first, "seconds": round(time.time() - t0, 1), "rows": rows}
    (ROOT / "examples" / "referee_benchmark.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    write_doc(out)
    print(json.dumps(summary), f"of {total} claims")


def write_doc(out: dict) -> None:
    s, n = out["summary"], out["claims"]
    lines = ["# The AI referee", "",
             f"Muse Spark (`{out['spark']}`) made three checkable claims about each of {out['debates']} circuits no textbook "
             f"contains; Muse Wonder (`{out['wonder']}`) agreed with or disputed each; Muse Spark then stood by or conceded "
             "each disputed claim. Exact simulation graded every position (`scripts/referee_bench.py`).", "",
             "| Measure | Result |", "| --- | --- |",
             f"| Muse Spark's claims right as first stated | {s['spark_first']} of {n} |",
             f"| Answers right after the debate | {s['final_right']} of {n} |",
             f"| Wrong claims Muse Wonder caught with the right answer | {s['caught']} of {out['wrong_at_first']} |",
             f"| Right claims Muse Wonder disputed (false alarms) | {s['false_alarms']} |",
             f"| Right claims Muse Spark was talked out of | {s['talked_out']} |", "",
             "| Circuit | Claim | Truth | Muse Wonder | Final | Right at first | Right after |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in out["rows"]:
        if "error" in r:
            lines.append(f"| {r['title']} | no debate: {r['error'][:80]} | | | | | |")
            continue
        for c in r["claims"]:
            ch = "agrees" if c["challenge"]["agree"] else f"disputes: {c['challenge']['counter']}"
            lines.append(f"| {r['title']} | {c['claim_text']} | {c['truth']} | {ch} | {c['final']} | "
                         f"{'yes' if c['claim_right'] else 'no'} | {'yes' if c['final_right'] else 'no'} |")
    (ROOT / "docs" / "REFEREE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
