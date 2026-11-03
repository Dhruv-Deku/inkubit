"""Parse SAM 3.1 special-token output into boxes.

Grammar (docs/meta-api/sam_reading-segmentation.md):
    line   ::= "<" frame "f>" record ("," record)*
    record ::= object_id "<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..[;c=..]|>" "<|mask;...|>"
Fields are parsed by key, so the optional ``c`` (confidence) can be present or not.
Masks are base85 rasters; Inkubit only needs boxes, so mask payloads are skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FRAME = re.compile(r"<(\d+)f>")
_RECORD = re.compile(r"(\d+)<\|box;([^|]*)\|>")


@dataclass(frozen=True)
class SamBox:
    """One detection on one frame, in source pixels."""

    frame: int
    object_id: int
    x1: float
    y1: float
    x2: float
    y2: float
    width: int
    height: int
    confidence: float | None


def _fields(blob: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in blob.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def parse_sam_output(text: str) -> list[SamBox]:
    """All boxes in a SAM output lane (one or more frame lines). Empty text means no matches."""
    boxes: list[SamBox] = []
    # Mask payloads may contain almost any printable character, so split on frame markers
    # and read box tokens only; a box token's body never contains '|'.
    for match in _FRAME.finditer(text):
        frame = int(match.group(1))
        end = _FRAME.search(text, match.end())
        chunk = text[match.end(): end.start() if end else len(text)]
        for rec in _RECORD.finditer(chunk):
            f = _fields(rec.group(2))
            try:
                boxes.append(SamBox(
                    frame=frame, object_id=int(rec.group(1)),
                    x1=float(f["x1"]), y1=float(f["y1"]), x2=float(f["x2"]), y2=float(f["y2"]),
                    width=int(float(f["w"])), height=int(float(f["h"])),
                    confidence=float(f["c"]) if "c" in f else None,
                ))
            except (KeyError, ValueError):
                continue
    return boxes
