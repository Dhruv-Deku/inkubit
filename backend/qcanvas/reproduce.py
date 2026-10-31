"""Paper reproducibility checker: a figure (or its caption and code) in, the circuit rebuilt and re-run, each claim judged.

1. Read. From a figure, Muse Spark (one JSON-schema call with the image) transcribes the drawn circuit as OpenQASM 2
   and the claimed numbers (outcome odds from a histogram or table), the shot count, the hardware and the bit order
   the paper uses. The QASM goes through the Rosetta's exact parser, so the model transcribes and never simulates; if
   it cannot be parsed, the sketch pipeline (SAM 3.1 + Muse Spark) reads the drawing instead. From pasted text,
   OpenQASM is parsed exactly and claims like "P(00) = 0.48" or "11: 46%" are read by rules, with no model at all.
2. Re-run. Exact simulation, ideal and with the realistic preset.
3. Judge. Papers often write q0 on the left; when the order is not stated both are tried and the one that fits the
   ideal odds better is used, and the page says so. A claim is within reach when it is inside its error bar
   (3 sigma of shot noise when the shot count is known, else 0.03 for measured and 0.005 for ideal claims) of the
   ideal value, or, for hardware data, anywhere between our realistic-noise value and the ideal one (our noise model
   is not their chip). Verdict: reproduced (every claim), partly reproduced (at least half), or not reproduced.
"""

from __future__ import annotations

import math
import re
from typing import Any

from pydantic import BaseModel

CLAIMS_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["claims", "shots", "hardware", "bit_order", "circuit_qasm", "notes"],
    "properties": {
        "claims": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["outcome", "probability", "kind"],
            "properties": {
                "outcome": {"type": "string", "description": "The outcome bitstring exactly as printed."},
                "probability": {"type": "number", "description": "Claimed probability, 0 to 1 (convert percent)."},
                "kind": {"type": "string", "enum": ["measured", "ideal", "simulated"]}}}},
        "shots": {"type": "integer", "description": "Number of shots if stated, else 0."},
        "hardware": {"type": "string", "description": "Device or simulator named, else empty."},
        "bit_order": {"type": "string", "enum": ["q0_rightmost", "q0_leftmost", "unknown"],
                      "description": "Which end of the printed bitstrings is qubit 0, if the figure says."},
        "circuit_qasm": {"type": "string", "description": "The drawn circuit as OpenQASM 2.0 (include \"qelib1.inc\", "
                                                          "qreg q[n]; creg c[n]; gates; measure), or empty."},
        "notes": {"type": "string", "description": "Anything unclear, in one sentence; empty if nothing."}}}
CLAIMS_SYSTEM = (
    "You read figures from quantum computing papers. Transcribe exactly what is shown; do not compute or correct "
    "anything. Copy the circuit gate by gate as OpenQASM 2.0 with the qubit numbering of the figure, and copy every "
    "outcome probability shown in a histogram or table, reading bar heights as carefully as you can. Say which end "
    "of the bitstrings is qubit 0 only if the figure states it.")

_PROB = re.compile(r"(?:P\s*\(\s*\|?([01]+)[⟩>]?\s*\)|\|([01]+)[⟩>]|\b([01]{1,10})\b)\s*(?:=|:|→|->|≈)\s*"
                   r"(\d+(?:\.\d+)?)\s*(%)?")


class Claim(BaseModel):
    outcome: str
    probability: float
    kind: str = "measured"


class Judged(BaseModel):
    outcome: str  # as the paper writes it
    ours: str  # our key (Qiskit order, qubit 0 rightmost)
    claimed: float
    ideal: float
    noisy: float | None
    tolerance: float
    verdict: str  # within shot noise of ideal | between ideal and noisy | off by X
    ok: bool


class Reproduction(BaseModel):
    verdict: str
    headline: str
    read_from: str  # figure (Muse Spark QASM) | figure (sketch pipeline) | text
    bit_order: str
    bit_order_inferred: bool
    shots: int
    hardware: str
    spec: dict[str, Any]
    ideal: dict[str, float]
    noisy: dict[str, float] | None
    claims: list[Judged]
    tvd_to_ideal: float | None
    notes: str
    calls: list[dict[str, Any]]


