"""Live board: a camera frame in, the circuit read, simulated exactly, and its odds placed back on the drawing.

The browser watches the camera and sends a frame only when the drawing has changed and the picture has been still
for a moment, so each read is one pass of the sketch pipeline (Muse Spark chooses what to look for, SAM 3.1 segments
the parts, Muse Spark reads them into a validated spec). That pass takes seconds, not milliseconds, and the page says
so. The circuit is then simulated exactly (ideal and realistic noise) and each qubit's odds are pinned to its wire in
the photo: the wire's height is the median height of the boxes drawn on it, and the label sits right of its last box.
"""

from __future__ import annotations

import re
import statistics
from typing import Any

from qcanvas.sketch import SketchAnalysis

_OP = re.compile(r"operations\[(\d+)\]")


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def wires(analysis: SketchAnalysis) -> list[dict[str, Any]]:
    """For each qubit: where its wire is in the photo. Boxes of one-qubit gates place their wire directly; the boxes
    of a multi-qubit gate (a dot and a circle) are matched top to bottom to its qubits in index order, the way
    circuits are drawn."""
    spec = analysis.spec
    ops = spec.get("operations") or []
    by_op: dict[int, list[tuple[float, float, float, float]]] = {}
    for box in analysis.overlay:
        m = _OP.fullmatch(box.linked_to or "")
        if m and int(m.group(1)) < len(ops):
            boxes = by_op.setdefault(int(m.group(1)), [])
            if not any(_iou(box.bbox, b) > 0.7 for b in boxes):  # SAM can find one part under two concepts
                boxes.append(box.bbox)
    rows: dict[int, list[tuple[float, float]]] = {}
    for i, boxes in by_op.items():
        op = ops[i]
        pts = [((b[1] + b[3]) / 2, b[2]) for b in boxes]
        qubits = sorted(set((op.get("targets") or []) + (op.get("controls") or [])))
        if len(qubits) == 1:
            rows.setdefault(qubits[0], []).extend(pts)
        elif len(pts) == len(qubits):
            for q, pt in zip(qubits, sorted(pts)):
                rows.setdefault(q, []).append(pt)
        elif len(pts) == 1 and op.get("targets"):  # only the big target symbol was found
            rows.setdefault(op["targets"][0], []).append(pts[0])
    right = max((b.bbox[2] for b in analysis.overlay), default=0.0)
    out = []
    for q in range(int(spec.get("num_qubits") or 0)):
        pts = rows.get(q)
        if pts:
            out.append({"qubit": q, "y": statistics.median(p[0] for p in pts), "x_end": max(p[1] for p in pts),
                        "x_right": right})
    return out


def marginals(dist: dict[str, float], measured: list[tuple[int, int]]) -> dict[int, float]:
    """P(1) per measured qubit from outcome odds keyed by classical bits (Qiskit order: clbit 0 rightmost)."""
    out: dict[int, float] = {}
    for q, c in measured:
        out[q] = sum(p for k, p in dist.items() if len(k) > c and k[len(k) - 1 - c] == "1")
    return out


def read_frame(analysis: SketchAnalysis) -> dict[str, Any]:
    """Simulate what was read and pin the results to the drawing."""
    from qcanvas.insights.circuit import MAX_NOISY_QUBITS
    from qcanvas.spec import parse_spec
    from qcanvas.verify.expected import ideal_distribution, noisy_distribution

    out: dict[str, Any] = {"kind": analysis.spec.get("kind"), "wires": wires(analysis)}
    if not analysis.valid:
        out["error"] = "; ".join(analysis.issues)[:300] or "the drawing did not read as a valid design"
        return out
    spec = parse_spec(analysis.spec)
    if spec.kind == "circuit":
        ideal = ideal_distribution(spec)
        noisy = noisy_distribution(spec, "realistic") if spec.num_qubits <= MAX_NOISY_QUBITS else None
        pairs = spec.measured_pairs()
        out.update({
            "ideal": {k: round(v, 6) for k, v in sorted(ideal.items(), key=lambda kv: -kv[1])[:8]},
            "noisy": {k: round(noisy.get(k, 0.0), 6) for k in sorted(ideal, key=lambda k: -ideal[k])[:8]} if noisy else None,
            "p1_ideal": marginals(ideal, pairs), "p1_noisy": marginals(noisy, pairs) if noisy else None,
            "gates": len(spec.operations), "qubits": spec.num_qubits,
        })
    else:
        from qcanvas.network.model import simulate

        e = simulate(spec).end_to_end
        out["network"] = {"pairs_per_second": e.pair_rate_hz, "fidelity": e.fidelity, "key_bits_per_second": e.key_rate_bps}
    return out
