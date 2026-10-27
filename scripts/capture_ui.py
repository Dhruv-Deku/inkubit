"""Drive the UI headlessly (system Edge via Playwright) and save screenshots.

    .venv/Scripts/python scripts/capture_ui.py [base_url]

Needs the backend running with the built frontend (scripts/dev.sh or uvicorn).
Writes docs/screenshots/*.png.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1480, "height": 940}, device_scale_factor=1)
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(BASE)
        page.wait_for_selector(".sample img")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "1-start.png"))

        # circuit: sample sketch -> overlay -> demo run
        page.click(".sample >> nth=0")
        page.wait_for_selector(".overlay-wrap svg rect")
        page.hover(".ops tbody tr >> nth=1")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "2-overlay.png"))
        page.click("label.toggle")
        page.click("button.btn.primary.big")
        page.wait_for_selector(".ev.diagnose, .ev.fail", timeout=60000)
        page.wait_for_timeout(2500)
        page.screenshot(path=str(OUT / "3-live-log.png"))
        page.wait_for_selector(".verdict-badge", timeout=120000)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "4-results.png"))
        page.screenshot(path=str(OUT / "4-results-full.png"), full_page=True)

        # network: preset A from the spec list
        page.click("nav.steps button >> nth=0")
        page.click("text=Preset A: satellite link")
        page.wait_for_selector(".ops")
        page.click("button.btn.primary.big")
        page.wait_for_selector(".verdict-badge", timeout=120000)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "5-network.png"), full_page=True)
        browser.close()
        if errors:
            print("console errors:", *errors, sep="\n  ")
    for f in sorted(OUT.glob("*.png")):
        print(f.relative_to(ROOT))


if __name__ == "__main__":
    main()
