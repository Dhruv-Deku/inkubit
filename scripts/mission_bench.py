"""Mission control benchmark: 30 varied problems run live, scored on what can go wrong.

    .venv/Scripts/python scripts/mission_bench.py

For each mission: did Muse Spark produce a usable plan (or did the offline planner have to stand in), how many
steps, how many failed, were repaired, were flagged by verification, how many numbers in the report were traced to a
tool result, and how long it took. A few missions are hard on purpose: a number the Shor tool cannot factor, a
problem with no quantum angle, and an ambiguous one. Writes examples/mission_benchmark.json and docs/MISSIONS.md.
Live calls are billed (about a cent per mission); responses are cached, so a re-run is free.
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

from qcanvas.adapters.registry import get_models  # noqa: E402
from qcanvas.mission import Ctx, Mission, run_mission  # noqa: E402

MISSIONS = [
    "Compare the hydrogen molecule at 0.6, 1.0 and 2.0 angstrom and say where the classical shortcut fails.",
    "Is a spy listening to 40% of the photons caught? And one listening to 10%?",
    "Factor 15 with Shor's algorithm using the bases 2, 7 and 13 and compare how often each run succeeds on noisy hardware.",
    "Plan a 300 km fiber link and a 1,500 km satellite link; which gives more secret key per second?",
    "Make a 5-qubit GHZ state, find a shorter equivalent if there is one, and check how well it survives realistic noise.",
    "Run 3-qubit Grover search and the swap test; which one is more fragile under realistic noise?",
    "Seven friends with feuds Ann-Ben, Ben-Cat, Cat-Dan, Dan-Eve, Eve-Fay, Fay-Gus, Gus-Ann: split them over two tables and say how well QAOA does.",
    "When does error correction start to help, for today's gates and for gates ten times better?",
    "Turn the state (|00⟩ + |11⟩)/√2 into a circuit and check how it survives noise with the ML verifier.",
    "Run Simon's algorithm and Bernstein-Vazirani and tell me whether their answers survive realistic noise.",
    "How does the energy of H2 at its equilibrium bond length compare between Hartree-Fock, the exact answer and noisy VQE with mitigation?",
    "A bank wants to link two data centres 80 km apart with quantum keys. Plan the link and check an eavesdropper on 25% of photons.",
    "Run the quantum Fourier transform period-finding example and the phase estimation example; do they still give the right answer with noise?",
    "Build a W state on 3 qubits, then check whether a shorter circuit exists and how robust it is.",
    "Teleport a qubit and swap entanglement between two pairs; which protocol loses more to noise?",
    "Schedule four exams, Maths, Art, Music and Biology, with clashes Maths-Art, Art-Music, Music-Biology, Biology-Maths, over two days.",
    "What does the circuit h q[0]; cx q[0],q[1]; cx q[1],q[2]; measure all produce, and how entangled is it?",
    "Plan a quantum network link of 2,000 km by satellite and of 2,000 km of fiber with 3 repeaters.",
    "Compare a half adder circuit and a Toffoli AND circuit under realistic noise.",
    "Simulate the 3-spin quantum magnet example and tell me how much the noise changes its outcome odds.",
    "Is the Deutsch-Jozsa example still decisive on realistic hardware? Check it with the ML verifier too.",
    "Which is worse for H2 at 2.5 angstrom: the Hartree-Fock error or the raw noisy VQE error?",
    "Check BB84 with no eavesdropper and with one on every photon; what happens to the key?",
    "For a 600 km fiber link, what is the weakest part and the best fix?",
    "Run Grover on 2 qubits and on 3 qubits and compare their success under noise.",
    "Explain how the bit-flip code example corrects an error and whether it survives noise.",
    "Translate the Quil program H 0; CNOT 0 1 into a circuit and simulate it.",
    "Factor 21 with Shor's algorithm.",
    "Use a quantum computer to sort a list of a million numbers faster.",
    "Do something interesting with entanglement.",
]


def main() -> None:
    models = get_models()
    s = models.settings
    if not (s.provider == "meta" and s.has_key):
        sys.exit("needs META_API_KEY in .env (live Muse Spark)")
    ctx = Ctx(live=True, reasoning=models.reasoning, deep_model=s.deep_model)
    rows = []
    for k, goal in enumerate(MISSIONS, 1):
        m = Mission(goal)
        t0 = time.time()
        run_mission(m, ctx)
        steps = [n for n in m.nodes.values() if n.lane == "step"]
        plan = m.nodes.get("plan")
        r = m.report
        row = {
            "mission": goal, "status": m.status, "error": m.error,
            "planner": "muse" if r and r.router == "muse" else "offline",
            "plan_note": plan.detail if plan else "",
            "steps": len(steps), "tools": [n.tool for n in steps],
            "verified": sum(n.status in ("done", "repaired") for n in steps),
            "repaired": sum(n.status == "repaired" for n in steps),
            "flagged": sum(n.status == "flagged" for n in steps),
            "failed": sum(n.status in ("failed", "skipped") for n in steps),
            "ml_notes": sum(1 for n in steps for c in n.checks if not c.affects and not c.ok),
            "numbers_checked": r.trace["checked"] if r else 0, "numbers_traced": (r.trace["traced"] + r.trace["given"]) if r else 0,
            "untraced": r.trace["untraced"] if r else [], "headline": r.headline if r else "",
            "seconds": round(time.time() - t0, 1),
        }
        rows.append(row)
        print(f"{k:2}. {row['status']:6} {row['planner']:7} steps {row['steps']} ok {row['verified']} rep {row['repaired']} "
              f"flag {row['flagged']} fail {row['failed']} traced {row['numbers_traced']}/{row['numbers_checked']} "
              f"{row['seconds']}s | {goal[:60]}", flush=True)
    out = ROOT / "examples" / "mission_benchmark.json"
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    write_doc(rows)
    print(f"wrote {out} and docs/MISSIONS.md")


def write_doc(rows: list[dict]) -> None:
    n = len(rows)
    done = sum(r["status"] == "done" for r in rows)
    muse = sum(r["planner"] == "muse" for r in rows)
    steps = sum(r["steps"] for r in rows)
    ver = sum(r["verified"] for r in rows)
    rep = sum(r["repaired"] for r in rows)
    flag = sum(r["flagged"] for r in rows)
    fail = sum(r["failed"] for r in rows)
    chk = sum(r["numbers_checked"] for r in rows)
    trc = sum(r["numbers_traced"] for r in rows)
    secs = sorted(r["seconds"] for r in rows)
    lines = [
        "# Mission control benchmark", "",
        f"{n} varied problems run live with Muse Spark planning and reporting (`scripts/mission_bench.py`). Three are "
        "hard on purpose: a number the Shor tool cannot factor (21), a problem with no quantum angle (sorting), and an "
        "ambiguous one.", "",
        "| Measure | Result |", "| --- | --- |",
        f"| Missions that finished with a report | {done} of {n} |",
        f"| Plans written by Muse Spark (not the offline stand-in) | {muse} of {n} |",
        f"| Steps run | {steps} |",
        f"| Steps verified (including repaired ones) | {ver} of {steps} |",
        f"| Steps repaired by the model after an error | {rep} |",
        f"| Steps flagged by a physics check | {flag} |",
        f"| Steps that failed or were skipped | {fail} |",
        f"| Numbers in the reports traced to a tool result | {trc} of {chk} |",
        f"| Time per mission | median {secs[n // 2]:.0f} s, slowest {secs[-1]:.0f} s |", "",
        "## Every mission", "",
        "| # | Mission | Steps | Verified | Repaired | Flagged | Failed | Traced | Seconds | Headline |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for k, r in enumerate(rows, 1):
        head = r["headline"].replace("|", "/")[:160]
        lines.append(f"| {k} | {r['mission'].replace('|', '/')} | {r['steps']} | {r['verified']} | {r['repaired']} | "
                     f"{r['flagged']} | {r['failed']} | {r['numbers_traced']}/{r['numbers_checked']} | {r['seconds']} | {head} |")
    (ROOT / "docs" / "MISSIONS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
