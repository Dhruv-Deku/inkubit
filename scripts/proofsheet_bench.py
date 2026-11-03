"""Run the proof sheet over every algorithm in the gallery and write the results.

    .venv/Scripts/python scripts/proofsheet_bench.py

Writes examples/proofsheet_benchmark.json and docs/PROOFSHEET.md: for each gallery circuit, by category, how many of
the proof sheet's checks passed, failed, were skipped (with the reason) or left a note (the ML verifier's interval
missing the exact value grades the model, not the circuit).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from inkubit import EXAMPLES_DIR  # noqa: E402
from inkubit.api.app import CATEGORIES  # noqa: E402
from inkubit.proofsheet import proof_sheet  # noqa: E402
from inkubit.spec import parse_spec  # noqa: E402


def main() -> None:
    rows, per_check, kinds = [], {}, {}
    for cat, names in CATEGORIES.items():
        for name in names:
            spec = parse_spec(json.loads((EXAMPLES_DIR / "specs" / f"{name}.json").read_text(encoding="utf-8")))
            ps = proof_sheet(spec)
            for c in ps.checks:
                per_check.setdefault(c.id, Counter())[c.status] += 1
                kinds[c.id] = (c.category, c.title, c.guards)
            rows.append({"id": name, "title": ps.title, "category": cat, "qubits": ps.num_qubits, "gates": ps.gates,
                         "passed": ps.passed, "failed": ps.failed, "skipped": ps.skipped, "notes": ps.notes,
                         "seconds": ps.seconds, "checks": {c.id: c.status for c in ps.checks},
                         "skipped_why": {c.id: c.detail for c in ps.checks if c.status == "skipped"}})
            print(f"{name:22s} {ps.summary}", flush=True)
    total = Counter()
    for r in rows:
        total.update({"passed": r["passed"], "failed": r["failed"], "skipped": r["skipped"], "notes": r["notes"]})
    out = {"date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "circuits": len(rows),
           "categories": len(CATEGORIES), "checks_per_circuit": len(kinds), "kinds": len({k[0] for k in kinds.values()}),
           "totals": dict(total), "rows": rows,
           "per_check": {cid: {"category": kinds[cid][0], "title": kinds[cid][1], "guards": kinds[cid][2],
                               **dict(per_check[cid])} for cid in kinds}}
    (ROOT / "examples" / "proofsheet_benchmark.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    lines = ["# The proof sheet over the gallery", "",
             f"`scripts/proofsheet_bench.py` ran the proof sheet ({out['checks_per_circuit']} checks of {out['kinds']} kinds, "
             f"`backend/inkubit/proofsheet.py`) on all {out['circuits']} gallery circuits in {out['categories']} categories, "
             f"{out['date_utc'][:10]}: **{total['passed']} passed, {total['failed']} failed**, {total['skipped']} skipped with "
             f"the reason, {total['notes']} notes (the ML verifier's interval missing the exact value: a note about the "
             "model, not the circuit).", "", "| Check | Kind | Guards against | Passed | Failed | Skipped | Notes |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for cid, c in out["per_check"].items():
        lines.append(f"| {c['title']} | {c['category']} | {c['guards']} | {c.get('pass', 0)} | {c.get('fail', 0)} | "
                     f"{c.get('skipped', 0)} | {c.get('note', 0)} |")
    lines += ["", "| Circuit | Category | Qubits | Gates | Passed | Failed | Skipped | Notes | Seconds |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['title']} | {r['category']} | {r['qubits']} | {r['gates']} | {r['passed']} | {r['failed']} | "
                     f"{r['skipped']} | {r['notes']} | {r['seconds']:.1f} |")
    (ROOT / "docs" / "PROOFSHEET.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{total['passed']} passed, {total['failed']} failed, {total['skipped']} skipped, {total['notes']} notes")


if __name__ == "__main__":
    main()
