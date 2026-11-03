"""Proven illustrations, measured: Muse Image draws each small gallery circuit (no captions), SAM 3.1 and Muse Spark
read the figure back, exact comparison decides, and a wrong figure is corrected with Muse Image edits (at most twice).

Writes examples/figure_benchmark.json and a small copy of every figure (first try, and the final one when it changed)
to examples/figures/. Needs the live models (META_API_KEY). Run from the repo root:

    .venv/Scripts/python scripts/figure_bench.py [--workers 3] [ids...]
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image  # noqa: E402

from inkubit import figproof  # noqa: E402
from inkubit.adapters.registry import get_models  # noqa: E402
from inkubit.spec.validation import SpecError, parse_spec  # noqa: E402

SPECS = ROOT / "examples" / "specs"
OUT = ROOT / "examples" / "figure_benchmark.json"
FIGS = ROOT / "examples" / "figures"


def small(b64: str, path: Path) -> str:
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    img.thumbnail((720, 720))
    img.save(path, format="WEBP", quality=80, method=6)
    return path.relative_to(ROOT / "examples").as_posix()


def circuits(only: set[str]) -> list[tuple[str, dict]]:
    out = []
    for f in sorted(SPECS.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("kind") != "circuit" or (only and f.stem not in only):
            continue
        try:
            s = parse_spec(d)
        except SpecError:  # the gallery's broken-on-purpose example
            continue
        ops = [o for o in s.operations if o.gate != "BARRIER"]
        if s.num_qubits <= 4 and len(ops) <= 14 and not s.is_dynamic():
            out.append((f.stem, d))
    return out


def one(models, cid: str, spec: dict) -> dict:
    t0 = time.perf_counter()
    parsed = parse_spec(spec)
    drawn = models.image.diagram(parsed, {"plain": True})
    if drawn.call.provider != "meta":
        raise RuntimeError(f"{cid}: Muse Image did not answer live ({drawn.call.error})")
    proof = figproof.prove(models, spec, drawn.image_b64, drawn.mime)
    row = {"id": cid, "title": spec.get("metadata", {}).get("title", cid), "qubits": parsed.num_qubits,
           "gates": len([o for o in parsed.operations if o.gate != "BARRIER"]),
           "verdict": proof["verdict"], "first_try": proof["verdict"] == "proven", "attempts": proof["attempts"],
           "detail": proof["detail"], "read_ops": proof["read_ops"],
           "first_image": small(drawn.image_b64, FIGS / f"{cid}-first.webp"),
           "seconds": round(time.perf_counter() - t0, 1),
           "calls": [c.model_dump(mode="json") for c in [drawn.call, *proof["calls"]]]}
    if proof["image"] != drawn.image_b64:
        row["final_image"] = small(proof["image"], FIGS / f"{cid}-final.webp")
    print(f"{cid:24s} {row['verdict']:9s} attempts {row['attempts']}  {row['seconds']:5.0f} s  {row['detail'][:90]}", flush=True)
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    models = get_models()
    if not (models.settings.provider == "meta" and models.settings.has_key):
        raise SystemExit("needs the live models (META_API_KEY)")
    FIGS.mkdir(parents=True, exist_ok=True)
    todo = circuits(set(args.ids))
    old = {r["id"]: r for r in json.loads(OUT.read_text(encoding="utf-8"))["circuits"]} if OUT.exists() and args.ids else {}
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(lambda c: one(models, *c), todo))
    merged = {**old, **{r["id"]: r for r in rows}}
    rows = [merged[k] for k in sorted(merged)]
    totals = {"circuits": len(rows), "first_try": sum(r["first_try"] for r in rows),
              "repaired": sum(r["verdict"] == "repaired" for r in rows),
              "mismatch": sum(r["verdict"] == "mismatch" for r in rows), "unread": sum(r["verdict"] == "unread" for r in rows)}
    OUT.write_text(json.dumps({"date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "image_model": models.settings.image_model, "reader": [models.settings.reasoning_model,
                                                                                    models.settings.segment_model],
                               "max_repairs": figproof.MAX_REPAIRS, "totals": totals, "circuits": rows},
                              indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(totals)


if __name__ == "__main__":
    main()
