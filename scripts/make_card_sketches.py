"""Draw the "What it can do" cards' pen sketches: one notebook doodle per card, on paper, with the same unsteady pen
as the bundled sample sketches (scripts/make_sketches.py). Writes frontend/public/usecases/<card>.webp. Run from the
repo root:

    .venv/Scripts/python scripts/make_card_sketches.py
"""

from __future__ import annotations

import io
import math
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_sketches import INK, PAPER, Sketch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "public" / "usecases"
WIDTH, HEIGHT = 960, 480  # shown at about 450 x 225
W = 7


def curve(sk: Sketch, pts: list[tuple[float, float]], width: int = W) -> None:
    """A free-hand polyline through ``pts``."""
    for k in range(2):
        sk.d.line(sk._jitter_path(pts, 1.4), fill=INK, width=width - k, joint="curve")


def arrow(sk: Sketch, p0, p1, width: int = W, head: float = 22) -> None:
    sk.line(p0, p1, width)
    a = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    for s in (-1, 1):
        sk.line(p1, (p1[0] - head * math.cos(a + s * 0.5), p1[1] - head * math.sin(a + s * 0.5)), width)


def tick(sk: Sketch, x: float, y: float, s: float = 1.0, width: int = W + 1) -> None:
    sk.line((x, y), (x + 16 * s, y + 18 * s), width)
    sk.line((x + 16 * s, y + 18 * s), (x + 46 * s, y - 24 * s), width)


def cross(sk: Sketch, x: float, y: float, s: float = 1.0, width: int = W + 1) -> None:
    sk.line((x, y - 18 * s), (x + 34 * s, y + 18 * s), width)
    sk.line((x + 34 * s, y - 18 * s), (x, y + 18 * s), width)


def box(sk: Sketch, x: float, y: float, s: str = "", w: float = 72) -> None:
    """A gate box on a wire: paper inside (the wire stops at its edges), the letter drawn in."""
    sk.d.rectangle((x, y - w / 2, x + w, y + w / 2), fill=PAPER)
    sk.rect(x, y - w / 2, x + w, y + w / 2, W)
    if s:
        sk.text((x + w / 2 - 15, y - w / 2 + 4), s, int(w * 0.72))


def meter(sk: Sketch, x: float, y: float, h: float = 72) -> None:
    """The measurement box of the sample sketches: an arc and a needle."""
    w = h * 1.15
    sk.d.rectangle((x, y - h / 2, x + w, y + h / 2), fill=PAPER)
    sk.rect(x, y - h / 2, x + w, y + h / 2, W)
    r = h * 0.36
    curve(sk, [(x + w / 2 + r * math.cos(math.pi + math.pi * t / 14), y + h * 0.24 + r * math.sin(math.pi + math.pi * t / 14))
               for t in range(15)], W - 2)
    sk.line((x + w / 2, y + h * 0.24), (x + w / 2 + r * 0.95, y - h * 0.26), W - 2)


def sketch_card(sk: Sketch) -> None:
    """A circuit on paper, an arrow, and the code it becomes, ticked."""
    for y in (180, 300):
        sk.line((50, y), (330, y), W)
    box(sk, 95, 180, "H")
    sk.dot(230, 180, 11)
    sk.line((230, 180), (230, 326), W)
    sk.circle(230, 300, 26, W)
    meter(sk, 320, 180)
    meter(sk, 320, 300)
    arrow(sk, (460, 240), (545, 240))
    for i, s in enumerate(["qc.h(0)", "qc.cx(0, 1)", "qc.measure_all()"]):
        sk.text((585, 120 + 72 * i), s, 44)
    tick(sk, 740, 380, 1.15)


def hardware_card(sk: Sketch) -> None:
    """A heavy-hex patch of a chip, with three qubits picked out for the circuit."""
    rows, xs = (120, 250, 380), [110 + 68 * k for k in range(12)]
    for y in rows:
        sk.line((xs[0] - 30, y), (xs[-1] + 30, y), W - 2)
    for r, ks in ((0, (0, 4, 8)), (1, (2, 6, 10))):
        for k in ks:
            sk.line((xs[k], rows[r]), (xs[k], rows[r + 1]), W - 2)
            sk.circle(xs[k], (rows[r] + rows[r + 1]) / 2, 11, W - 3)
    for y in rows:
        for x in xs:
            sk.circle(x, y, 13, W - 3)
    for k in (5, 6, 7):
        sk.dot(xs[k], rows[1], 13)
    curve(sk, [(xs[6] + 140 * math.cos(t / 24 * 2.15 * math.pi), rows[1] + 48 * math.sin(t / 24 * 2.15 * math.pi))
               for t in range(25)], W - 1)
    sk.text((xs[0] - 20, 26), "ibm_fez", 42)
    sk.text((xs[7] - 10, 26), "3 qubits picked", 40)