def claims_from_text(text: str) -> list[Claim]:
    out: list[Claim] = []
    for m in _PROB.finditer(text):
        bits = m.group(1) or m.group(2) or m.group(3)
        v = float(m.group(4)) / (100 if m.group(5) else 1)
        if bits and 0 <= v <= 1 and not any(c.outcome == bits for c in out):
            out.append(Claim(outcome=bits, probability=v,
                             kind="ideal" if re.search(r"\bideal|theor", text, re.I) and not re.search(r"measur|hardware|device", text, re.I) else "measured"))
    return out


def shots_from_text(text: str) -> int:
    m = re.search(r"(\d[\d,]*)\s*shots", text, re.I)
    return int(m.group(1).replace(",", "")) if m else 0


_STMT = re.compile(r"^(OPENQASM\s+[\d.]+|include\s+\"[^\"]+\"|(qreg|creg)\s+\w+\[\d+\]|barrier\b.*|"
                   r"measure\s+\w+(\[\d+\])?\s*->\s*\w+(\[\d+\])?|reset\s+\w+(\[\d+\])?|"
                   r"[a-z][a-z0-9_]*\s*(\([^)]*\))?\s+\w+(\[\d+\])?(\s*,\s*\w+(\[\d+\])?)*)$")


def extract_qasm(text: str) -> str | None:
    """The OpenQASM statements in a pasted text, without the caption around them."""
    start = text.find("OPENQASM")
    if start < 0:
        m = re.search(r"\bqreg\s", text)
        if not m:
            return None
        start = m.start()
    kept = []
    for stmt in text[start:].split(";"):
        st = " ".join(stmt.split())
        if not st:
            continue
        if not _STMT.match(st):
            break
        kept.append(st)
    if not kept:
        return None
    if not kept[0].startswith("OPENQASM"):
        kept = ["OPENQASM 2.0", 'include "qelib1.inc"'] + kept
    return ";\n".join(kept) + ";"


def spec_from_qasm(qasm: str) -> dict[str, Any]:
    from qcanvas.rosetta import translate

    res = translate(extract_qasm(qasm) or qasm, None, with_languages=False)
    return res.spec


def judge(spec_raw: dict[str, Any], claims: list[Claim], shots: int, bit_order: str) -> tuple[list[Judged], str, bool, float | None]:
    from qcanvas.insights.circuit import MAX_NOISY_QUBITS
    from qcanvas.spec import parse_spec
    from qcanvas.verify.expected import ideal_distribution, noisy_distribution

    spec = parse_spec(spec_raw)
    ideal = ideal_distribution(spec)
    noisy = noisy_distribution(spec, "realistic") if spec.num_qubits <= MAX_NOISY_QUBITS else None
    width = len(next(iter(ideal)))

    def score(order: str) -> tuple[list[Judged], float]:
        rows, miss = [], 0.0
        for c in claims:
            bits = c.outcome.strip().replace(" ", "").zfill(width)[-width:]
            key = bits[::-1] if order == "q0_leftmost" else bits
            i, n = ideal.get(key, 0.0), (noisy.get(key, 0.0) if noisy else None)
            if shots > 0:
                tol = max(3 * math.sqrt(max(c.probability * (1 - c.probability), 1e-4) / shots), 0.01)
            else:
                tol = 0.005 if c.kind != "measured" else 0.03
            if abs(c.probability - i) <= tol:
                verdict, ok = "within error of the ideal value", True
            elif c.kind == "measured" and n is not None and min(i, n) - tol <= c.probability <= max(i, n) + tol:
                verdict, ok = "between the ideal and the realistic-noise value", True
            else:
                verdict, ok = f"off by {abs(c.probability - i):.3f} from the ideal value", False
            miss += abs(c.probability - i)
            rows.append(Judged(outcome=c.outcome, ours=key, claimed=round(c.probability, 6), ideal=round(i, 6),
                               noisy=round(n, 6) if n is not None else None, tolerance=round(tol, 4), verdict=verdict, ok=ok))
        return rows, miss

    inferred = False
    if bit_order == "unknown":
        a, b = score("q0_rightmost"), score("q0_leftmost")
        bit_order, (rows, _) = ("q0_rightmost", a) if a[1] <= b[1] else ("q0_leftmost", b)
        inferred = a[1] != b[1]
    else:
        rows, _ = score(bit_order)
    claimed = {r.ours: r.claimed for r in rows}
    total = sum(claimed.values())
    tvd = None
    if claims and total > 0.5:
        keys = set(ideal) | set(claimed)
        tvd = round(0.5 * sum(abs(claimed.get(k, 0.0) - ideal.get(k, 0.0)) for k in keys), 4)
    return rows, bit_order, inferred, tvd


