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
import re
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


def panel(page: Page, title: str) -> Locator:
    return page.locator(".panel", has=page.locator("h2", has_text=title))


async def section(d: Director, label: str) -> None:
    """Open one of the five sections from the sticky tab bar."""
    await d.caption(None)  # a caption never outlives the panel it describes
    await d.scroll_top()
    await d.click(d.page.get_by_role("tab", name=re.compile("^" + re.escape(label))))
    await d.wait(0.8)


async def show(d: Director, title: str, pause: float = 0.9) -> Locator:
    """Scroll a panel to the top of the view (under the sticky tabs) and return it."""
    await d.caption(None)
    p = panel(d.page, title)
    await p.first.wait_for(timeout=60_000)
    await p.first.evaluate("el => el.scrollIntoView({behavior: 'smooth', block: 'start'})")
    await d.wait(pause)
    return p


async def mission_story(d: Director) -> None:
    page, live = d.page, d.live
    mc = panel(page, "Mission control")
    await d.caption("**Mission control**: one request, in words, a photo or speech.", hold=2.4)
    await d.click(mc.locator(".chip-btn", has_text="Secure two cities"))
    await d.wait(1.6)
    await d.caption(models_or(live, "**Muse Spark** turns it into a plan: a graph of exact tools. Independent steps run in parallel.",
                              "The planner turns it into a graph of exact tools. Independent steps run in parallel."))
    await d.click(mc.locator("button.btn.primary", has_text="Launch mission"))
    await page.wait_for_selector(".mnode", timeout=120_000)
    await d.scroll_to(page.locator(".mission-graph-scroll"), block="center", pause=0.3)
    await d.fast(3, "tools and model calls")
    await page.locator(".mission-report").wait_for(timeout=300_000)
    await d.normal()
    await d.caption("Every step passed physics checks and a second, independent simulator before anything was reported.", hold=0.4)
    nodes = page.locator(".mnode.s-done, .mnode.s-repaired")
    if await nodes.count() > 1:
        await d.click(nodes.nth(1))
    await d.wait(3.2)
    await d.scroll_to(page.locator(".mission-report"), block="center", pause=0.4)
    await d.caption(models_or(live, "**Muse Spark** writes the report, and every number in it is traced to the tool that computed it.",
                              "The report's numbers are each traced to the tool that computed them."), hold=4.4)


async def sketch_story(d: Director) -> None:
    page, live = d.page, d.live
    await section(d, "Sketch to code")
    sample = page.locator(".sample", has_text="Bell pair")
    await d.scroll_to(sample, block="center", pause=0.5)
    await d.caption("Where it started: a photo of a pen sketch becomes verified code.", hold=1.6)
    await d.click(sample)
    await d.caption(models_or(live, "**SAM 3.1** finds every drawn part; **Muse Spark** reads the photo into a spec…",
                              "The sketch is segmented and read into a spec…"))
    if live:
        await d.fast(4, "model calls")
    await page.wait_for_selector(".overlay-wrap svg rect", timeout=180_000)
    await d.normal()
    await d.caption("…with every gate linked to the box it was read from.", hold=2.2)
    await d.scroll_top()
    await d.caption("**Demo mode** plants a real bug in the first attempt, so you can watch it get caught.")
    await d.click(page.locator("header label.toggle"))
    await d.wait(0.8)
    await d.scroll_to(page.locator(".run-bar"), block="center", pause=0.4)
    await d.click(page.locator("button.btn.primary.big"))
    await d.fast(4, "sandbox run")
    await page.wait_for_selector(".ev.fail", timeout=180_000)
    await d.normal()
    await d.caption("The verifier predicts the answer from the spec, never from the code. This run disagrees, so it **fails**.", hold=3.4)
    await d.caption(models_or(live, "**Muse Spark** gets the evidence and repairs the code…",
                              "The repairer gets the evidence and fixes the code…"))
    await d.fast(4, "repair and re-run")
    await page.wait_for_selector(".verdict-badge", timeout=240_000)
    await d.normal()
    await d.wait(0.4)
    await d.caption("…attempt 2 matches the prediction within shot noise: **verified**.", hold=3.4)
    await d.click(page.locator("header label.toggle"))  # demo mode off again
    await d.scroll_top()
    await d.click(page.locator("nav.steps button >> nth=0"))
    await d.wait(0.8)


async def discovery_story(d: Director) -> None:
    page, live = d.page, d.live
    await section(d, "Discover")
    disc = await show(d, "Discovery lab")
    await d.caption("**Discovery lab**: AI proposes, physics proves.", hold=1.8)
    await d.click(disc.locator(".chip-btn", has_text="GHZ on all 7"))
    await d.caption(models_or(live, "**Muse Spark** proposes circuit layouts for all 7 qubits of an IBM chip; an exact optimiser fits each one.",
                              "Circuit layouts for all 7 qubits of an IBM chip; an exact optimiser fits each one."))
    await d.click(disc.locator("button.btn.primary", has_text="Start discovery"))
    await d.fast(6, "the search")
    await page.wait_for_function(
        "() => [...document.querySelectorAll('.panel button.btn.primary')].some(b => b.textContent === 'Start discovery')",
        timeout=400_000)
    await d.normal()
    labels = await disc.locator(".disc-bar-label").all_inner_texts()
    cx = {t.split("·")[0].strip(): int(re.search(r"(\d+)\s*CNOT", t).group(1)) for t in labels if re.search(r"(\d+)\s*CNOT", t)}
    await d.scroll_to(disc.locator(".disc-bars"), block="center", pause=0.3)
    if "Discovered" in cx and "Textbook" in cx:
        await d.caption(f"Qiskit proves the winner exact: **{cx['Discovered']} CNOTs**, where the textbook circuit compiled "
                        f"onto the chip needs {cx['Textbook']}, and more of the state survives noise.", hold=4.6)
    else:
        await d.caption("Qiskit proves every winner exact, and exact noisy simulation decides which survives best.", hold=4.0)


