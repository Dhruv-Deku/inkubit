"""Does Muse Spark get better at designing circuits when it sees what exact physics said? (backend/inkubit/learning.py)

    .venv/Scripts/python scripts/learning_bench.py

Three targets (W on 4 qubits, Dicke(4,2), W on 5 qubits in a line), five rounds of up to four layouts each, in three
conditions: with feedback, without feedback, and random wiring of the same lengths. Live calls are billed (about 30
calls); responses are cached, so a re-run is free. Writes examples/learning_benchmark.json and docs/LEARNING.md.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("INKUBIT_MODEL_PROVIDER", "meta")
os.environ["INKUBIT_ALLOW_FALLBACK"] = "0"

from inkubit.adapters.registry import get_models  # noqa: E402
from inkubit.learning import ROUNDS, TARGETS, run_all  # noqa: E402

LABEL = {"feedback": "With feedback", "fresh": "No feedback", "random": "Random wiring"}


def main() -> None:
    models = get_models()
    if not (models.settings.provider == "meta" and models.settings.has_key):
        sys.exit("needs META_API_KEY in .env (live Muse Spark)")
    t0 = time.time()
    results = []
    for gid, goal in TARGETS.items():
        def on_round(condition: str, rd) -> None:
            v = [p.verdict for p in rd.proposals]
            print(f"  {gid:8} {condition:8} round {rd.round}: {v.count('reached')} reached, {v.count('missed')} missed, "
                  f"{v.count('invalid') + v.count('repeat')} invalid/repeat; best so far {rd.best_so_far}", flush=True)

        res = run_all(goal, models.reasoning, on_round=on_round)
        results.append(res)
        print(f"{gid}: curves {res['curves']}", flush=True)
    out = {"model": models.settings.reasoning_model, "rounds": ROUNDS, "seconds": round(time.time() - t0, 1), "targets": results}
    (ROOT / "examples" / "learning_benchmark.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    write_doc(out)
    print("wrote examples/learning_benchmark.json and docs/LEARNING.md")


def fmt(v) -> str:
    return "–" if v is None else str(v)


def write_doc(out: dict) -> None:
    lines = ["# An AI scientist that learns under proof", "",
             f"Muse Spark (`{out['model']}`) proposed CNOT layouts for three target states over {out['rounds']} rounds "
             "of up to four layouts each (`scripts/learning_bench.py`, `backend/inkubit/learning.py`). The exact "
             "optimiser judged every layout and Qiskit proved every one that reached the target. With feedback, each "
             "round's prompt listed every earlier layout and its verdict; without feedback, the same model was asked "
             "afresh; random wiring used the same lengths as the feedback run with random allowed pairs.", "",
             "Fewest proven CNOTs after each round (– means none proven yet):", ""]
    for t in out["targets"]:
        g = t["goal"]
        lines += [f"## {g['title']}", "", f"Lower bound from the state's structure: {t['lower_bound']} CNOTs.", "",
                  "| Condition | " + " | ".join(f"Round {i + 1}" for i in range(out["rounds"])) + " | Layouts that reached the target |",
                  "| --- | " + " | ".join("---" for _ in range(out["rounds"])) + " | --- |"]
        for k in ("feedback", "fresh", "random"):
            lines.append(f"| {LABEL[k]} | " + " | ".join(fmt(v) for v in t["curves"][k]) + f" | {t['reach_rate'][k] * 100:.0f}% |")
        lines.append("")
    (ROOT / "docs" / "LEARNING.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