def reproduce(image: bytes | None, text: str, models: Any = None) -> Reproduction:
    from qcanvas.verify.expected import ideal_distribution, noisy_distribution
    from qcanvas.spec import parse_spec

    calls: list[dict[str, Any]] = []
    claims: list[Claim] = claims_from_text(text) if text else []
    shots, hardware, bit_order, notes = shots_from_text(text) if text else 0, "", "unknown", ""
    spec_raw: dict[str, Any] | None = None
    read_from = "text"
    if re.search(r"OPENQASM|qreg\s", text or "", re.I):
        spec_raw = spec_from_qasm(text)
    if image is not None:
        if models is None:
            raise ValueError("reading a figure needs the live model; paste the caption and OpenQASM instead")
        from qcanvas.adapters.imaging import normalise_upload

        img, mime, _, _ = normalise_upload(image)
        data, call = models.reasoning.structured(CLAIMS_SYSTEM, f"Caption or notes from the user: {text[:1500]}" if text
                                                 else "Read this figure.", CLAIMS_SCHEMA, "paper_figure", effort="medium",
                                                 max_tokens=12000, image=img, mime=mime)
        calls.append(call.model_dump(mode="json"))
        if not claims:
            claims = [Claim(outcome=str(c["outcome"]), probability=float(c["probability"]), kind=str(c.get("kind", "measured")))
                      for c in data.get("claims") or [] if isinstance(c, dict) and 0 <= float(c.get("probability", -1)) <= 1]
        shots = shots or int(data.get("shots") or 0)
        hardware = str(data.get("hardware") or "")
        bit_order = str(data.get("bit_order") or "unknown")
        notes = str(data.get("notes") or "")
        if spec_raw is None and data.get("circuit_qasm"):
            try:
                spec_raw = spec_from_qasm(str(data["circuit_qasm"]))
                read_from = "figure (Muse Spark transcribed it as OpenQASM; read by the exact parser)"
            except Exception as err:  # noqa: BLE001 - the sketch pipeline gets a go
                notes = (notes + f" The transcribed OpenQASM did not parse ({str(err)[:80]}).").strip()
        if spec_raw is None:
            from qcanvas.sketch import analyze_image

            analysis, _ = analyze_image(image, models)
            calls += [c.model_dump(mode="json") for c in analysis.calls]
            if analysis.valid and analysis.spec.get("kind") == "circuit":
                spec_raw = analysis.spec
                read_from = "figure (sketch pipeline: SAM 3.1 + Muse Spark)"
    if spec_raw is None:
        raise ValueError("no circuit found: give a figure with a circuit, or paste its OpenQASM")
    spec = parse_spec(spec_raw)
    rows, order, inferred, tvd = judge(spec_raw, claims, shots, bit_order)
    ok = sum(r.ok for r in rows)
    if not rows:
        verdict = "nothing to compare"
        headline = "The circuit was rebuilt and run, but no claimed numbers were found to check."
    else:
        verdict = "reproduced" if ok == len(rows) else "partly reproduced" if ok * 2 >= len(rows) else "not reproduced"
        headline = (f"{ok} of {len(rows)} claimed numbers are within reach of an exact re-run"
                    + (f" (shot noise for {shots:,} shots)" if shots else "") + ". "
                    + ("Every claim checks out." if verdict == "reproduced" else
                       "The rest differ by more than their error bars." if rows else ""))
    ideal = ideal_distribution(spec)
    noisy = noisy_distribution(spec, "realistic") if spec.num_qubits <= 10 else None
    top = sorted(ideal, key=lambda k: -ideal[k])[:16]
    shown = spec.model_dump(mode="json", by_alias=True, exclude_none=True)
    pairs = spec.measured_pairs()  # measurements as the spec's measurement list, not MEASURE gates
    shown["operations"] = [o for o in shown["operations"] if o["gate"] != "MEASURE"]
    shown["measurements"] = [{"qubit": q, "clbit": c} for q, c in pairs]
    return Reproduction(verdict=verdict, headline=headline, read_from=read_from, bit_order=order,
                        bit_order_inferred=inferred, shots=shots, hardware=hardware, spec=shown,
                        ideal={k: round(ideal[k], 6) for k in top},
                        noisy={k: round(noisy.get(k, 0.0), 6) for k in top} if noisy else None,
                        claims=rows, tvd_to_ideal=tvd, notes=notes, calls=calls)
