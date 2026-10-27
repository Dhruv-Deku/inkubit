"""Draw the bundled sample "sketch photos" and their ground-truth fixtures.

Writes examples/images/<name>.png and <name>.json. The JSON holds the image's
SHA-256, the true bounding box of every drawn element (used as the offline
stand-in for SAM 3.1 segments) and the spec the drawing represents (the offline
stand-in for Muse Spark's reading). Run from the repo root:

    .venv/Scripts/python scripts/make_sketches.py
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "examples" / "images"
INK = (38, 50, 84)
PAPER = (246, 243, 236)
FONT_CANDIDATES = ["C:/Windows/Fonts/Inkfree.ttf", "C:/Windows/Fonts/segoepr.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def font(size: int) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


class Sketch:
    """A sheet of paper plus a pen with a slightly unsteady hand."""

    def __init__(self, w: int, h: int, seed: int):
        self.w, self.h = w, h
        self.rng = random.Random(seed)
        self.img = Image.new("RGB", (w, h), PAPER)
        self.d = ImageDraw.Draw(self.img)
        self.segments: list[dict] = []

    def _jitter_path(self, pts: list[tuple[float, float]], amp: float) -> list[tuple[float, float]]:
        phase, freq = self.rng.random() * 6.28, 0.6 + self.rng.random() * 0.8
        out = []
        for i, (x, y) in enumerate(pts):
            out.append((x + amp * math.sin(phase + i * freq) + self.rng.gauss(0, amp * 0.25),
                        y + amp * math.cos(phase * 0.7 + i * freq) + self.rng.gauss(0, amp * 0.25)))
        return out

    def line(self, p0, p1, width: int = 4, amp: float = 1.6, dashed: bool = False) -> None:
        length = math.dist(p0, p1)
        n = max(2, int(length / 14))
        pts = [(p0[0] + (p1[0] - p0[0]) * t / n, p0[1] + (p1[1] - p0[1]) * t / n) for t in range(n + 1)]
        for k in range(2):  # two passes read as pencil pressure
            path = self._jitter_path(pts, amp)
            if dashed:
                for i in range(0, len(path) - 1, 3):
                    self.d.line(path[i:i + 2], fill=INK, width=width - k, joint="curve")
            else:
                self.d.line(path, fill=INK, width=width - k, joint="curve")

    def rect(self, x1, y1, x2, y2, width: int = 4) -> None:
        o = 5  # corners overshoot a little, like a quick hand
        self.line((x1 - o, y1), (x2 + o, y1 + 1), width)
        self.line((x2, y1 - o), (x2 + 1, y2 + o), width)
        self.line((x2 + o, y2), (x1 - o, y2 - 1), width)
        self.line((x1, y2 + o), (x1 - 1, y1 - o), width)

    def circle(self, cx, cy, r, width: int = 4) -> None:
        n = 40
        pts = [(cx + r * math.cos(2 * math.pi * t / n * 1.06), cy + r * math.sin(2 * math.pi * t / n * 1.06))
               for t in range(n + 1)]
        self.d.line(self._jitter_path(pts, 1.4), fill=INK, width=width, joint="curve")

    def dot(self, cx, cy, r) -> None:
        self.d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=INK)

    def text(self, xy, s: str, size: int = 46) -> tuple[float, float, float, float]:
        f = font(size)
        self.d.text(xy, s, fill=INK, font=f)
        return self.d.textbbox(xy, s, font=f)

    def seg(self, concept: str, bbox, conf: float) -> str:
        sid = f"s{len(self.segments)}"
        self.segments.append({"id": sid, "concept": concept,
                              "bbox": [round(v, 1) for v in bbox], "confidence": conf})
        return sid

    def finish(self) -> bytes:
        """Paper grain and soft phone-camera lighting, then PNG bytes."""
        grain = Image.effect_noise((self.w, self.h), 10).convert("RGB")
        img = Image.blend(self.img, grain, 0.05)
        shade = Image.radial_gradient("L").resize((self.w, self.h)).filter(ImageFilter.GaussianBlur(40))
        dark = Image.new("RGB", (self.w, self.h), (205, 200, 190))
        img = Image.composite(dark, img, shade.point(lambda v: int(v * 0.35)))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


def _src(sk: Sketch, sid: str) -> dict:
    s = next(x for x in sk.segments if x["id"] == sid)
    return {"bbox": s["bbox"], "confidence": s["confidence"], "segment_id": sid}


def _union(*boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def draw_circuit(name: str, title: str, wires: list[float], gates: list[tuple], seed: int) -> dict:
    """Draw wires, H boxes, CNOTs and meters. ``gates``: ('H', q, x) or ('CX', c, t, x)."""
    sk = Sketch(1400, 220 + 170 * len(wires), seed)
    sk.text((120, 50), title, 54)
    x0, x_meter = 200, 1010
    ops, meas = [], []
    stops: dict[int, list[tuple[float, float]]] = {q: [] for q in range(len(wires))}
    for g in gates:
        if g[0] == "H":
            _, q, x = g
            stops[q].append((x - 50, x + 50))
        elif g[0] == "CX":
            _, c, t, x = g
            stops[t].append((x - 38, x + 38))
    for q, y in enumerate(wires):
        sk.text((90, y - 30), f"q{q}", 44)
        cuts = sorted(stops[q]) + [(x_meter, x_meter + 110)]
        start = x0
        for a, b in cuts:
            sk.line((start, y), (a, y + sk.rng.uniform(-2, 2)))
            start = b
    for g in gates:
        if g[0] == "H":
            _, q, x = g
            y = wires[q]
            box = (x - 50, y - 50, x + 50, y + 50)
            sk.rect(*box)
            sk.text((x - 17, y - 34), "H", 54)
            sid = sk.seg("gate box", box, round(0.93 + sk.rng.random() * 0.05, 3))
            ops.append({"gate": "H", "targets": [q], "source": _src(sk, sid)})
        else:
            _, c, t, x = g
            yc, yt = wires[c], wires[t]
            sk.dot(x, yc, 13)
            sk.circle(x, yt, 38)
            sk.line((x, yc), (x, yt + (38 if yt > yc else -38)))
            sk.line((x - 38, yt), (x + 38, yt), 3)
            dot_id = sk.seg("dot", (x - 15, yc - 15, x + 15, yc + 15), round(0.9 + sk.rng.random() * 0.06, 3))
            tgt_id = sk.seg("circle", (x - 41, yt - 41, x + 41, yt + 41), round(0.9 + sk.rng.random() * 0.06, 3))
            box = _union(sk.segments[-2]["bbox"], sk.segments[-1]["bbox"])
            ops.append({"gate": "CX", "controls": [c], "targets": [t],
                        "source": {"bbox": [round(v, 1) for v in box],
                                   "confidence": min(sk.segments[-1]["confidence"], sk.segments[-2]["confidence"]),
                                   "segment_id": tgt_id}})
            _ = dot_id
    for q, y in enumerate(wires):
        box = (x_meter, y - 46, x_meter + 110, y + 46)
        sk.rect(*box)
        arc = [(x_meter + 55 + 36 * math.cos(math.pi + math.pi * t / 16), y + 22 + 36 * math.sin(math.pi + math.pi * t / 16))
               for t in range(17)]
        sk.d.line(sk._jitter_path(arc, 1.0), fill=INK, width=3, joint="curve")
        sk.line((x_meter + 55, y + 22), (x_meter + 84, y - 22), 3)
        sid = sk.seg("meter", box, round(0.88 + sk.rng.random() * 0.08, 3))
        meas.append({"qubit": q, "clbit": q, "segment_id": sid})
    png = sk.finish()
    n = len(wires)
    spec = {"kind": "circuit", "version": "1.0", "num_qubits": n, "num_clbits": n, "operations": ops,
            "measurements": [{"qubit": m["qubit"], "clbit": m["clbit"]} for m in meas],
            "metadata": {"title": title, "notes": "Read from the bundled sample sketch.", "origin": "image"}}
    return _save(name, png, sk, spec, "circuit", ["gate box", "dot", "circle", "meter"])


def draw_network(name: str, seed: int) -> dict:
    sk = Sketch(1400, 900, seed)
    sk.text((90, 40), "Satellite entanglement link", 52)
    # satellite
    sx, sy = 700, 220
    sk.rect(sx - 55, sy - 38, sx + 55, sy + 38)
    for side in (-1, 1):
        px1, px2 = (sx - 230, sx - 85) if side < 0 else (sx + 85, sx + 230)
        sk.rect(px1, sy - 30, px2, sy + 30, 3)
        for k in range(1, 4):
            xx = px1 + (px2 - px1) * k / 4
            sk.line((xx, sy - 30), (xx, sy + 30), 2, 0.8)
        sk.line((px2 if side < 0 else px1, sy), (sx - 55 if side < 0 else sx + 55, sy), 3)
    sk.text((sx - 32, sy - 100), "SAT", 40)
    sat = sk.seg("satellite", (sx - 235, sy - 45, sx + 235, sy + 45), 0.962)
    # ground stations (dishes)
    dishes = {}
    for key, cx, label in (("delingha", 230, "Station A"), ("lijiang", 1170, "Station B")):
        cy = 690
        bowl = [(cx + 70 * math.cos(math.pi * (0.1 + 0.8 * t / 20)) * 1.0,
                 cy - 40 + 45 * math.sin(math.pi * (0.1 + 0.8 * t / 20))) for t in range(21)]
        sk.d.line(sk._jitter_path(bowl, 1.2), fill=INK, width=4, joint="curve")
        sk.line(bowl[0], bowl[-1], 3)
        sk.line((cx, cy + 5), (cx, cy + 70))
        sk.line((cx - 50, cy + 72), (cx + 50, cy + 72))
        sk.text((cx - 85, cy + 90), label, 40)
        dishes[key] = sk.seg("antenna dish", (cx - 75, cy - 45, cx + 75, cy + 75), round(0.9 + sk.rng.random() * 0.07, 3))
    # links
    links = []
    for key, cx, dist, tx in (("delingha", 230, "1100 km", 235), ("lijiang", 1170, "1600 km", 1015)):
        p0, p1 = (cx, 640), (sx + (-120 if cx < sx else 120), sy + 50)
        sk.line(p0, p1, 3, 1.2, dashed=True)
        sk.text((tx, 400), dist, 42)
        lid = sk.seg("dashed line", _union((min(p0[0], p1[0]), p1[1], max(p0[0], p1[0]), p0[1])), 0.81)
        links.append((key, lid))
    # ground distance
    sk.line((300, 845), (1100, 845), 3)
    sk.text((560, 790), "~1200 km apart", 40)
    png = sk.finish()
    spec = json.loads((ROOT / "examples" / "specs" / "network_satellite.json").read_text(encoding="utf-8"))
    for node in spec["nodes"]:
        sid = sat if node["id"] == "sat" else dishes[node["id"]]
        node["source"] = _src(sk, sid)
    for link, (_, lid) in zip(spec["links"], links):
        link["source"] = _src(sk, lid)
    spec["metadata"] = {"title": "Satellite entanglement link", "notes": "Read from the bundled sample sketch.",
                        "origin": "image"}
    return _save(name, png, sk, spec, "network", ["satellite", "antenna dish", "dashed line"])


def _save(name: str, png: bytes, sk: Sketch, spec: dict, kind: str, concepts: list[str]) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.png").write_bytes(png)
    fixture = {"name": name, "sha256": hashlib.sha256(png).hexdigest(), "width": sk.w, "height": sk.h,
               "kind": kind, "concepts": concepts, "segments": sk.segments, "spec": spec}
    (OUT / f"{name}.json").write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    return fixture


def main() -> None:
    draw_circuit("bell_sketch", "Bell pair", [300, 470], [("H", 0, 360), ("CX", 0, 1, 640)], seed=7)
    draw_circuit("ghz_sketch", "GHZ state", [270, 430, 590], [("H", 0, 340), ("CX", 0, 1, 580), ("CX", 1, 2, 800)],
                 seed=11)
    draw_network("satellite_sketch", seed=5)
    for p in sorted(OUT.glob("*.png")):
        print(p.relative_to(ROOT), p.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
