"""AI alone vs Q-Canvas: ask Muse Spark to predict circuits' outcome odds on its own, with no simulator.

Two sets: the textbook examples (famous circuits a model has seen many times) and new circuits no textbook contains
(seeded, like a student's own sketch). Needs the live model (META_API_KEY in .env). Answers are cached, so a re-run
costs nothing. Writes examples/arena_benchmark.json (shown on the start page) and docs/ARENA.md.

    .venv/Scripts/python scripts/arena_bench.py
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
from qcanvas.arena import BENCH_FILE, BenchRow, ask_alone, bigger_circuits, fresh_circuits, summarise  # noqa: E402
from qcanvas.bughunt import _load  # noqa: E402
from qcanvas.spec import parse_spec  # noqa: E402

TEXTBOOK = ["bell", "ghz3", "superposition", "superdense", "toffoli_and", "deutsch_jozsa", "bernstein_vazirani",
            "grover2", "w_state", "teleportation", "bit_flip_code", "phase_estimation", "shor15"]
VERIFIER = ("Q-Canvas never shows a model's answer unchecked: every run is compared with exact simulation, and in "
            "the planted-fault benchmark (docs/BENCHMARK.md) 55 of 55 runs ended correctly, including 9 of 9 faked "
            "results caught.")


def main() -> None:
    models = get_models()
    if models.settings.provider != "meta" or not models.settings.has_key:
        sys.exit("needs the live model: set META_API_KEY and QCANVAS_MODEL_PROVIDER=meta")
    todo = [("textbook", name, _load(name)) for name in TEXTBOOK]
    todo += [("new", f"new{k + 1}", d) for k, d in enumerate(fresh_circuits())]
    todo.append(("new", "qaoa_party", _load("qaoa_party")))
    todo += [("bigger", f"big{k + 1}", d) for k, d in enumerate(bigger_circuits())]
    rows = []
    for group, name, data in todo:
        spec = parse_spec(data)
        start = time.perf_counter()
        try:
            res = ask_alone(spec, models.reasoning.predict_odds)
        except Exception as err:  # noqa: BLE001 - no usable answer is a result too
            print(f"{name:20} no answer ({str(err)[:80]})", flush=True)
            rows.append(BenchRow(id=name, set=group, title=spec.metadata.title or name, qubits=spec.num_qubits,
                                 gates=len(spec.operations), tvd=None, verdict="no answer", impossible=0, missed=0,
                                 seconds=round(time.perf_counter() - start, 1)))
            continue
        c = res.comparison
        rows.append(BenchRow(id=name, set=group, title=spec.metadata.title or name, qubits=spec.num_qubits,
                             gates=len(spec.operations), tvd=round(c.tvd, 4), verdict=c.verdict,
                             impossible=len(c.impossible), missed=len(c.missed),
                             seconds=round(time.perf_counter() - start, 1)))
        print(f"{name:20} {c.verdict:8} off by {c.tvd * 100:5.1f}%  {'(cached)' if res.call['cached'] else ''}",
              flush=True)
    bench = summarise(models.settings.reasoning_model, rows, VERIFIER)
    BENCH_FILE.write_text(json.dumps(bench.model_dump(mode="json"), indent=1) + "\n", encoding="utf-8")

    def line(label: str, s) -> str:
        return (f"- **{label}**: exact on {s.matched} of {s.count}, close on {s.close}, wrong on {s.wrong}"
                f"{f', no usable answer on {s.no_answer}' if s.no_answer else ''}; on average "
                f"{s.mean_tvd * 100:.1f}% of the probability in the wrong place (over the answers given).")

    lines = [
        "# AI alone vs Q-Canvas",
        "",
        f"Muse Spark (`{bench.model}`) was asked to predict each circuit's measured outcome odds on its own, the way "
        "a chat assistant answers: the circuit as data (no title or notes), no simulator, medium reasoning effort. "
        "Answers are scored against exact simulation by total variation distance (the share of probability in the "
        "wrong place): exact below 1%, close below 5%, wrong from 5%. Two sets: the textbook examples, which a "
        "model has seen many times, and new circuits no textbook contains (seeded random circuits of 3 to 5 qubits "
        "and the six-guest QAOA circuit), which is what a student's own sketch looks like to a model, and bigger new "
        "circuits of 6 to 8 qubits (all in superposition first, 4 qubits measured). Regenerate "
        f"with `scripts/arena_bench.py`; run on {bench.date}.",
        "",
        line("Textbook circuits", bench.textbook),
        line("New circuits", bench.new),
        line("Bigger new circuits (6 to 8 qubits, 4 measured)", bench.bigger),
        "",
        "| Set | Circuit | Qubits | Gates | Model alone | Off by | Impossible outcomes given | Real outcomes missed |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        off = "–" if r.tvd is None else f"{r.tvd * 100:.1f}%"
        lines.append(f"| {r.set} | {r.title} | {r.qubits} | {r.gates} | {r.verdict} | {off} | {r.impossible} | {r.missed} |")
    lines += ["", bench.verifier, ""]
    (ROOT / "docs" / "ARENA.md").write_text("\n".join(lines), encoding="utf-8")
    for label, s in (("textbook", bench.textbook), ("new", bench.new), ("bigger", bench.bigger)):
        print(f"{label}: exact {s.matched}/{s.count}, close {s.close}, wrong {s.wrong}, no answer {s.no_answer}, "
              f"mean off {s.mean_tvd * 100:.1f}%")


if __name__ == "__main__":
    main()
