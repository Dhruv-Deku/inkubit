"""Model-facing draft schemas and their conversion into real specs.

Muse Spark fills a flat projection of ``schema.json`` (no tuples, no optional
nested objects, every field required) because flat schemas are the most
reliable for constrained decoding. :func:`draft_to_spec` then attaches image
boxes from the segments and the result is validated against the real schema.
"""

from __future__ import annotations

from typing import Any

from qcanvas.spec.models import GateName

_GATES = list(GateName.__args__)  # type: ignore[attr-defined]


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


_INTS = {"type": "array", "items": {"type": "integer", "minimum": 0}}
_BOX = {"type": "array", "items": {"type": "number"},
        "description": "Where it is drawn: [x1, y1, x2, y2] on a 0-1000 grid of the photo (0,0 top-left)."}
GRID = 1000.0

CIRCUIT_DRAFT_SCHEMA = _obj({
    "title": {"type": "string", "description": "Title written on the sketch, or a short name."},
    "num_qubits": {"type": "integer", "minimum": 1, "maximum": 12},
    "num_clbits": {"type": "integer", "minimum": 0, "maximum": 12},
    "operations": {"type": "array", "items": _obj({
        "gate": {"type": "string", "enum": _GATES},
        "targets": _INTS,
        "controls": _INTS,
        "params": {"type": "array", "items": {"type": "number"}, "description": "Angles in radians."},
        "segment_id": {"type": "string", "description": "Id of the numbered box this came from, or empty."},
        "box": _BOX,
    })},
    "measurements": {"type": "array", "items": _obj({
        "qubit": {"type": "integer", "minimum": 0},
        "clbit": {"type": "integer", "minimum": 0},
        "segment_id": {"type": "string"},
    })},
    "notes": {"type": "string", "description": "Anything unclear in the drawing, in one or two sentences."},
})

NETWORK_DRAFT_SCHEMA = _obj({
    "title": {"type": "string"},
    "nodes": {"type": "array", "items": _obj({
        "id": {"type": "string", "description": "Short lower-case id, e.g. station_a."},
        "type": {"type": "string", "enum": ["ground_station", "satellite", "repeater"]},
        "label": {"type": "string"},
        "segment_id": {"type": "string"},
        "box": _BOX,
    })},
    "links": {"type": "array", "items": _obj({
        "from": {"type": "string"},
        "to": {"type": "string"},
        "medium": {"type": "string", "enum": ["fiber", "free_space"]},
        "length_km": {"type": "number", "exclusiveMinimum": 0},
        "segment_id": {"type": "string"},
        "box": _BOX,
    })},
    "source": {"type": "string"},
    "destination": {"type": "string"},
    "notes": {"type": "string"},
})

REWRITE_SCHEMA = _obj({
    "idea": {"type": "string", "description": "One sentence: what you simplified and why the results stay the same."},
    "operations": {"type": "array", "items": _obj({
        "gate": {"type": "string", "enum": [g for g in _GATES if g not in ("MEASURE", "BARRIER")]},
        "targets": _INTS,
        "controls": _INTS,
        "params": {"type": "array", "items": {"type": "number"}, "description": "Angles in radians."},
    })},
})

CONCEPTS_SCHEMA = _obj({
    "kind": {"type": "string", "enum": ["circuit", "network"]},
    "concepts": {"type": "array", "items": {"type": "string"},
                 "description": "1 to 4 short noun phrases, one concrete drawn thing each."},
})


def draft_schema(kind: str) -> dict[str, Any]:
    """The draft schema for ``kind``."""
    return CIRCUIT_DRAFT_SCHEMA if kind == "circuit" else NETWORK_DRAFT_SCHEMA


GRID_CONFIDENCE = 0.6  # a box Muse Spark reported itself, used when no SAM segment matches


def _source(item: dict[str, Any], segments: dict[str, dict[str, Any]],
            size: tuple[int, int] | None) -> dict[str, Any] | None:
    seg = segments.get((item.get("segment_id") or "").strip())
    if seg:
        return {"bbox": list(seg["bbox"]), "confidence": float(seg.get("confidence", 1.0)), "segment_id": seg["id"]}
    box = item.get("box") or []
    if size and len(box) == 4 and all(isinstance(v, (int, float)) for v in box):
        w, h = size
        x1, y1, x2, y2 = (min(max(float(v), 0.0), GRID) for v in box)
        if x2 > x1 and y2 > y1:
            return {"bbox": [x1 * w / GRID, y1 * h / GRID, x2 * w / GRID, y2 * h / GRID],
                    "confidence": GRID_CONFIDENCE, "segment_id": None}
    return None


def draft_to_spec(kind: str, draft: dict[str, Any], segments: list[dict[str, Any]],
                  size: tuple[int, int] | None = None) -> dict[str, Any]:
    """Convert a filled draft into a spec dict with image sources attached.

    ``size`` (image width, height) lets 0-1000 grid boxes from the model stand in
    for missing segments.
    """
    by_id = {s["id"]: s for s in segments}
    meta = {"title": draft.get("title") or None, "notes": draft.get("notes") or None, "origin": "image"}
    if kind == "circuit":
        ops = []
        for op in draft.get("operations", []):
            item: dict[str, Any] = {k: op.get(k, []) for k in ("targets", "controls", "params")}
            item["gate"] = op.get("gate")
            src = _source(op, by_id, size)
            if src:
                item["source"] = src
            ops.append(item)
        return {
            "kind": "circuit", "version": "1.0",
            "num_qubits": draft.get("num_qubits"), "num_clbits": draft.get("num_clbits"),
            "operations": ops,
            "measurements": [{"qubit": m.get("qubit"), "clbit": m.get("clbit")} for m in draft.get("measurements", [])],
            "metadata": meta,
        }
    nodes = []
    for n in draft.get("nodes", []):
        item = {"id": n.get("id"), "type": n.get("type"), "label": n.get("label") or None}
        src = _source(n, by_id, size)
        if src:
            item["source"] = src
        if item["type"] == "repeater":
            item["memory_t2_ms"] = 10.0
        nodes.append(item)
    links = []
    for link in draft.get("links", []):
        item = {k: link.get(k) for k in ("from", "to", "medium", "length_km")}
        src = _source(link, by_id, size)
        if src:
            item["source"] = src
        links.append(item)
    return {"kind": "network", "version": "1.0", "nodes": nodes, "links": links,
            "source": draft.get("source"), "destination": draft.get("destination"), "metadata": meta}
