"""Drive the UI headlessly (system Edge via Playwright) and save screenshots.

    .venv/Scripts/python scripts/capture_ui.py [base_url]

Needs the backend running with the built frontend (scripts/dev.sh or uvicorn).
Writes docs/screenshots/*.png.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def _gif(frames: list[bytes], path: Path, width: int = 1000) -> None:
    """Assemble PNG screenshots into a compact looping GIF."""
    import io

    from PIL import Image

    images = []
    for raw in frames:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
        images.append(img.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
    durations = [350] * (len(images) - 1) + [2600]
    images[0].save(path, save_all=True, append_images=images[1:], duration=durations, loop=0, optimize=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1480, "height": 940}, device_scale_factor=1)
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(BASE)
        # full-page captures see past the viewport, where the scroll-in fade would leave panels dim
        page.add_style_tag(content=".panel { animation: none !important; }")
        tab = lambda label: page.get_by_role("tab", name=re.compile("^" + re.escape(label))).click()  # noqa: E731
        page.wait_for_selector(".sample img")
        page.wait_for_timeout(600)
        page.wait_for_timeout(10500)  # the opening scene reaches its verified state
        page.screenshot(path=str(OUT / "1-start.png"))
        tab("Hardware")
        lab = page.locator(".panel", has=page.locator("h2", has_text="Error-correction lab"))
        page.wait_for_selector(".panel:has(h2:has-text('Error-correction lab')) svg path")
        lab.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        lab.screenshot(path=str(OUT / "19-qec-lab.png"))
        page.evaluate("window.scrollTo(0, 0)")
        tab("Sketch to code")

        # circuit: sample sketch -> overlay -> demo run
        page.click(".sample >> nth=0")
        page.wait_for_selector(".overlay-wrap svg rect")
        page.hover(".ops tbody tr >> nth=1")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "2-overlay.png"))
        page.click("header label.toggle")
        page.click("button.btn.primary.big")
        frames: list[bytes] = []
        logged_fail = False
        for _ in range(240):  # record the live log until the verdict appears
            frames.append(page.screenshot())
            if not logged_fail and page.locator(".ev.fail").count() >= 2:
                page.wait_for_timeout(1200)
                page.screenshot(path=str(OUT / "3-live-log.png"))
                logged_fail = True
            if page.locator(".verdict-badge").count():
                break
            page.wait_for_timeout(350)
        page.wait_for_selector(".verdict-badge", timeout=120000)
        page.wait_for_timeout(700)
        frames += [page.screenshot()] * 6
        _gif(frames, OUT / "agent-repair.gif")
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "4-results.png"))
        page.wait_for_selector(".inspector", timeout=120000)
        page.wait_for_selector(".panel.explain", timeout=120000)
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "4-results-full.png"), full_page=True)

        # inside the circuit: step back to the superposition, then the analyses
        page.locator(".inspector").scroll_into_view_if_needed()
        page.click("button[aria-label='Previous step']")
        page.wait_for_timeout(500)
        panel = lambda title: page.locator(".panel", has=page.locator("h2", has_text=title)).first  # noqa: E731
        panel("Inside the circuit").screenshot(path=str(OUT / "6-inspector.png"))
        page.click("button[aria-label='Next step']")
        page.wait_for_timeout(500)
        panel("Inside the circuit").screenshot(path=str(OUT / "6-inspector-entangled.png"))
        panel("How good must the hardware be").screenshot(path=str(OUT / "7-hardware.png"))
        panel("How good must the hardware be").locator(".whatif input[type=range]").fill("48")
        page.wait_for_timeout(700)
        panel("How good must the hardware be").screenshot(path=str(OUT / "13-whatif.png"))
        panel("Zero-noise extrapolation").screenshot(path=str(OUT / "14-zne.png"))
        panel("Error budget").screenshot(path=str(OUT / "7-budget.png"))
        panel("On real chip layouts").screenshot(path=str(OUT / "7-layouts.png"))
        page.click(".chip-btn:has-text('Why did the first attempt fail?')")
        page.wait_for_selector(".qa .a p")
        page.click(".chip-btn:has-text('How good must the hardware be?')")
        page.wait_for_function("document.querySelectorAll('.qa .a p').length >= 2")
        page.wait_for_timeout(300)
        panel("Ask about this result").screenshot(path=str(OUT / "8-ask.png"))

        # describe it in words
        page.click("nav.steps button >> nth=0")
        page.fill("input[aria-label='Describe a circuit or network']", "Bernstein-Vazirani with secret 1011")
        page.click("button:has-text('Build it')")
        page.wait_for_selector(".ops")
        page.click("button:has-text('Step through')")
        page.wait_for_selector(".inspector")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "9-describe.png"))

        # find a shorter circuit, proven equal; the entanglement web of a W state
        page.click("nav.steps button >> nth=0")
        page.click(".spec-list button:has-text('Phase estimation')")
        page.click(".optimizer button:has-text('Find a shorter circuit')")
        page.wait_for_selector(".opt-table", timeout=60000)
        page.wait_for_timeout(400)
        page.locator(".optimizer").screenshot(path=str(OUT / "15-optimizer.png"))
        page.click("nav.steps button >> nth=0")
        page.click(".spec-list button:has-text('W state')")
        page.wait_for_selector(".live-strip .ent-web")
        page.wait_for_timeout(400)
        page.locator(".live-strip").screenshot(path=str(OUT / "16-entanglement-web.png"))
        page.click("button:has-text('Step through')")
        page.wait_for_selector(".panel:has(h2:has-text('Bell test'))", timeout=60000)
        page.wait_for_timeout(300)
        panel("Bell test").screenshot(path=str(OUT / "17-bell-test.png"))
        page.click("nav.steps button >> nth=0")
        page.click(".spec-list button:has-text('GHZ')")
        page.click("button:has-text('Step through')")
        page.wait_for_selector(".panel:has(h2:has-text('State tomography'))", timeout=60000)
        page.wait_for_timeout(300)
        panel("State tomography").screenshot(path=str(OUT / "18-tomography.png"))

        # a challenge solved with the click-to-compose palette
        page.click("nav.steps button >> nth=0")
        tab("Labs")
        page.click(".challenge-card:has-text('Bell pair')")
        page.wait_for_selector(".check-msg")
        page.click(".gate-btn:text-is('H')")
        page.click(".preview rect[aria-label='Add to q0']")
        page.click(".gate-btn:text-is('CX')")
        page.click(".preview rect[aria-label='Add to q0']")
        panel("Spec").evaluate("el => el.scrollIntoView({block: 'start'})")
        box = page.locator(".preview rect[aria-label='Add to q1']").bounding_box()
        page.mouse.move(box["x"] + 120, box["y"] + box["height"] / 2)
        page.wait_for_timeout(400)
        panel("Spec").screenshot(path=str(OUT / "11-compose.png"))
        page.click(".preview rect[aria-label='Add to q1']")
        page.wait_for_selector(".solved-box")
        page.wait_for_timeout(1200)
        page.locator(".panel.challenge").screenshot(path=str(OUT / "10-challenge.png"))

        # network: preset A from the spec list
        page.click("nav.steps button >> nth=0")
        tab("Sketch to code")
        page.click("text=Preset A: satellite link")
        page.wait_for_selector(".ops")
        page.click("button.btn.primary.big")
        page.wait_for_selector(".verdict-badge", timeout=120000)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "5-network.png"), full_page=True)
        panel("Network map").screenshot(path=str(OUT / "12-network-map.png"))
        browser.close()
        if errors:
            print("console errors:", *errors, sep="\n  ")
    for f in sorted(OUT.glob("*.png")):
        print(f.relative_to(ROOT))


if __name__ == "__main__":
    main()