async def estimator_story(d: Director) -> None:
    page = d.page
    est = await show(d, "When does quantum win?")
    await d.caption("**When does quantum win?** Surface-code estimates against the best classical route.")
    await d.click(est.locator(".chip-btn", has_text="Break RSA-2048"))
    await est.locator(".est-verdict").first.wait_for(timeout=120_000)
    await d.wait(3.0)
    await d.click(est.locator(".chip-btn", has_text="Crack a 64-bit key"))
    await d.wait(1.0)
    await d.caption("Checked against Gidney and Ekerå's RSA-2048 figure, and when classical wins, it says so.", hold=3.8)


async def hardware_story(d: Director) -> None:
    page = d.page
    await section(d, "Hardware & networks")
    pulse = await show(d, "Pulse lab")
    await pulse.locator(".obs-head").first.wait_for(timeout=120_000)
    await d.caption("Down to the microwave pulse: a three-level transmon, where DRAG keeps a fast X gate near 1e-4 error.", hold=3.8)
    dec = await show(d, "ML error-correction decoder")
    await dec.locator(".obs-head").first.wait_for(timeout=60_000)
    await d.caption("A learned surface-code decoder that reads both kinds of checks beats minimum-weight matching, beyond its error bars.", hold=4.2)
    d5 = dec.locator(".d5")
    if await d5.count():
        await d.caption(None)
        await d.scroll_to(d5, block="start", pause=0.6)
        await d.caption("And at distance 5, below threshold, the bigger code suppresses errors, as Google's Willow chip showed.", hold=4.0)
    sat = await show(d, "Satellite planner")
    await sat.locator(".sat-card").wait_for(timeout=120_000)
    await d.caption("Out to orbit, live: SpeQtre on today's real orbit from CelesTrak, every night pass over its ground stations…", hold=3.6)
    await d.scroll_to(sat.locator(".outlook"), block="center", pause=0.3)
    await d.caption("…weighed by the cloud forecast at each station. Micius re-entered in January 2026; its 2017 experiments replay on a model.", hold=4.4)


async def evidence_story(d: Director) -> None:
    await section(d, "Evidence")
    await show(d, "AI alone vs Q-Canvas")
    await d.caption("Why verify at all? Asked alone, the same model was exact on small circuits but on only 3 of 6 bigger ones, "
                    "once 43% off with full confidence.", hold=5.0)


async def record(base: str, out: Path) -> None:
    with urllib.request.urlopen(f"{base}/api/health", timeout=10) as r:
        health = json.load(r)
    live = health.get("mode") == "meta"
    print(f"backend mode: {health.get('mode_label')}")
    chips = ["Muse Spark", "Muse Wonder", "SAM 3.1", "Muse Image", "Muse Voice", "Qiskit + Aer"]
    note = "" if live else "Offline recording: model answers are recorded mock responses, labelled Mock in the app."

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        context = await browser.new_context(viewport={"width": VIEW_W, "height": VIEW_H},
                                            device_scale_factor=SCALE, color_scheme="dark")
        await context.add_init_script(OVERLAY_JS)
        page = await context.new_page()
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
        await page.goto(base)
        await page.wait_for_selector(".mission-goal")
        await page.evaluate("document.fonts.ready")
        d = Director(page, live)
        await page.evaluate("a => window.__demo.card(...a)", ["Q-Canvas", "", [], "", False])
        await d.wait(0.8)

        with tempfile.TemporaryDirectory() as tmp:
            rec = Recorder(page, Path(tmp))
            d.rec = rec
            await rec.start()
            await d.card("Q-Canvas", "Meta's models turn a quantum idea into a plan. Exact physics checks every number before you see it.",
                         chips, note, hold=4.6)
            await page.screenshot(path=str(out.with_suffix(".png")))
            await d.hide_card()
            for name, story in (("mission", mission_story), ("sketch", sketch_story), ("discovery", discovery_story),
                                ("estimator", estimator_story), ("hardware", hardware_story), ("evidence", evidence_story)):
                print(name, f"{rec._video_time(time.monotonic()):.1f} s", flush=True)
                await story(d)
            await d.caption(None)
            await d.card("Q-Canvas", "Sketch it, say it or photograph it. The AI proposes; exact physics has the last word.",
                         chips, "github.com/Dhruv-Deku/q-canvas · built during the Meta Global AI Developer Hackathon 2026", hold=5.0)
            await rec.stop()
            print(f"captured {len(rec.frames)} frames over {rec.t_end - rec.frames[0][0]:.1f} s "
                  f"({rec._video_time(rec.t_end):.1f} s after speed-ups); encoding…")
            rec.encode(out)
        await browser.close()
    if errors:
        print("console errors:", *errors, sep="\n  ")
    print(f"wrote {out} and {out.with_suffix('.png')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("base", nargs="?", default="http://127.0.0.1:8000")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "video" / "q-canvas-demo.mp4")
    args = ap.parse_args()
    asyncio.run(record(args.base.rstrip("/"), args.out.resolve()))


if __name__ == "__main__":
    main()
