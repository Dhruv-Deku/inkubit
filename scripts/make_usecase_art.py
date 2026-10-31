"""Generate the use-case card images with Muse Image 1.0 (live model; cached, so a re-run costs nothing).

Writes frontend/public/usecases/<id>.webp at 720x405. About $0.01 per image (docs/meta-api/pricing-rate-limits.md).

    .venv/Scripts/python scripts/make_usecase_art.py [id ...]
"""

from __future__ import annotations

import base64
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("QCANVAS_MODEL_PROVIDER", "meta")

from PIL import Image  # noqa: E402

from qcanvas.adapters.config import load_settings  # noqa: E402
from qcanvas.adapters.meta_client import MetaClient  # noqa: E402

# Same look as the pipeline's Muse Image diagrams (adapters/meta_vision.diagram_prompt), without labels.
STYLE = ("Flat, precise technical illustration on a dark charcoal background (#16171b), crisp off-white line work, "
         "a single warm gold accent (#d9a441) for the one element that matters, generous negative space, the subject "
         "slightly off-centre, wide 16:9 composition. No text, no letters, no numbers, no labels, no logos, no glow, "
         "no gradients, no neon, no sparkles, no particles, no people.")
ART = {
    "sketch": "On the left, a loose pencil sketch of a two-wire quantum circuit on a sheet of paper; on the right, the "
              "same circuit redrawn as a clean diagram: two horizontal wires, a square gate box, a CNOT drawn as a "
              "gold dot joined by a vertical line to a gold circled plus, and two meter boxes.",
    "bughunt": "A five-wire quantum circuit diagram with many square gate boxes and CNOT connectors; one single gate "
               "box is outlined in gold and sits inside the lens of a simple outlined magnifying glass.",
    "molecule": "A hydrogen molecule: two small off-white atom circles with concentric electron-density contour lines "
                "merging between them into a gold bonding region, and beneath them a smooth potential-energy curve "
                "with one gold dot at its minimum.",
    "qkd": "Two outlined ground-station telescopes far apart, joined by a straight row of small photon dots each with "
           "a short polarization arrow at 0, 45 or 90 degrees; an outlined eavesdropper box taps the middle of the "
           "line and the photons after it turn gold.",
    "qaoa": "A network graph of ten round nodes and many straight edges; the nodes are split into two groups, "
            "off-white and outlined, and every edge that crosses between the two groups is drawn in gold.",
    "network": "A low-earth-orbit satellite with solar panels above the curve of the Earth drawn as a thin arc, two "
               "outlined ground stations with dish antennas far apart on the arc, and two straight gold beams from the "
               "satellite down to each station.",
    "shor": "A row of identical tall interference peaks rising from a flat baseline at perfectly even spacing, like a "
            "frequency spectrum; one peak is gold, and a faint off-white sine wave with the same period runs behind "
            "them.",
    "hardware": "Top-down view of a superconducting quantum processor chip: a square die with a heavy-hexagon lattice "
                "of small cross-shaped qubits joined by short couplers, thin wiring fanning out to bond pads at the "
                "edges; one coupler between two qubits is gold.",
    "evidence": "Two simple bar charts side by side with the same four bars; on the left the bars are uneven outlines, "
                "on the right they are solid off-white and one thin gold line sits exactly on top of each bar.",
}


def main() -> None:
    out = ROOT / "frontend" / "public" / "usecases"
    out.mkdir(parents=True, exist_ok=True)
    client = MetaClient(load_settings())
    for key in sys.argv[1:] or list(ART):
        data, cached = client.post("/images/generations", {
            "model": "muse-image-1.0", "prompt": f"{ART[key]} {STYLE}", "size": "1536x1024",
            "response_format": "b64_json", "output_format": "png", "reasoning_strength": "high"})
        img = Image.open(io.BytesIO(base64.b64decode(data["data"][0]["b64_json"]))).convert("RGB")
        w, h = img.size
        target = 16 / 9
        if w / h > target:
            nw = int(h * target)
            img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = int(w / target)
            img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
        img.resize((720, 405), Image.LANCZOS).save(out / f"{key}.webp", quality=82)
        print(key, "cached" if cached else "generated", img.size)


if __name__ == "__main__":
    main()