def evidence_card(sk: Sketch) -> None:
    """Two columns of marks: the model alone gets one wrong; checked, nothing wrong gets through."""
    sk.text((150, 40), "AI alone", 46)
    sk.text((560, 40), "checked", 46)
    sk.line((470, 40), (470, 440), W - 2)
    sk.line((90, 112), (870, 112), W - 2)
    for i in range(4):
        y = 170 + 76 * i
        (cross if i == 2 else tick)(sk, 220, y, 0.95)
        tick(sk, 620, y, 0.95)
    sk.circle(238, 322, 44, W - 2)


def network_card(sk: Sketch) -> None:
    """A satellite over two ground stations, distances on the beams, one beam marked weak."""
    curve(sk, [(40 + 880 * t / 30, 470 - 120 * math.sin(math.pi * t / 30)) for t in range(31)], W)
    sk.rect(430, 50, 520, 110, W)
    for x0, x1 in ((290, 410), (540, 660)):
        sk.rect(x0, 62, x1, 98, W - 2)
        for k in range(1, 4):
            sk.line((x0 + (x1 - x0) * k / 4, 62), (x0 + (x1 - x0) * k / 4, 98), W - 4)
    sk.line((410, 80), (430, 80), W - 2)
    sk.line((520, 80), (540, 80), W - 2)
    for cx, cy in ((180, 382), (780, 382)):
        curve(sk, [(cx - 46 + 92 * t / 12, cy - 30 + 34 * math.sin(math.pi * t / 12)) for t in range(13)], W)
        sk.line((cx - 46, cy - 30), (cx + 46, cy - 30), W - 2)
        sk.line((cx, cy + 4), (cx, cy + 34), W)
    sk.line((470, 112), (190, 340), W - 1, dashed=True)
    sk.line((480, 112), (770, 340), W - 1, dashed=True)
    sk.text((185, 180), "1100 km", 40)
    sk.text((650, 180), "1600 km", 40)
    sk.text((700, 245), "weak", 38)


def shor_card(sk: Sketch) -> None:
    """Shor's arithmetic for 15: the powers of 7 repeat every 4, and two gcds give the factors."""
    sk.text((60, 40), "powers of 7, mod 15", 46)
    for i, v in enumerate((1, 7, 4, 13, 1, 7, 4, 13)):
        sk.text((86 + 112 * i - 14 * len(str(v)), 135), str(v), 52)
    curve(sk, [(66, 225), (70, 250), (250, 248), (270, 268), (290, 248), (470, 250), (474, 225)], W - 2)
    sk.text((200, 285), "period r = 4", 42)
    sk.text((60, 372), "gcd(7² ± 1, 15)  =  3, 5", 50)


def molecule_card(sk: Sketch) -> None:
    """H2: two atoms and the energy curve over their distance, lowest at the bond."""
    sk.circle(120, 150, 46, W)
    sk.circle(250, 150, 46, W)
    sk.line((166, 150), (204, 150), W)
    sk.text((104, 122), "H", 48)
    sk.text((234, 122), "H", 48)
    sk.line((400, 40), (400, 450), W - 1)
    sk.line((400, 450), (920, 450), W - 1)
    sk.text((350, 40), "E", 44)
    sk.text((780, 390), "distance", 38)

    def energy(r: float) -> float:  # a Morse-shaped well (lower energy is lower on the page)
        x = math.exp(-2.1 * (r - 0.9))
        return 150 - 230 * (x * x - 2 * x)

    pts = [(430 + 470 * (r - 0.62) / 3.3, energy(r)) for r in (0.62 + 3.3 * t / 40 for t in range(41))]
    curve(sk, [p for p in pts if p[1] > 30], W)
    xm = 430 + 470 * (0.9 - 0.62) / 3.3
    sk.dot(xm, energy(0.9), 12)
    sk.line((xm, energy(0.9) + 18), (xm, 445), W - 4, dashed=True)
    sk.text((xm + 26, 392), "bond length", 38)


