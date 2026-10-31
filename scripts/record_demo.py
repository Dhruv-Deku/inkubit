"""Record the demo video: a captioned screen recording of the real app.

    .venv/Scripts/python scripts/record_demo.py [base_url] [--out docs/video/q-canvas-demo.mp4]

Needs the backend serving the built frontend (scripts/dev.sh, or uvicorn on :8000).
The script only drives the UI and lays captions over it; every number on screen
comes from a real run. Captions name Meta models only when the backend reports
live Meta mode, so an offline recording never claims a model call it did not make.

Frames come from the browser's own screencast (crisp text, real timing) and are
encoded to H.264 with the ffmpeg bundled in imageio-ffmpeg.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import imageio_ffmpeg
from playwright.async_api import Locator, Page, async_playwright

ROOT = Path(__file__).resolve().parent.parent
VIEW_W, VIEW_H, SCALE = 1440, 810, 4 / 3  # CSS viewport; 1920x1080 device pixels
FPS = 30

OVERLAY_JS = r"""
(() => {
  if (window.__demo) return;
  const css = `
  #demo-cap { position: fixed; left: 50%; bottom: 34px; transform: translateX(-50%) translateY(8px);
    max-width: 1060px; width: max-content; padding: 14px 24px; border-radius: 14px;
    background: rgba(22,22,25,.94); border: 1px solid rgba(255,255,255,.10);
    box-shadow: 0 10px 30px rgba(0,0,0,.35); color: #ededea; z-index: 2147483646;
    font: 500 21px/1.42 Inter, system-ui, sans-serif; letter-spacing: -.005em; text-align: center;
    opacity: 0; transition: opacity .35s ease, transform .35s ease; pointer-events: none; }
  #demo-cap.on { opacity: 1; transform: translateX(-50%) translateY(0); }
  #demo-cap b { color: #fff; font-weight: 650; }
  #demo-card { position: fixed; inset: 0; background: #111113; z-index: 2147483645; display: flex;
    flex-direction: column; align-items: center; justify-content: center; gap: 18px; text-align: center;
    opacity: 0; transition: opacity .6s ease; pointer-events: none; padding: 0 120px; }
  #demo-card.on { opacity: 1; }
  #demo-card h1 { margin: 0; color: #f2f1ee; font: 650 76px/1.05 Inter, system-ui, sans-serif; letter-spacing: -.03em; }
  #demo-card h1.small { font-size: 54px; }
  #demo-card p { margin: 0; max-width: 980px; color: #b7b6b1; font: 400 27px/1.45 Inter, system-ui, sans-serif; }
  #demo-card .foot { margin-top: 26px; display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
  #demo-card .chip { padding: 7px 14px; border-radius: 999px; border: 1px solid rgba(255,255,255,.12);
    color: #d8d7d3; font: 500 17px/1 Inter, system-ui, sans-serif; background: #1a1a1d; }
  #demo-card .note { margin-top: 8px; color: #85847f; font: 400 17px/1.4 Inter, system-ui, sans-serif; }
  #demo-tag { position: fixed; top: 14px; left: 50%; transform: translateX(-50%); padding: 6px 14px;
    border-radius: 999px; background: rgba(22,22,25,.94); border: 1px solid rgba(255,255,255,.12);
    color: #cfcec9; font: 600 14px/1 Inter, system-ui, sans-serif; letter-spacing: .02em;
    z-index: 2147483646; opacity: 0; transition: opacity .25s; pointer-events: none; }
  #demo-tag.on { opacity: 1; }
  #demo-cursor { position: fixed; left: 0; top: 0; width: 18px; height: 18px; margin: -9px 0 0 -9px;
    border-radius: 50%; background: rgba(255,255,255,.92); border: 2px solid #18181b;
    box-shadow: 0 1px 4px rgba(0,0,0,.45); z-index: 2147483647; pointer-events: none;
    transition: width .12s, height .12s, margin .12s, opacity .4s; opacity: 0; }
  #demo-cursor.on { opacity: 1; }
  #demo-cursor.down { width: 13px; height: 13px; margin: -6.5px 0 0 -6.5px; }
  `;
  const make = () => {
    if (document.getElementById('demo-cap')) return;
    const style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);
    for (const id of ['demo-card', 'demo-cap', 'demo-tag', 'demo-cursor']) {
      const el = document.createElement('div'); el.id = id; document.body.appendChild(el);
    }
    document.getElementById('demo-cursor').style.transform = 'translate(-40px,-40px)';
  };
  document.addEventListener('DOMContentLoaded', make);
  document.addEventListener('mousemove', (e) => {
    const c = document.getElementById('demo-cursor');
    if (!c) return;
    c.style.transform = `translate(${e.clientX}px, ${e.clientY}px)`;
    c.classList.add('on');  // fade out when the pointer rests, so it never sits on the content
    clearTimeout(window.__demoIdle);
    window.__demoIdle = setTimeout(() => c.classList.remove('on'), 1600);
  }, true);
  document.addEventListener('mousedown', () => document.getElementById('demo-cursor')?.classList.add('down'), true);
  document.addEventListener('mouseup', () => document.getElementById('demo-cursor')?.classList.remove('down'), true);
  const esc = (s) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  window.__demo = {
    caption(text) {
      make();
      const el = document.getElementById('demo-cap');
      if (!text) { el.classList.remove('on'); return; }
      const show = () => { el.innerHTML = esc(text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>'); el.classList.add('on'); };
      if (el.classList.contains('on')) { el.classList.remove('on'); setTimeout(show, 260); } else show();
    },
    card(title, sub, chips, note, small) {
      make();
      const el = document.getElementById('demo-card');
      el.innerHTML = `<h1 class="${small ? 'small' : ''}">${esc(title)}</h1>` + (sub ? `<p>${esc(sub)}</p>` : '')
        + (chips && chips.length ? `<div class="foot">${chips.map((c) => `<span class="chip">${esc(c)}</span>`).join('')}</div>` : '')
        + (note ? `<div class="note">${esc(note)}</div>` : '');
      el.classList.add('on');
    },
    tag(text) {
      make();
      const el = document.getElementById('demo-tag');
      if (text) { el.textContent = text; el.classList.add('on'); } else el.classList.remove('on');
    },
    hideCard() { document.getElementById('demo-card')?.classList.remove('on'); },
  };
})();
"""


class Recorder:
    """Collects screencast frames with arrival times and encodes them at a fixed rate."""

    def __init__(self, page: Page, workdir: Path):
        self.page, self.dir = page, workdir
        self.frames: list[tuple[float, Path]] = []
        self.speeds: list[tuple[float, float]] = []  # (real time, playback factor from then on)
        self.cdp = None
        self.t_end = 0.0

    def speed(self, factor: float) -> None:
        """Play everything from now on ``factor`` times faster (1 = real time)."""
        self.speeds.append((time.monotonic(), factor))

    def _video_time(self, t: float) -> float:
        """Map a real capture time to its time in the edited video."""
        marks = [(self.frames[0][0], 1.0), *self.speeds]
        out = 0.0
        for i, (start, factor) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else float("inf")
            if t <= start:
                break
            out += (min(t, end) - start) / factor
        return out

    async def start(self) -> None:
        self.cdp = await self.page.context.new_cdp_session(self.page)

        def on_frame(params: dict) -> None:
            path = self.dir / f"f{len(self.frames):06d}.jpg"
            path.write_bytes(base64.b64decode(params["data"]))
            self.frames.append((time.monotonic(), path))
            asyncio.ensure_future(self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]}))

        self.cdp.on("Page.screencastFrame", on_frame)
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 95,
                                                     "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1})

    async def stop(self) -> None:
        self.t_end = time.monotonic()
        await self.cdp.send("Page.stopScreencast")

    def encode(self, out: Path) -> None:
        if not self.frames:
            raise RuntimeError("no frames were captured")
        # resample to a fixed rate: each output frame shows the newest captured frame at that moment
        times = [self._video_time(t) for t, _ in self.frames]
        total = self._video_time(self.t_end)
        picks: list[list] = []  # [path, number of output frames]
        j = 0
        for k in range(int(total * FPS) + 1):
            while j + 1 < len(times) and times[j + 1] <= k / FPS:
                j += 1
            path = self.frames[j][1]
            if picks and picks[-1][0] == path:
                picks[-1][1] += 1
            else:
                picks.append([path, 1])
        lines = ["ffconcat version 1.0"]
        for path, n in picks:
            lines += [f"file '{path.as_posix()}'", f"duration {n / FPS:.6f}"]
        lines.append(f"file '{picks[-1][0].as_posix()}'")  # the concat demuxer drops the last duration
        listing = self.dir / "frames.ffconcat"
        listing.write_text("\n".join(lines), encoding="utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
               "-i", str(listing), "-vf", "scale=1920:1080:flags=lanczos:out_range=tv,format=yuv420p", "-color_range", "tv", "-r", str(FPS),
               "-fps_mode", "cfr", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-tune", "stillimage",
               "-movflags", "+faststart", str(out)]
        subprocess.run(cmd, check=True)


class Director:
    """Moves a visible cursor, clicks, scrolls smoothly and shows captions."""

    def __init__(self, page: Page, live: bool, rec: Recorder | None = None):
        self.page, self.live, self.rec = page, live, rec
        self.x, self.y = VIEW_W / 2, VIEW_H / 2

    async def fast(self, factor: float, label: str) -> None:
        """Speed up waiting (sandbox runs, model calls) and say so on screen."""
        await self.page.evaluate("t => window.__demo.tag(t)", f"{factor:g}× speed · {label}")
        await self.wait(0.15)
        if self.rec:
            self.rec.speed(factor)

    async def normal(self) -> None:
        if self.rec:
            self.rec.speed(1.0)
        await self.page.evaluate("window.__demo.tag('')")

    async def wait(self, seconds: float) -> None:
        await self.page.wait_for_timeout(seconds * 1000)

    async def caption(self, text: str | None, hold: float = 0) -> None:
        await self.page.evaluate("t => window.__demo.caption(t)", text or "")
        if hold:
            await self.wait(hold)

    async def card(self, title: str, sub: str = "", chips: list[str] | None = None, note: str = "",
                   small: bool = False, hold: float = 4) -> None:
        await self.page.evaluate("a => window.__demo.card(...a)", [title, sub, chips or [], note, small])
        await self.wait(hold)

    async def hide_card(self) -> None:
        await self.page.evaluate("window.__demo.hideCard()")
        await self.wait(0.7)

    async def scroll_to(self, target: Locator, block: str = "start", pause: float = 1.0) -> None:
        await target.first.evaluate(f"el => el.scrollIntoView({{behavior: 'smooth', block: '{block}'}})")
        await self.wait(pause)

    async def scroll_top(self) -> None:
        await self.page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        await self.wait(0.8)

    async def settle(self, target: Locator, timeout: float = 5.0) -> dict | None:
        """The target's box once it has stopped moving (smooth scrolls and late layout shift the page)."""
        await target.first.wait_for(state="visible", timeout=60_000)
        last, waited = None, 0.0
        while waited < timeout:
            box = await target.first.bounding_box()
            if box and last and all(abs(box[k] - last[k]) < 0.5 for k in ("x", "y", "width", "height")):
                return box
            last = box
            await self.page.wait_for_timeout(150)
            waited += 0.15
        return last

    async def move(self, target: Locator, fx: float = 0.5, fy: float = 0.5, steps: int = 30) -> None:
        box = await self.settle(target)
        if box is None:
            raise RuntimeError(f"not visible: {target}")
        self.x, self.y = box["x"] + box["width"] * fx, box["y"] + box["height"] * fy
        await self.page.mouse.move(self.x, self.y, steps=steps)

    async def click(self, target: Locator, pause: float = 0.25) -> None:
        await self.move(target)
        await self.wait(pause)
        await self.page.mouse.click(self.x, self.y)

    async def type_into(self, target: Locator, text: str) -> None:
        await self.click(target)
        await self.page.keyboard.press("Control+A")
        await self.page.keyboard.type(text, delay=120)


def models_or(live: bool, meta: str, offline: str) -> str:
    return meta if live else offline


async def circuit_story(d: Director) -> None:
    page, live = d.page, d.live
    await d.caption("Start from a photo of a sketch, one of the samples, or a JSON spec.", hold=3.2)
    await d.click(page.locator(".sample", has_text="Bell pair"))
    await d.caption(models_or(live, "**SAM 3.1** finds every drawn part. **Muse Spark** reads the photo into a spec…",
                              "The sketch is segmented and read into a spec (offline mode: recorded answers)…"))
    if live:
        await d.fast(4, "model calls")
    await page.wait_for_selector(".overlay-wrap svg rect", timeout=180_000)
    await d.normal()
    await d.wait(0.6)
    await d.caption("…a validated JSON spec, with every gate linked to the box it was read from.")
    rects = page.locator(".overlay-wrap svg rect")
    for i in range(min(await rects.count(), 4)):
        await d.move(rects.nth(i), steps=22)
        await d.wait(0.9)

    # show the live validation on the CNOT row, then undo it
    row = await page.evaluate("""() => [...document.querySelectorAll('.ops tbody tr')]
        .findIndex(r => r.querySelector('select')?.value === 'CX')""")
    if row >= 0:
        control = page.locator(f".ops tbody tr >> nth={row}").locator("td >> nth=3").locator("input")
        await d.caption("Nothing runs until you agree with the reading. Every edit is checked as you type.")
        await d.scroll_to(control, block="center", pause=0.4)
        await d.type_into(control, "1")
        await page.wait_for_selector(".notice.error", timeout=10_000)
        await d.scroll_to(page.locator(".notice.error"), block="center", pause=2.6)
        await d.type_into(control, "0")
        await page.wait_for_selector(".notice.error", state="detached", timeout=10_000)
        await d.wait(0.8)

    await d.scroll_top()
    await d.caption("**Demo mode** plants a real bug in the first attempt, so you can watch the agent catch it.")
    await d.click(page.locator("header label.toggle"))
    await d.wait(1.6)
    await d.scroll_to(page.locator(".run-bar"), block="center", pause=0.6)
    await d.click(page.locator("button.btn.primary.big"))
    await d.wait(0.6)
    await d.caption(models_or(live, "**Muse Spark** writes the Qiskit code. It runs in a sandbox under realistic noise.",
                              "The agent writes the Qiskit code and runs it in a sandbox under realistic noise."))
    await d.wait(1.2)
    await d.fast(4, "sandbox run")
    await page.wait_for_selector(".ev.fail", timeout=180_000)
    await d.normal()
    await d.wait(0.4)
    await d.caption("The verifier predicts the exact answer from the spec, never from the code. "
                    "This run disagrees, so it **fails**.", hold=3.4)
    await d.caption("The agent explains why in plain words: the two bits should agree and don't, "
                    "so the entangling gate is missing.")
    await page.locator(".ev .meta span", has_text="Repair").first.wait_for(timeout=180_000)
    await d.caption(models_or(live, "**Muse Spark** gets the spec, the failing code and that evidence, and repairs it.",
                              "The repairer gets the spec, the failing code and that evidence, and fixes it."))
    await page.locator(".ev.ok .meta span", has_text="Repair").first.wait_for(timeout=180_000)
    await d.wait(2.2)
    await d.fast(4, "sandbox run")
    await page.wait_for_selector(".verdict-badge", timeout=240_000)
    await d.normal()
    await d.wait(0.5)
    await d.caption("Attempt 2 matches the prediction within the shot-noise limit: **verified**.", hold=4)

    await d.caption("Predicted, measured and the noiseless ideal side by side: the cost of noise is shown, not hidden.")
    await d.scroll_to(page.locator(".panel", has=page.locator("h2", has_text="Outcomes")), pause=4.2)
    explain = page.locator(".panel.explain")
    await explain.wait_for(timeout=180_000)
    await d.caption(models_or(live, "**Muse Spark** explains the result for a student, using the real numbers.",
                              "A plain-language explanation, written from the real numbers."))
    await d.scroll_to(explain, pause=4.6)

    ask = page.locator(".panel", has=page.locator("h2", has_text="Ask about this result"))
    await d.scroll_to(ask, block="center", pause=0.4)
    await d.caption(models_or(live, "Ask **Muse Spark** anything about the run: it answers only from this run's numbers.",
                              "Ask about the run: answers come only from this run's numbers."))
    await d.click(ask.locator(".chip-btn", has_text="Why did the first attempt fail?"))
    await ask.locator(".qa .a p").first.wait_for(timeout=120_000)
    await d.wait(4.2)

    inside = page.locator(".panel", has=page.locator("h2", has_text="Inside the circuit"))
    await inside.wait_for(timeout=120_000)
    await d.scroll_to(inside, pause=0.5)
    await d.caption("Step through the exact state, gate by gate. When the CNOT entangles the qubits, "
                    "their Bloch arrows shrink to the centre.")
    await d.click(inside.locator("button", has_text="Play"))
    await d.wait(3.6)
    sweep = page.locator(".panel", has=page.locator("h2", has_text="How good must the hardware be"))
    await d.caption("Which noise costs the most, and how much better the hardware must get for a 99% match.")
    await d.scroll_to(page.locator(".panel", has=page.locator("h2", has_text="Entanglement")), pause=2.6)
    await d.scroll_to(sweep, block="center", pause=3.4)
    bell = page.locator(".panel", has=page.locator("h2", has_text="Bell test"))
    if await bell.count():
        await d.caption("A Bell test: could any classical explanation fake these correlations? "
                        "Even with realistic noise, no: by over ten standard errors.")
        await d.scroll_to(bell, block="center", pause=4.0)
    zne = page.locator(".panel", has=page.locator("h2", has_text="Zero-noise extrapolation"))
    if await zne.count():
        await d.caption("Error mitigation: run it noisier on purpose (every gate folded), then extrapolate back "
                        "to zero noise. Shown with exact odds and with real shot counts.")
        await d.scroll_to(zne, block="center", pause=4.4)
    code = page.locator(".panel", has=page.locator("h2", has_text="Code"))
    await d.scroll_to(code, pause=0.6)
    await d.caption("Standalone Qiskit you can download, with the exact change the repair made.")
    diff_btn = code.locator(".seg button", has_text="Changes from attempt")
    if await diff_btn.count():
        await d.click(diff_btn)
    await d.wait(3.6)
    figs = page.locator(".panel", has=page.locator("h2", has_text="Diagrams"))
    if await figs.count():
        await d.caption(models_or(live, "**Muse Image** draws a clean illustration, always next to the exact Qiskit drawing.",
                                  "The exact circuit, drawn by Qiskit."))
        await d.scroll_to(figs, pause=3.8)
    await d.caption("Every result says which model produced it.")
    await d.scroll_to(page.locator(".panel", has=page.locator("h2", has_text="Models used")), block="center", pause=3.4)


async def words_story(d: Director) -> None:
    page, live = d.page, d.live
    await d.caption(None)
    await d.scroll_top()
    await d.click(page.locator("nav.steps button >> nth=0"))
    await d.wait(0.5)
    box = page.locator("input[aria-label='Describe a circuit or network']")
    await d.scroll_to(box, block="center", pause=0.3)
    await d.caption(models_or(live, "No sketch? Describe it in words, and **Muse Spark** builds the spec.",
                              "No sketch? Describe it in words (offline: named algorithms and gate lists)."))
    await d.click(box)
    await page.keyboard.type("Bernstein-Vazirani with secret 1011", delay=55)
    await d.wait(0.4)
    await d.click(page.locator("button", has_text="Build it"))
    await page.wait_for_selector(".ops", timeout=180_000)
    await d.wait(1.6)
    await d.scroll_to(page.locator(".run-bar"), block="center", pause=0.3)
    await d.caption("Step through it before running anything: one query to the oracle reveals the secret.")
    await d.click(page.locator("button", has_text="Step through"))
    await page.wait_for_selector(".inspector", timeout=60_000)
    await d.scroll_to(page.locator(".inspector"), block="start", pause=0.4)
    await d.click(page.locator(".inspector button", has_text="Play"))
    await d.wait(7.5)


async def optimizer_story(d: Director) -> None:
    page, live = d.page, d.live
    await d.caption(None)
    await d.scroll_top()
    await d.click(page.locator("nav.steps button >> nth=0"))
    await d.wait(0.5)
    item = page.locator(".spec-list button", has_text="Phase estimation")
    await d.scroll_to(item, block="center", pause=1.1)  # let the smooth scroll settle before reading its position
    await d.click(item)
    await page.wait_for_selector(".optimizer button", timeout=60_000)
    opt = page.locator(".optimizer")
    await d.scroll_to(opt, block="start", pause=0.3)
    await d.caption(models_or(live, "Find a shorter circuit: rewrite rules, the Qiskit compiler and **Muse Spark** compete. "
                                    "Exact simulation proves each answer, or rejects it.",
                              "Find a shorter circuit: rewrite rules and the Qiskit compiler compete. "
                              "Exact simulation proves each answer, or rejects it."))
    await d.click(opt.locator("button", has_text="Find a shorter circuit"))
    await page.wait_for_selector(".opt-table", timeout=180_000)
    await d.wait(2.4)
    await d.caption("Every step has a reason you can check. Phase estimation of a known phase shrinks to one X: "
                    "its answer was fixed in advance, and the panel says so.")
    await d.scroll_to(page.locator(".opt-detail"), block="center", pause=5.0)


async def challenge_story(d: Director) -> None:
    page, live = d.page, d.live
    await d.caption(None)
    await d.scroll_top()
    await d.click(page.locator("nav.steps button >> nth=0"))
    await d.wait(0.5)
    board = page.locator(".panel", has=page.locator("h2", has_text="Challenges"))
    await d.scroll_to(board, block="center", pause=0.4)
    await d.caption(models_or(live, "Or learn by playing: puzzles scored exactly against a hidden answer. "
                                    "**Muse Spark** gives hints, never the solution.",
                              "Or learn by playing: puzzles scored exactly against a hidden answer, with par like golf."))
    await d.wait(1.2)
    await d.click(board.locator(".challenge-card", has_text="Bell pair"))
    await page.wait_for_selector(".check-msg", timeout=60_000)
    await d.wait(1.4)
    await d.scroll_to(page.locator(".palette"), block="start", pause=0.4)
    await d.caption("Pick a gate, click a wire. The live state and the score update on every click.")
    for gate, wires in (("H", [0]), ("CX", [0, 1])):
        await d.click(page.locator(f".gate-btn:text-is('{gate}')"))
        for q in wires:
            await d.move(page.locator(f".preview rect[aria-label='Add to q{q}']"), fx=0.18)
            await d.wait(0.5)
            await page.mouse.click(d.x, d.y)
            await d.wait(0.6)
    await page.wait_for_selector(".solved-box", timeout=30_000)
    await d.wait(1.0)
    await d.caption("Solved at par: three stars, what it teaches, and how much survives real noise.")
    await d.scroll_to(page.locator(".panel.challenge"), block="start", pause=4.2)


async def network_story(d: Director) -> None:
    page, live = d.page, d.live
    await d.caption(None)
    await d.scroll_top()
    await d.click(page.locator("nav.steps button >> nth=0"))
    await d.wait(0.6)
    await d.caption("Q-Canvas also plans **quantum networks**: here, two ground stations share entanglement through a satellite.")
    sat = page.locator(".sample", has_text="Satellite")
    await d.scroll_to(sat, block="center", pause=0.4)
    await d.click(sat)
    await page.wait_for_selector(".overlay-wrap svg rect", timeout=180_000)
    await d.wait(3.4)
    await d.scroll_to(page.locator(".run-bar"), block="center", pause=0.4)
    await d.click(page.locator("button.btn.primary.big"))
    await d.caption("It models every link from physics: diffraction, turbulence, fiber loss, memory decoherence.")
    await page.locator(".ev .meta span", has_text="Bottleneck").first.wait_for(timeout=60_000)
    await d.wait(1.6)
    await d.caption("Then it finds the bottleneck, tries real fixes, re-simulates each one and keeps the best.")
    await page.wait_for_selector(".verdict-badge", timeout=240_000)
    await d.wait(1.8)
    await d.caption("Before and after, from the same physics model: entangled pairs in flight, thicker links deliver more.")
    netmap = page.locator(".panel", has=page.locator("h2", has_text="Network map"))
    await d.scroll_to(netmap, block="center", pause=2.4)
    await d.click(netmap.locator("button", has_text="Before"))
    await d.wait(2.2)
    await d.click(netmap.locator("button", has_text="After the fix"))
    await d.wait(2.4)
    await d.caption("Every candidate fix, with its re-simulated rates.")
    await d.scroll_to(page.locator(".panel", has=page.locator("h2", has_text="Fixes the agent tried")), block="center", pause=4)
    checks = page.locator(".panel", has=page.locator("h2", has_text="Sanity checks"))
    if await checks.count():
        await d.caption("And the result has to pass physics sanity checks.")
        await d.scroll_to(checks, block="center", pause=3.4)
    await d.caption(None)


def panel(page: Page, title: str) -> Locator:
    return page.locator(".panel", has=page.locator("h2", has_text=title))


async def copilot_story(d: Director) -> None:
    page, live = d.page, d.live
    box = panel(page, "Ask Q-Canvas")
    await d.scroll_to(box, block="start", pause=0.6)
    await d.caption(models_or(live, "Ask anything. **Muse Spark** picks the right exact tools, runs them, and answers.",
                              "Ask anything: the question is routed to the right exact tool."), hold=3.4)
    questions = [
        ("Ana fights with Ben and Cai, Ben fights with Dev, Cai fights with Dev and Eli. Split them into two teams.",
         "A people problem becomes a graph, and **QAOA** on a simulated quantum computer splits it."),
        ("Make a 3-qubit GHZ state. How well does it survive real hardware?",
         "It writes the circuit itself, simulates it exactly, then again under realistic noise."),
        ("Compare the energy of H2 at 0.74 and 2.5 angstrom. Why does Hartree-Fock fail when it is stretched?",
         "Chemistry from first principles: two tool calls in parallel, one per bond length."),
    ]
    for i, (q, cap) in enumerate(questions):
        if i:
            await d.scroll_to(page.locator(".copilot form"), block="center", pause=0.8)
        await d.type_into(page.locator(".copilot-input"), q)
        await d.click(page.locator(".copilot button[type=submit]"))
        await d.caption(cap)
        await d.fast(4, "the model and the tools at work")
        print(f"assistant question {i + 1} sent", flush=True)
        await page.wait_for_function(f"document.querySelectorAll('.copilot-turn .copilot-a, .copilot-turn .notice').length > {i}",
                                     timeout=240_000)
        print(f"assistant question {i + 1} answered", flush=True)
        await d.normal()
        turn = page.locator(".copilot-turn").nth(i)
        await d.scroll_to(turn, block="start", pause=0.8)
        await d.move(turn.locator(".trace-badge"))
        await d.caption("Every number in the answer is traced back to an exact tool result. "
                        "A number the model made up would be flagged here.", hold=4.6 if i == 0 else 3.2)
        card = turn.locator(".copilot-card").first
        await d.scroll_to(card, block="center", pause=2.6)
    await d.caption(None)


async def trust_story(d: Director) -> None:
    page = d.page
    arena = panel(page, "AI alone vs Q-Canvas")
    await d.scroll_to(arena, block="start", pause=0.8)
    await d.caption("Why check at all? We asked the same model to predict circuits alone, like a chatbot with no simulator.", hold=4.2)
    await d.caption("Famous circuits: perfect. Bigger new ones: right only half the time, once **confidently 43% wrong**.", hold=4.6)
    await d.scroll_to(arena.locator(".arena-rows").first, block="center", pause=3.2)
    await d.caption(None)


async def usecases_story(d: Director) -> None:
    page = d.page
    hub = panel(page, "Who it is for")
    await d.scroll_to(hub, block="start", pause=0.8)
    await d.caption("One app for teachers, students, chemists, security, logistics, network planners and researchers.", hold=3.0)
    for who in ("Chemist", "Security", "Logistics"):
        await d.move(hub.locator(".uc-card", has_text=who), steps=24)
        await d.wait(0.6)
    await d.caption("Photos generated with **Muse Image**. Every card opens the real thing.", hold=2.6)
    await d.caption(None)


async def bughunt_story(d: Director) -> None:
    page, live = d.page, d.live
    found: dict[str, int] = {}

    def on_response(resp) -> None:
        if "/api/bughunt/round" in resp.url and "level=" in resp.url and "level" not in found:
            q = dict(kv.split("=") for kv in resp.url.split("?", 1)[1].split("&"))
            found.update(level=int(q["level"]), seed=int(q["seed"]))

    page.on("response", on_response)
    hunt = panel(page, "Bug hunt")
    await d.click(hunt.locator(".seg button", has_text="Tricky"))
    await page.wait_for_selector(".bug-circuit.live .op", timeout=120_000)
    await d.scroll_to(hunt, block="start", pause=0.6)
    await d.caption(models_or(live, "**Bug hunt**: one gate is wrong. You race the clock, and **Muse Spark** plays the same round.",
                              "**Bug hunt**: one gate is wrong. Find it from the histogram."), hold=3.6)
    await d.scroll_to(hunt.locator(".bug-circuit"), block="center", pause=1.0)
    if live:
        await d.fast(4, "Muse Spark thinking")
        try:
            await page.wait_for_selector("text=Muse Spark has answered", timeout=120_000)
        except Exception:  # noqa: BLE001 - the round still plays without it
            pass
        await d.normal()
    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    from qcanvas.bughunt import search  # noqa: E402
    culprit = search(found.get("level", 2), found.get("seed", 0)).culprits[0] if found else 0
    await d.caption("Click the gate you think is broken.")
    await d.click(hunt.locator(".bug-circuit .op").nth(culprit))
    await page.wait_for_selector(".bug-reveal", timeout=120_000)
    await d.scroll_to(hunt.locator(".bug-reveal"), block="center", pause=0.6)
    await d.caption("An exact search tried every one-gate edit, so any gate whose fix restores the odds counts.", hold=4.4)
    page.remove_listener("response", on_response)
    await d.caption(None)


async def labs_story(d: Director) -> None:
    page = d.page
    chem = panel(page, "Molecule lab")
    await d.scroll_to(chem, block="start", pause=0.8)
    await d.caption("**Chemistry**: the hydrogen molecule from first principles, integrals checked against the textbook.", hold=3.4)
    await d.click(chem.locator("button", has_text="pull apart"))
    await d.wait(1.2)
    await d.caption("Pull it apart and the classical shortcut fails by 233 mHa. Raw VQE suffers from noise; "
                    "undoing the calibrated noise lands within chemical accuracy.", hold=5.4)
    spy = panel(page, "Catch the spy")
    await d.scroll_to(spy, block="start", pause=0.8)
    await d.caption("**Security**: BB84 quantum key distribution. Slide in an eavesdropper…", hold=2.2)
    slider = spy.locator("input[aria-label='Share of photons Eve measures']")
    for v in ("0.2", "0.4", "0.6"):
        await d.move(slider, fx=float(v), steps=14)
        await slider.fill(v)
        await d.wait(0.7)
    await d.caption("…and the errors she causes give her away: above 11% the key is thrown out. Physics, not a password.", hold=4.4)
    party = panel(page, "Split the party")
    await d.scroll_to(party, block="start", pause=0.8)
    await d.caption("**Optimization**: QAOA seats feuding guests at two tables, the shape of scheduling and routing problems.", hold=3.4)
    land = party.locator("svg[aria-label^='Expected cut']")
    await d.click(land, pause=0.3)
    await d.wait(1.0)
    await d.caption("Click the landscape to try your own angles against the optimizer.", hold=3.2)
    await d.click(party.locator(".seg button", has_text="3 layers"))
    await d.caption("Three layers find a best seating 95% of the time with perfect qubits, about half with realistic noise.", hold=4.0)
    await d.caption(None)


async def record(base: str, out: Path) -> None:
    with urllib.request.urlopen(f"{base}/api/health", timeout=10) as r:
        health = json.load(r)
    live = health.get("mode") == "meta"
    print(f"backend mode: {health.get('mode_label')}")
    chips = ["SAM 3.1", "Muse Spark", "Muse Image", "Muse Voice", "Qiskit + Aer"]
    note = "" if live else "Offline recording: model answers are recorded mock responses, labelled Mock in the app."

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        context = await browser.new_context(viewport={"width": VIEW_W, "height": VIEW_H},
                                            device_scale_factor=SCALE, color_scheme="dark")
        await context.add_init_script(OVERLAY_JS)
        page = await context.new_page()
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        await page.goto(base)
        await page.wait_for_selector(".sample img")
        await page.wait_for_selector(".copilot-input")
        await page.evaluate("document.fonts.ready")
        d = Director(page, live)
        await page.evaluate("a => window.__demo.card(...a)", ["Q-Canvas", "", [], "", False])
        await d.wait(0.8)

        with tempfile.TemporaryDirectory() as tmp:
            rec = Recorder(page, Path(tmp))
            d.rec = rec
            await rec.start()
            await d.card("Q-Canvas", "A quantum lab you can draw on and talk to. Every answer checked by exact simulation.",
                         chips, note, hold=4.6)
            await page.screenshot(path=str(out.with_suffix(".png")))
            await d.hide_card()
            await copilot_story(d)
            await d.card("A wrong quantum program still runs.",
                         "It just prints the wrong histogram. Draw a circuit on paper: Q-Canvas reads it, writes the code, "
                         "checks the result against an exact prediction, and repairs the code when it is wrong.",
                         small=True, hold=5.0)
            await d.hide_card()
            await d.scroll_to(page.locator(".sample", has_text="Bell pair"), block="center", pause=0.9)
            print('circuit_story', flush=True)
            await circuit_story(d)
            print('optimizer_story', flush=True)
            await optimizer_story(d)
            await d.scroll_top()
            await d.click(page.locator("nav.steps button >> nth=0"))
            await d.wait(0.8)
            print('trust_story', flush=True)
            await trust_story(d)
            print('usecases_story', flush=True)
            await usecases_story(d)
            print('bughunt_story', flush=True)
            await bughunt_story(d)
            print('labs_story', flush=True)
            await labs_story(d)
            await d.card("Q-Canvas", "Sketch it, say it, or ask it. Chemistry, security, optimization, networks, algorithms.",
                         chips, "Every number checked by exact simulation. Every model answer labelled.", hold=5.0)
            await rec.stop()
            print(f"captured {len(rec.frames)} frames over {rec.t_end - rec.frames[0][0]:.1f} s "
                  f"({rec._video_time(rec.t_end):.1f} s after speed-ups); encoding…")
            rec.encode(out)
        await browser.close()
    if errors:
        print("console errors:", *errors, sep="\n  ")
    print(f"wrote {out.relative_to(ROOT)} and {out.with_suffix('.png').relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("base", nargs="?", default="http://127.0.0.1:8000")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "video" / "q-canvas-demo.mp4")
    args = ap.parse_args()
    asyncio.run(record(args.base.rstrip("/"), args.out.resolve()))


if __name__ == "__main__":
    main()
