"""Plant every fault in every example circuit and record what the agent does.

    .venv/Scripts/python scripts/benchmark.py [--noise realistic] [--workers 4]

Writes docs/BENCHMARK.md. Offline (template code + rule-based repairer), so it
measures the loop and the verifier, not a model. A repairable fault counts as
handled when the run ends verified; the fake-result fault counts as handled
when the run ends NOT verified (the verifier caught it).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from inkubit.adapters.mock_code import MockCodeModel  # noqa: E402
from inkubit.agent.faults import FAULTS  # noqa: E402
from inkubit.agent.loop import AgentOptions, run_agent  # noqa: E402
from inkubit.spec import parse_spec  # noqa: E402
from inkubit.spec.models import CircuitSpec  # noqa: E402

UNREPAIRABLE = {"fake_result"}


def circuits() -> dict[str, CircuitSpec]:
    out = {}
    for path in sorted((ROOT / "examples" / "specs").glob("*.json")):
        if path.stem == "invalid_circuit":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("kind") == "circuit":
            out[path.stem] = parse_spec(data)
    return out


def run(name: str, spec: CircuitSpec, fault: str | None, noise: str) -> dict:
    start = time.perf_counter()
    result = run_agent(spec, MockCodeModel(), AgentOptions(noise=noise, demo_fault=fault))
    planted = result.fault["name"] if result.fault else None
    if fault and planted != fault:
        outcome = "n/a"  # this fault cannot be planted in this circuit (e.g. no CNOT to delete)
    elif fault in UNREPAIRABLE:
        outcome = "caught" if not result.verified else "MISSED"
    else:
        outcome = "verified" if result.verified else "FAILED"
    return {"circuit": name, "title": spec.metadata.title or name, "fault": fault or "none", "outcome": outcome,
            "attempts": len(result.attempts), "seconds": round(time.perf_counter() - start, 1)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--noise", default="realistic")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    specs = circuits()
    faults = [None, *FAULTS]
    jobs = [(n, s, f) for n, s in specs.items() for f in faults]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda j: run(*j, args.noise), jobs))
    elapsed = time.perf_counter() - t0

    planted = [r for r in rows if r["outcome"] != "n/a"]
    good = [r for r in planted if r["outcome"] in ("verified", "caught")]
    repaired = [r for r in planted if r["fault"] not in ("none", *UNREPAIRABLE)]
    lines = [
        "# Planted-fault benchmark",
        "",
        f"Every example circuit, run under the `{args.noise}` noise preset, once clean and once with each fault "
        "that can be planted in it. Offline: template code and the rule-based repairer, so this measures the agent "
        "loop and the independent verifier, not a language model. Regenerate with `scripts/benchmark.py`.",
        "",
        f"**{len(good)} of {len(planted)} runs ended correctly**: clean runs and repairable faults verified, "
        f"fake results caught. Repairable faults fixed: "
        f"{sum(r['outcome'] == 'verified' for r in repaired)} of {len(repaired)}. "
        f"Fake results caught: {sum(r['outcome'] == 'caught' for r in planted if r['fault'] in UNREPAIRABLE)} of "
        f"{sum(r['fault'] in UNREPAIRABLE for r in planted)}. Wall time {elapsed:.0f} s.",
        "",
        "| Circuit | " + " | ".join(f or "clean" for f in faults) + " |",
        "| --- | " + " | ".join("---" for _ in faults) + " |",
    ]
    for name in specs:
        cells = []
        for f in faults:
            r = next(x for x in rows if x["circuit"] == name and x["fault"] == (f or "none"))
            mark = {"verified": "✓", "caught": "caught", "n/a": "–"}.get(r["outcome"], f"**{r['outcome']}**")
            cells.append(mark if r["outcome"] in ("n/a", "caught") else f"{mark} ({r['attempts']})")
        lines.append(f"| {specs[name].metadata.title or name} | " + " | ".join(cells) + " |")
    lines += ["", "✓ (n) = verified after n attempts; caught = the verifier refused a faked result; "
              "– = the fault cannot be planted in this circuit.", ""]
    out = ROOT / "docs" / "BENCHMARK.md"
    out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("\n".join(lines[:7]))
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
