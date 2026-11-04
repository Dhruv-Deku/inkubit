"""Record the quantum internet globe full-frame (no panel around it) for the opening of the demo video.

Plans the sample network, sets the satellites to 600x, makes the globe fill the window and captures it turning.
Usage: record_globe.py OUT.mp4 [--seconds 16] [--base http://127.0.0.1:8000]
"""

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
from record_demo import SCALE, VIEW_H, VIEW_W, Recorder  # noqa: E402

FULL = """
html, body { overflow: hidden !important; }
.qe-globe { position: fixed !important; inset: 0 !important; width: 100vw !important; height: 100vh !important;
            max-width: none !important; z-index: 99999 !important; background: #0b0c0f !important; border-radius: 0 !important; }
"""


async def record(base: str, out: Path, seconds: float) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        ctx = await browser.new_context(viewport={"width": VIEW_W, "height": VIEW_H}, device_scale_factor=SCALE, color_scheme="dark")
        page = await ctx.new_page()
        await page.goto(f"{base}/#tab=hardware")
        earth = page.locator(".panel", has=page.locator("h2", has_text="Quantum internet")).first
        await earth.wait_for(timeout=120_000)
        await earth.scroll_into_view_if_needed()
        await earth.locator(".qe-list button").first.wait_for(timeout=120_000)
        await earth.locator(".qe-samples .linkish", has_text="Connect Delhi, Mumbai and London").click()
        await page.wait_for_function("() => [...document.querySelectorAll('.qe-steps li')].some(li => "
                                     "li.textContent.includes('Verdict') && li.className.includes('s-done'))", timeout=300_000)
        await earth.locator(".qe-time .seg button", has_text="600").click()
        await page.add_style_tag(content=FULL)
        await page.wait_for_timeout(2500)  # the canvas resizes and the routes settle
        with tempfile.TemporaryDirectory() as tmp:
            rec = Recorder(page, Path(tmp))
            await rec.start()
            await page.wait_for_timeout(seconds * 1000)
            await rec.stop()
            rec.encode(out)
        await browser.close()
    print(f"wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--seconds", type=float, default=16)
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    a = ap.parse_args()
    asyncio.run(record(a.base.rstrip("/"), a.out.resolve(), a.seconds))


if __name__ == "__main__":
    main()
