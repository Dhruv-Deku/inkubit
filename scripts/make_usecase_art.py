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

STYLE = ("Photorealistic studio photograph, soft physically based lighting, matte dark charcoal background, muted "
         "neutral colours with one restrained blue accent, shallow depth of field, calm minimal composition with the "
         "subject slightly off-centre. No text, no letters, no numbers, no logos, no glow, no neon, no sparkles, no "
         "particles, no holograms.")
ART = {
    "teacher": "A phone held in one hand photographing a pencil sketch of a quantum circuit (boxes on horizontal lines, "
               "dots joined by vertical lines) on a white classroom whiteboard.",
    "student": "An open paper notebook with a neat pencil diagram of horizontal lines with small boxes, and a red pencil "
               "circling one of the boxes.",
    "chemist": "A classic ball-and-stick model of a hydrogen molecule: two white spheres joined by a short grey rod, "
               "resting on a dark desk.",
    "security": "A single optical fibre cable with a small metal connector lying next to a closed steel padlock.",
    "logistics": "Top-down view of two small round dinner tables with white place cards and chairs, guests' seats set "
                 "apart.",
    "network": "A white satellite ground-station dish antenna on a rooftop at dusk, pointing at the sky.",
    "cryptography": "An antique brass padlock lying open with its key beside it on dark slate.",
    "researcher": "Close-up of the gold-plated copper stages of a superconducting quantum computer's dilution "
                  "refrigerator, with fine coaxial cables.",
    "skeptic": "A magnifying glass resting on a printed bar chart on a dark desk.",
}


def main() -> None:
    out = ROOT / "frontend" / "public" / "usecases"
    out.mkdir(parents=True, exist_ok=True)
    client = MetaClient(load_settings())
    for key in sys.argv[1:] or list(ART):
        data, cached = client.post("/images/generations", {
            "model": "muse-image-1.0", "prompt": f"{ART[key]} {STYLE}", "size": "1792x1024",
            "response_format": "b64_json", "output_format": "png"})
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
