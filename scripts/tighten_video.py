"""Shorten a demo take to a target length by trimming only its still stretches, then retime its cue sheet.

Frames inside a still stretch are identical, so a cut there cannot be seen: every motion in the take is kept, and
only the waiting is shortened. Each still stretch keeps at least --keep seconds; the opening and closing cards are
never touched. Usage: tighten_video.py IN.mp4 OUT.mp4 --target 175
"""

import argparse
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()


def stills(path: Path, noise: float = 0.0015, min_s: float = 0.6) -> tuple[list[tuple[float, float]], float]:
    out = subprocess.run([FF, "-hide_banner", "-i", str(path), "-vf", f"scale=480:-1,freezedetect=n={noise}:d={min_s}", "-an", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    total = float(re.search(r"Duration: (\d+):(\d+):([\d.]+)", out).group(3)) + 60 * int(re.search(r"Duration: (\d+):(\d+)", out).group(2))
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", out)]
    return [(s, ends[i] if i < len(ends) else total) for i, s in enumerate(starts)], total


def plan(spans: list[tuple[float, float]], total: float, target: float, head: float, tail: float) -> tuple[list[tuple[float, float]], float]:
    """The longest still each stretch may keep so that the take lands on the target; returns the cuts and that length."""
    inner = [(s, e) for s, e in spans if s >= head and e <= total - tail]
    need = total - target
    lo, hi = 0.8, max((e - s for s, e in inner), default=0.8)
    for _ in range(40):  # bisect on the longest still kept
        mid = (lo + hi) / 2
        if sum(max(0.0, e - s - mid) for s, e in inner) > need:
            lo = mid
        else:
            hi = mid
    keep = lo
    cuts = [(s + keep / 2, e - keep / 2) for s, e in inner if e - s > keep]  # cut the middle: both ends of each still stay
    return cuts, keep


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--target", type=float, required=True, help="length in seconds")
    ap.add_argument("--head", type=float, default=5.0, help="seconds at the start never touched (the title card)")
    ap.add_argument("--tail", type=float, default=4.5, help="seconds at the end never touched (the end card)")
    a = ap.parse_args()
    spans, total = stills(a.src)
    if total <= a.target:
        raise SystemExit(f"already {total:.1f} s")
    cuts, keep = plan(spans, total, a.target, a.head, a.tail)
    if keep < 1.2:
        raise SystemExit(f"would leave stills of only {keep:.2f} s; record a faster take instead")
    keep_expr = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in cuts)
    vf = f"select='not({keep_expr})',setpts=N/FRAME_RATE/TB"
    script = a.out.with_suffix(".filter.txt")
    script.write_text(vf, encoding="utf-8")
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(a.src), "-filter_script:v", str(script), "-an", "-r", "30", "-c:v", "libx264",
                    "-preset", "slow", "-crf", "18", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(a.out)], check=True)
    script.unlink()
    cues = a.src.with_suffix(".cues.txt")
    if cues.exists():
        lines = []
        for line in cues.read_text(encoding="utf-8").splitlines():
            m = re.match(r"(\d+):([\d.]+)\s+(.*)", line)
            if not m:
                continue
            t = int(m.group(1)) * 60 + float(m.group(2))
            t2 = t - sum(min(e, t) - s for s, e in cuts if s < t)
            lines.append(f"{int(t2 // 60)}:{t2 % 60:04.1f}  {m.group(3)}")
        a.out.with_suffix(".cues.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{total:.1f} s -> {total - sum(e - s for s, e in cuts):.1f} s: {len(cuts)} still stretches trimmed to {keep:.2f} s each")


if __name__ == "__main__":
    main()
