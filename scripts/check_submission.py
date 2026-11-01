"""Pre-submission check: everything the hackathon form and the judges need, checked against the repo itself.

    .venv/Scripts/python scripts/check_submission.py

Prints one line per item: OK, TODO (something only you can do, with how) or FAIL (something in the repo is wrong).
Nothing is changed or sent anywhere; it reads the repo, runs the claims test and asks GitHub (gh) about the repo.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEADLINE = datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc)  # Nov 4, 9:00 PM ET
VIDEO = ROOT / "docs" / "video" / "q-canvas-demo-v2.mp4"
PY = sys.executable
rows: list[tuple[str, str, str]] = []


def add(status: str, item: str, note: str = "") -> None:
    rows.append((status, item, note))


def run(cmd: list[str], cwd: Path = ROOT, timeout: int = 600) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.TimeoutExpired) as err:
        return 1, str(err)


def main() -> None:
    sub = (ROOT / "SUBMISSION.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    code, out = run(["gh", "repo", "view", "Dhruv-Deku/q-canvas", "--json", "visibility", "-q", ".visibility"])
    vis = out.strip()
    add("OK" if vis == "PUBLIC" else "TODO", "Repository is public (the rules require it)",
        "" if vis == "PUBLIC" else f"now {vis or 'unknown'}: gh repo edit Dhruv-Deku/q-canvas --visibility public --accept-visibility-change-consequences")

    add("TODO" if "<YouTube / Loom link>" in sub else "OK", "Video link in SUBMISSION.md",
        "upload docs/video/q-canvas-demo-v2.mp4 (unlisted is fine), thumbnail docs/thumbnail.png, paste the link" if "<YouTube" in sub else "")
    add("TODO" if "<Hugging Face Space link>" in sub else "OK", "Hosted demo link in SUBMISSION.md",
        "hf auth login, then scripts/deploy_space.py <user>/q-canvas [--with-key]; or delete the 'Try it' part" if "<Hugging" in sub else "")
    hw = ROOT / "examples" / "hardware_runs.json"
    add("OK" if hw.exists() else "TODO", "Real IBM hardware run (optional, the strongest credibility item)",
        "" if hw.exists() else "IBM_QUANTUM_TOKEN=... in .env, then scripts/hardware_check.py")

    if VIDEO.exists():
        import imageio_ffmpeg

        _, info = run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(VIDEO)])
        m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", info)
        secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None
        add("OK" if secs and secs <= 180 else "FAIL", "Demo video is at most 3 minutes",
            f"{secs:.0f} s, {VIDEO.stat().st_size / 1e6:.0f} MB" if secs else "could not read its length")
    else:
        add("FAIL", "Demo video exists", f"record it: scripts/record_demo.py --out {VIDEO.relative_to(ROOT)}")

    thumb = ROOT / "docs" / "thumbnail.png"
    if thumb.exists():
        from PIL import Image

        size = Image.open(thumb).size
        add("OK" if size == (1280, 720) else "FAIL", "YouTube thumbnail 1280x720", f"{size[0]}x{size[1]}")
    else:
        add("FAIL", "YouTube thumbnail", "docs/thumbnail.png is missing")
    gif = ROOT / "docs" / "screenshots" / "mission-control.gif"
    add("OK" if gif.exists() and gif.stat().st_size < 10e6 and "mission-control.gif" in readme else "FAIL",
        "README opens with the mission-control GIF", f"{gif.stat().st_size / 1e6:.1f} MB" if gif.exists() else "missing")

    code, out = run([PY, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"], cwd=ROOT / "backend")
    m = re.search(r"(\d+) tests? collected", out)
    n = int(m.group(1)) if m else None
    quoted = {name: sorted(set(re.findall(r"(\d{3}) (?:offline |backend )*tests", (ROOT / name).read_text(encoding="utf-8"))))
              for name in ("README.md", "SUBMISSION.md", "PROGRESS.md")}
    stale = {k: v for k, v in quoted.items() if any(int(x) != n for x in v)}
    add("OK" if n and not stale else "FAIL", "Test counts quoted in the docs match the suite",
        f"{n} collected" + (f"; stale: {stale}" if stale else ""))

    code, out = run([PY, "-m", "pytest", "tests/test_claims.py", "-q", "-p", "no:cacheprovider"], cwd=ROOT / "backend")
    last = out.strip().splitlines()[-1] if out.strip() else ""
    add("OK" if code == 0 else "FAIL", "Every number quoted in README and SUBMISSION matches its data", last)

    env = ROOT / ".env"
    key = ""
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("META_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    if key:
        _, hist = run(["git", "log", "--all", "-p", "--no-color"], timeout=300)
        add("OK" if key not in hist else "FAIL", "The Meta key appears nowhere in git history", "")
    _, tracked = run(["git", "ls-files"])
    add("OK" if not any(re.search(r"(^|/)\.env$", f) for f in tracked.splitlines()) else "FAIL", ".env is not tracked", "")

    _, runs = run(["gh", "run", "list", "--limit", "1", "--json", "conclusion,status,headSha"])
    try:
        last_run = json.loads(runs)[0]
        _, head = run(["git", "rev-parse", "HEAD"])
        same = last_run["headSha"] == head.strip()
        ok = last_run.get("conclusion") == "success" and same
        add("OK" if ok else "TODO", "CI passed on the latest commit",
            "" if ok else f"latest run: {last_run.get('status')} {last_run.get('conclusion') or ''}{'' if same else ' (not on HEAD: push first)'}")
    except (ValueError, IndexError, KeyError):
        add("TODO", "CI passed on the latest commit", "could not ask GitHub (gh)")

    _, status = run(["git", "status", "--porcelain", "--untracked-files=no"])
    add("OK" if not status.strip() else "TODO", "Everything is committed", status.strip().replace("\n", "; ")[:200])
    _, ts = run(["git", "log", "-1", "--format=%cI"])
    when = datetime.fromisoformat(ts.strip()) if ts.strip() else None
    add("OK" if when and when < DEADLINE else "FAIL", "Last commit is before the deadline (Nov 4, 9 PM ET)", ts.strip())
    add("OK" if (ROOT / "LICENSE").exists() and "Built during the hackathon" in readme else "FAIL",
        "MIT license and the 'built during the hackathon' table", "")

    width = max(len(i) for _, i, _ in rows)
    for status_, item, note in rows:
        print(f"{status_:4}  {item.ljust(width)}  {note}")
    todo, fail = sum(s == "TODO" for s, _, _ in rows), sum(s == "FAIL" for s, _, _ in rows)
    print(f"\n{len(rows) - todo - fail} OK, {todo} to do, {fail} failing")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
