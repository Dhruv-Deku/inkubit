"""Code lab benchmark: Muse Spark designs error-correcting codes in rounds; exact checks prove each one (inkubit.codes).

    .venv/Scripts/python scripts/codes_bench.py

Three targets (1 logical qubit in 5; a CSS code with 1 in 7; 1 in 9 tailored to Z-biased noise), four rounds of up
to three codes each, every earlier verdict in the next prompt. Known codes are scored by the same checker. Live calls
are billed (about 12); responses are cached. Writes examples/codes_benchmark.json and docs/CODES.md.
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
from inkubit.codes import ROUNDS, TARGETS, references, run  # noqa: E402


def main() -> None:
    models = get_models()
    if not (models.settings.provider == "meta" and models.settings.has_key):
        sys.exit("needs META_API_KEY in .env (live Muse Spark)")
    t0 = time.time()
    results = []
    for t in TARGETS.values():
        def on_round(tid, rd) -> None:
            print(f"  {tid:10} round {rd.round}: " + "; ".join(c["verdict"] for c in rd.codes), flush=True)

        res = run(t, models.reasoning, on_round=on_round)
        results.append(res)
        b = res["best"]
        print(f"{t.id}: curve {res['curve']}; best {b['verdict'] if b else 'none'}", flush=True)
    out = {"model": models.settings.reasoning_model, "rounds": ROUNDS, "references": references(), "targets": results,
           "seconds": round(time.time() - t0, 1)}
    (ROOT / "examples" / "codes_benchmark.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    write_doc(out)
    print("wrote examples/codes_benchmark.json and docs/CODES.md")


def write_doc(out: dict) -> None:
    lines = ["# Code lab: AI-designed error-correcting codes", "",
             f"Muse Spark (`{out['model']}`) proposed stabilizer codes over {out['rounds']} rounds of up to three per target, "
             "seeing every earlier verdict (`scripts/codes_bench.py`, `backend/inkubit/codes.py`). Each code was checked "
             "exactly: commuting, independent generators, k = n - rank, and the distance d by brute force over every "
             "Pauli error from weight 1 up (dX, dZ: only X, only Z errors).", "",
             "## Known codes, scored by the same checker", "",
             "| Code | [[n,k,d]] | dX | dZ | CSS |", "| --- | --- | --- | --- | --- |"]
    for r in out["references"]:
        lines.append(f"| {r['name']} | [[{r['n']},{r['k']},{r['d']}]] | {r['dx']} | {r['dz']} | {'yes' if r['css'] else 'no'} |")
    for t in out["targets"]:
        tg, b = t["target"], t["best"]
        lines += ["", f"## {tg['title']}", "", f"Aim: {tg['goal']}.", "",
                  f"Best after each round: {', '.join('–' if v is None else str(v) for v in t['curve'])} "
                  f"({'dZ' if tg['objective'] == 'dz' else 'd'}).", "",
                  "| Round | Code | Verdict |", "| --- | --- | --- |"]
        for rd in t["rounds"]:
            for c in rd["codes"]:
                lines.append(f"| {rd['round']} | `{' '.join(c['generators'])}` | {c['verdict']} |")
        if b:
            lines += ["", f"Best: `{' '.join(b['generators'])}`, {b['verdict']}; idea: {b['why']}"]
    (ROOT / "docs" / "CODES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