def qkd_card(sk: Sketch) -> None:
    """BB84: A sends polarised photons to B; an eavesdropper on the line shows up as a 25% error rate."""
    for cx, s in ((90, "A"), (870, "B")):
        sk.circle(cx, 220, 48, W)
        sk.text((cx - 16, 190), s, 50)
    sk.line((140, 220), (820, 220), W - 2)
    for i, angle in enumerate((90, 0, 45, 90, 135, 0)):  # one photon per basis choice, its polarisation drawn above
        cx, cy, a = 215 + 106 * i, 130, math.radians(angle)
        sk.circle(cx, cy, 36, W - 3)
        dx, dy = 26 * math.cos(a), -26 * math.sin(a)
        arrow(sk, (cx - dx, cy - dy), (cx + dx, cy + dy), W - 3, 12)
        arrow(sk, (cx + dx, cy + dy), (cx - dx, cy - dy), W - 3, 12)
    sk.circle(480, 360, 40, W)
    sk.text((466, 332), "E", 46)
    sk.line((480, 318), (480, 230), W - 2)
    sk.text((560, 340), "errors 25%", 44)


def qaoa_card(sk: Sketch) -> None:
    """A graph split in two by a cut: filled nodes on one side, open ones on the other."""
    nodes = {0: (170, 90), 1: (270, 220), 2: (150, 350), 3: (320, 420), 4: (700, 80), 5: (620, 230), 6: (790, 300),
             7: (650, 410)}
    side = {0: 1, 1: 1, 2: 1, 3: 1, 4: 0, 5: 0, 6: 0, 7: 0}
    edges = [(0, 1), (6, 7), (0, 4), (0, 5), (1, 5), (1, 6), (2, 5), (2, 7), (3, 7), (3, 6), (1, 2)]
    for a, b in edges:
        (xa, ya), (xb, yb) = nodes[a], nodes[b]
        d = math.dist(nodes[a], nodes[b])
        ux, uy = (xb - xa) / d, (yb - ya) / d
        sk.line((xa + 26 * ux, ya + 26 * uy), (xb - 26 * ux, yb - 26 * uy), W - 2,
                dashed=False)
    for k, (x, y) in nodes.items():
        sk.circle(x, y, 24, W - 1)
        if side[k]:
            sk.dot(x, y, 15)
    pts = [(450 + 26 * math.sin(t / 18 * 3 * math.pi), 20 + 440 * t / 18) for t in range(19)]
    for i in range(0, 18, 2):
        curve(sk, pts[i:i + 2], W - 2)
    cut = sum(side[a] != side[b] for a, b in edges)
    sk.text((480, 20), f"cut {cut}", 44)


def bughunt_card(sk: Sketch) -> None:
    """A circuit with one gate circled: the planted bug."""
    ys = (110, 230, 350)
    for y in ys:
        sk.line((50, y), (900, y), W - 1)
    for x, q, s in ((110, 0, "H"), (110, 1, "H"), (420, 2, "X"), (700, 0, "T"), (700, 1, "H")):
        box(sk, x, ys[q], s)
    for x, c, t in ((270, 0, 1), (560, 1, 2)):
        sk.dot(x, ys[c], 11)
        sk.line((x, ys[c]), (x, ys[t] + 26), W)
        sk.circle(x, ys[t], 26, W)
    curve(sk, [(456 + 96 * math.cos(t / 24 * 2.1 * math.pi), 350 + 70 * math.sin(t / 24 * 2.1 * math.pi)) for t in range(25)], W - 1)
    sk.text((600, 400), "this one?", 42)


CARDS = {"sketch": (sketch_card, 21), "hardware": (hardware_card, 22), "evidence": (evidence_card, 23),
         "network": (network_card, 24), "shor": (shor_card, 25), "molecule": (molecule_card, 26),
         "qkd": (qkd_card, 27), "qaoa": (qaoa_card, 28), "bughunt": (bughunt_card, 29)}


def render(fn, seed: int) -> bytes:
    sk = Sketch(WIDTH, HEIGHT, seed)
    fn(sk)
    img = Image.open(io.BytesIO(sk.finish())).convert("RGB").resize((720, 360), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=86, method=6)
    return buf.getvalue()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    for name, (fn, seed) in CARDS.items():
        if only and name not in only:
            continue
        data = render(fn, seed)
        (OUT / f"{name}.webp").write_bytes(data)
        print(f"{name}.webp {len(data) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
