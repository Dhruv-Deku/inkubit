"""Draw the section tabs' pen sketches: one small doodle per section, on paper, with the same unsteady pen as the
bundled sample sketches (scripts/make_sketches.py). Writes frontend/public/tabs/<section>.webp. Run from the repo root:

    .venv/Scripts/python scripts/make_tab_sketches.py
"""

from __future__ import annotations

import io
import math
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_sketches import INK, Sketch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "public" / "tabs"
S = 320  # drawn size; shown at 64 px, so strokes are bold
W = 15


def circuit(sk: Sketch) -> None:
    """Sketch to code: two wires, an H box, a CNOT and a meter."""
    for y in (105, 225):
        sk.line((30, y), (290, y), W)
    sk.rect(55, 60, 140, 150, W)
    sk.line((80, 80), (80, 130), W - 3)  # the H
    sk.line((115, 80), (115, 130), W - 3)
    sk.line((80, 105), (115, 105), W - 3)
    sk.dot(185, 105, 16)
    sk.line((185, 105), (185, 252), W)
    sk.circle(185, 225, 28, W)
    sk.rect(225, 188, 292, 262, W)
    sk.line((240, 245), (258, 214), W - 5)  # meter needle
    sk.line((258, 214), (276, 245), W - 5)


def chip(sk: Sketch) -> None:
    """Hardware: a chip with pins and three linked qubits."""
    sk.rect(85, 85, 235, 235, W)
    for t in (115, 160, 205):
        sk.line((t, 85), (t, 50), W - 3)
        sk.line((t, 235), (t, 270), W - 3)
        sk.line((85, t), (50, t), W - 3)
        sk.line((235, t), (270, t), W - 3)
    pts = [(125, 135), (195, 135), (160, 195)]
    for a, b in ((0, 1), (1, 2), (2, 0)):
        sk.line(pts[a], pts[b], W - 5)
    for x, y in pts:
        sk.circle(x, y, 15, W - 4)


def proof(sk: Sketch) -> None:
    """Proof: two tall bars where the answer should be, two short ones, and a tick above."""
    sk.line((35, 272), (285, 272), W)
    for x, h in ((50, 118), (110, 22), (170, 26), (230, 112)):
        sk.rect(x, 272 - h, x + 40, 272, W - 3)
    sk.line((105, 82), (140, 118), W + 4)
    sk.line((140, 118), (215, 30), W + 4)


def discover(sk: Sketch) -> None:
    """Discover: a magnifier over a small circuit."""
    for y in (95, 165, 235):
        sk.line((30, y), (200, y), W - 4)
    sk.dot(90, 95, 11)
    sk.line((90, 95), (90, 165), W - 5)
    sk.circle(90, 165, 17, W - 5)
    sk.circle(165, 150, 72, W + 2)
    sk.line((217, 202), (285, 272), W + 8)


def flask(sk: Sketch) -> None:
    """Labs: a flask, half full, with two bubbles."""
    sk.line((128, 45), (192, 45), W)
    sk.line((138, 45), (138, 130), W)
    sk.line((182, 45), (182, 130), W)
    sk.line((138, 130), (62, 268), W)
    sk.line((182, 130), (258, 268), W)
    sk.line((58, 270), (262, 270), W)
    sk.line((96, 205), (224, 205), W - 6, dashed=True)
    sk.circle(140, 238, 12, W - 7)
    sk.circle(182, 225, 8, W - 7)


DOODLES = {"build": (circuit, 11), "hardware": (chip, 12), "evidence": (proof, 13), "discover": (discover, 14), "labs": (flask, 15)}


def render(fn, seed: int) -> bytes:
    sk = Sketch(S, S, seed)
    fn(sk)
    png = sk.finish()
    img = Image.open(io.BytesIO(png)).convert("RGB").resize((160, 160), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=88, method=6)
    return buf.getvalue()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (fn, seed) in DOODLES.items():
        data = render(fn, seed)
        (OUT / f"{name}.webp").write_bytes(data)
        print(f"{name}.webp {len(data) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
