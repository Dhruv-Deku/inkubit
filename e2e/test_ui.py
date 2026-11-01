"""End to end: the built app in a real browser, on the offline (mock) models, with its own server.

    (cd frontend && npm run build)
    python -m pytest e2e -q                                  # Playwright's Chromium (CI)
    E2E_BROWSER_CHANNEL=msedge python -m pytest e2e -q       # or the system Edge

The section list and the tour's steps are read from App.tsx and Tour.tsx, so the tests follow the app as it changes.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
TOUR = (ROOT / "frontend" / "src" / "components" / "Tour.tsx").read_text(encoding="utf-8")
SECTIONS = [(m[0], m[1], re.findall(r"'([^']+)'|\"([^\"]+)\"", m[2]))
            for m in re.findall(r"\{ id: '(\w+)', label: '([^']+)', hint: '[^']*', panels: \[([^\]]*)\] \}", APP)]
SECTIONS = [(sid, label, [a or b for a, b in panels]) for sid, label, panels in SECTIONS]
TOUR_PANELS = re.findall(r"panel: '([^']+)'", TOUR)
CONDITIONAL = {"Recent runs"}  # shown only once something has run


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server():
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        pytest.skip("build the frontend first: cd frontend && npm run build")
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if k not in ("META_API_KEY", "QCANVAS_PUBLIC")}
    env |= {"QCANVAS_MODEL_PROVIDER": "mock", "PYTHONUNBUFFERED": "1"}
    log = open(ROOT / "e2e" / "server.log", "w", encoding="utf-8")  # noqa: SIM115 - closed below
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "qcanvas.api.app:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=ROOT / "backend", env=env, stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            if httpx.get(f"{url}/api/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        if proc.poll() is not None:
            raise RuntimeError("the server stopped; see e2e/server.log")
        time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("the server did not start in 60 s")
    assert httpx.get(f"{url}/api/health").json()["mode"] != "meta"  # never a billed call from the tests
    yield url
    proc.terminate()
    proc.wait(10)
    log.close()


@pytest.fixture(scope="session")
def browser():
    channel = os.environ.get("E2E_BROWSER_CHANNEL")
    with sync_playwright() as p:
        b = p.chromium.launch(channel=channel) if channel else p.chromium.launch()
        yield b
        b.close()


def open_page(browser, url: str, width: int = 1440, height: int = 950) -> tuple[Page, list[str]]:
    page = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"page error: {e}"))
    # a fetch that 404s on purpose (no hardware run yet) logs "Failed to load resource"; anything else is a bug
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
    page.goto(url, wait_until="networkidle")
    return page, errors


def heading(page: Page, title: str):
    return page.locator(".panel h2", has_text=re.compile("^" + re.escape(title)))


def test_the_source_lists_were_read():
    assert len(SECTIONS) == 5 and all(panels for _, _, panels in SECTIONS)
    assert len(TOUR_PANELS) >= 8


def test_every_section_shows_its_panels(server, browser):
    page, errors = open_page(browser, server)
    assert heading(page, "Mission control").first.is_visible()
    for sid, label, panels in SECTIONS:
        page.get_by_role("tab", name=re.compile("^" + re.escape(label))).click()
        for title in panels:
            if title in CONDITIONAL:
                continue
            h = heading(page, title).first
            h.wait_for(state="visible", timeout=30_000)
        assert f"tab={sid}" in page.url
    assert not errors, errors
    page.close()


def test_a_sample_sketch_becomes_verified_code(server, browser):
    page, errors = open_page(browser, server + "/#tab=build")
    page.locator("button.sample").first.click()
    run = page.locator("button.btn.primary.big", has_text=re.compile("^Run "))
    run.wait_for(timeout=60_000)  # the sketch was read into a spec and checked
    page.wait_for_function("[...document.querySelectorAll('button.btn.primary.big')].some(b => b.textContent.startsWith('Run ') && !b.disabled)")
    run.click()
    page.locator(".verdict-badge.pass").wait_for(timeout=120_000)
    assert "Verified" in page.locator(".verdict-badge").inner_text()
    assert not errors, errors
    page.close()


def test_the_guided_tour_lands_on_every_step_and_finishes_its_runs(server, browser):
    page, errors = open_page(browser, server + "/#tour")
    page.locator(".tour").wait_for()
    for k, title in enumerate(TOUR_PANELS):
        page.wait_for_timeout(1300)  # the step scrolls twice (150 ms and 1.1 s) while sections mount
        box = heading(page, title).first.bounding_box()
        assert box is not None, f"step {k + 1}: no '{title}' panel"
        assert 0 <= box["y"] <= 400, f"step {k + 1}: '{title}' is at {box['y']:.0f} px, not in view"
        if k + 1 < len(TOUR_PANELS):
            page.get_by_role("button", name="Next").click()
    page.locator(".mission-report").wait_for(timeout=120_000)  # the mission the tour started
    link = page.get_by_role("link", name="Download report")
    link.wait_for(timeout=60_000)
    page_html = page.request.get(server + link.get_attribute("href"))
    assert page_html.status == 200 and page_html.text().startswith("<!doctype html>") and "Plan" in page_html.text()
    page.get_by_role("button", name="Done").click()
    page.get_by_role("tab", name=re.compile("^Discover")).click()
    page.locator(".disc-bar-row").first.wait_for(timeout=180_000)  # the discovery run it started
    assert not errors, errors
    page.close()


def test_the_satellite_planner_flies_a_real_satellite(server, browser):
    page, errors = open_page(browser, server + "/#tab=hardware")
    card = page.locator(".sat-card")
    card.wait_for(timeout=90_000)  # CelesTrak, else the shipped snapshot; the forecast is optional
    assert "NORAD 66769" in card.inner_text()
    assert page.locator(".panel.globe canvas").bounding_box()["width"] > 200
    assert not errors, errors
    page.close()


def test_no_section_scrolls_sideways_on_a_phone(server, browser):
    page, errors = open_page(browser, server, width=390, height=844)
    for _, label, _ in SECTIONS:
        page.get_by_role("tab", name=re.compile("^" + re.escape(label))).click()
        page.wait_for_timeout(1500)
        over = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert over <= 0, f"{label}: {over} px of sideways scroll at 390 px"
    assert not errors, errors
    page.close()
