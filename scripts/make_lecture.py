"""Make the sample lecture for the lecture checker: a pen sketch drawn step by step while two voices explain it.

A teacher (Windows' "David" voice) builds a three-qubit GHZ state on paper and a student ("Zira") asks about it.
Two statements are wrong on purpose, one from each speaker: the student thinks the third qubit is already entangled
before it is wired in, and the teacher calls the finished state a W state. Everything else they say is true.

Writes examples/lecture/lecture.mp4 (1280x720, H.264 + AAC) and examples/lecture/lecture.json, the script's own
record: who said what and when, when each drawn element appeared and where, the circuit, and the claims written out
formally. Offline mode replays that record in place of the models; live mode never reads it. Run from the repo root
on Windows:

    .venv/Scripts/python scripts/make_lecture.py
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import imageio_ffmpeg
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_sketches import INK, PAPER, Sketch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "examples" / "lecture"
W, H = 1280, 720
RATE = 16000
SEED = 41
WIRES = (230, 380, 530)
VOICES = {"Teacher": "Microsoft David Desktop", "Student": "Microsoft Zira Desktop"}

# (speaker, text, the element drawn just before this turn or None)
TURNS = [
    ("Teacher", "Today we build an entangled state on three qubits. Three wires, all starting at zero.", "wires"),
    ("Teacher", "A Hadamard on the first qubit. Now it reads zero or one, each half of the time.", "h"),
    ("Teacher", "A CNOT from the first qubit to the second. Now these two are entangled: we only ever see zero zero, "
                "or one one.", "cx01"),
    ("Student", "And the third qubit is entangled with them too, right?", None),
    ("Teacher", "Not yet. The third qubit is still just zero.", None),
    ("Teacher", "One more CNOT, from the second qubit to the third. Now all three are entangled. This is the W state: "
                "exactly one of the three qubits reads one.", "cx12"),
    ("Teacher", "When we measure, we get zero zero zero, or one one one, each with probability one half.", "meters"),
]

# The claims, written out the way the checker states them (qubits listed; an outcome's i-th bit is qubits[i]).
CLAIMS = [
    {"turn": 1, "quote": "Now it reads zero or one, each half of the time.", "kind": "probability", "qubits": [0],
     "outcome": "1", "value": 0.5},
    {"turn": 2, "quote": "Now these two are entangled", "kind": "entangled", "qubits": [0, 1]},
    {"turn": 2, "quote": "we only ever see zero zero, or one one", "kind": "outcomes", "qubits": [0, 1],
     "outcomes": ["00", "11"]},
    {"turn": 3, "quote": "And the third qubit is entangled with them too, right?", "kind": "entangled", "qubits": [2]},
    {"turn": 4, "quote": "The third qubit is still just zero.", "kind": "probability", "qubits": [2], "outcome": "0",
     "value": 1.0},
    {"turn": 5, "quote": "Now all three are entangled.", "kind": "entangled", "qubits": [0, 1, 2]},
    {"turn": 5, "quote": "This is the W state", "kind": "state", "qubits": [0, 1, 2], "state": "W"},
    {"turn": 5, "quote": "exactly one of the three qubits reads one", "kind": "outcomes", "qubits": [0, 1, 2],
     "outcomes": ["100", "010", "001"]},
    {"turn": 6, "quote": "we get zero zero zero, or one one one, each with probability one half", "kind": "outcomes",
     "qubits": [0, 1, 2], "outcomes": ["000", "111"]},
    {"turn": 6, "quote": "each with probability one half", "kind": "probability", "qubits": [0, 1, 2],
     "outcome": "000", "value": 0.5},
]


def speak_all(tmp: Path) -> list[Path]:
    """One 16 kHz mono WAV per turn, from the Windows speech synthesizer."""
    lines = ["Add-Type -AssemblyName System.Speech",
             "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
             "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)"]
    paths = []
    for i, (who, text, _) in enumerate(TURNS):
        path = tmp / f"turn{i}.wav"
        paths.append(path)
        safe = text.replace("'", "''")
        lines += ["$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
                  f"$s.SelectVoice('{VOICES[who]}')", "$s.Rate = 2",
                  f"$s.SetOutputToWaveFile('{path}', $fmt)", f"$s.Speak('{safe}')", "$s.Dispose()"]
    script = tmp / "speak.ps1"
    script.write_text("\n".join(lines), encoding="utf-8")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], check=True)
    return paths


def frames_of(path: Path) -> bytes:
    with wave.open(str(path)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, RATE), path
        return w.readframes(w.getnframes())


def timeline(clips: list[bytes]) -> tuple[list[dict], dict[str, float], bytes]:
    """Place the turns with pauses (longer after something new is drawn); return turns, draw times and the audio."""
    t, audio, turns, drawn = 0.8, bytearray(), [], {}
    for i, ((who, text, element), pcm) in enumerate(zip(TURNS, clips)):
        if element:
            drawn[element] = max(0.3, t - 0.9) if element != "wires" else 0.3
            t += 0.0 if element == "wires" else 0.6
        start = t
        audio += b"\x00\x00" * (int(start * RATE) - len(audio) // 2)
        audio += pcm
        end = start + len(pcm) / 2 / RATE
        turns.append({"index": i, "speaker": who, "voice": VOICES[who], "start": round(start, 2), "end": round(end, 2),
                      "text": text})
        t = end + (0.5 if i + 1 < len(TURNS) and TURNS[i + 1][2] is None else 1.3)
    total = t + 1.2
    audio += b"\x00\x00" * (int(total * RATE) - len(audio) // 2)
    return turns, drawn, bytes(audio)


def _box(sk: Sketch, x1, y1, x2, y2) -> None:
    sk.d.rectangle((x1, y1, x2, y2), fill=PAPER)
    sk.rect(x1, y1, x2, y2, 5)


def _cx(sk: Sketch, x: float, c: int, t: int) -> None:
    yc, yt = WIRES[c], WIRES[t]
    sk.dot(x, yc, 13)
    sk.line((x, yc), (x, yt + 36), 5)
    sk.circle(x, yt, 36, 5)
    sk.line((x - 36, yt), (x + 36, yt), 4)


def _meter(sk: Sketch, x: float, y: float) -> None:
    import math

    _box(sk, x, y - 44, x + 108, y + 44)
    arc = [(x + 54 + 34 * math.cos(math.pi + math.pi * k / 16), y + 22 + 34 * math.sin(math.pi + math.pi * k / 16))
           for k in range(17)]
    sk.d.line(sk._jitter_path(arc, 1.0), fill=INK, width=4, joint="curve")
    sk.line((x + 54, y + 22), (x + 82, y - 22), 4)


# Drawing order, each element's segments (concept, bbox) and the operation it is.
ELEMENTS = ["wires", "h", "cx01", "cx12", "meters"]
SEGMENTS = {
    "h": [("gate box", (250, 180, 350, 280))],
    "cx01": [("dot", (505, 215, 535, 245)), ("circle", (481, 341, 559, 419))],
    "cx12": [("dot", (725, 365, 755, 395)), ("circle", (701, 491, 779, 569))],
    "meters": [("meter", (960, y - 44, 1068, y + 44)) for y in WIRES],
}


def render(upto: int) -> Image.Image:
    sk = Sketch(W, H, SEED)
    sk.text((90, 40), "Entanglement, three qubits", 52)
    for q, y in enumerate(WIRES):
        sk.text((88, y - 30), f"q{q}", 44)
        sk.line((170, y), (1130, y + sk.rng.uniform(-2, 2)), 5)
    if upto >= 1:
        _box(sk, 250, 180, 350, 280)
        sk.text((282, 196), "H", 56)
    if upto >= 2:
        _cx(sk, 520, 0, 1)
    if upto >= 3:
        _cx(sk, 740, 1, 2)
    if upto >= 4:
        for y in WIRES:
            _meter(sk, 960, y)
    return Image.open(io.BytesIO(sk.finish())).convert("RGB")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        turns, drawn, audio = timeline([frames_of(p) for p in speak_all(tmp)])
        total = len(audio) / 2 / RATE
        with wave.open(str(tmp / "lecture.wav"), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(RATE)
            w.writeframes(audio)
        times = [drawn[e] for e in ELEMENTS]
        concat = []
        for k, e in enumerate(ELEMENTS):
            render(k).save(tmp / f"stage{k}.png")
            end = times[k + 1] if k + 1 < len(ELEMENTS) else total
            start = 0.0 if k == 0 else times[k]
            concat += [f"file 'stage{k}.png'", f"duration {end - start:.3f}"]
        concat.append(f"file 'stage{len(ELEMENTS) - 1}.png'")
        (tmp / "frames.txt").write_text("\n".join(concat), encoding="utf-8")
        video = OUT / "lecture.mp4"
        subprocess.run([ff, "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "frames.txt"),
                        "-i", str(tmp / "lecture.wav"), "-vf", "fps=10,format=yuv420p", "-c:v", "libx264", "-crf", "24",
                        "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(video)],
                       check=True, cwd=tmp)
    ops = [{"gate": "H", "targets": [0], "element": "h"},
           {"gate": "CX", "controls": [0], "targets": [1], "element": "cx01"},
           {"gate": "CX", "controls": [1], "targets": [2], "element": "cx12"}]
    record = {
        "title": "Entanglement, three qubits",
        "made_by": "scripts/make_lecture.py (pen sketch drawn in stages; Windows speech voices David and Zira)",
        "video": "lecture.mp4", "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
        "duration": round(total, 2), "width": W, "height": H,
        "turns": turns,
        "elements": [{"id": e, "appears": round(drawn[e], 2),
                      "segments": [{"concept": c, "bbox": list(b)} for c, b in SEGMENTS.get(e, [])]} for e in ELEMENTS],
        "spec": {"kind": "circuit", "version": "1.0", "num_qubits": 3, "num_clbits": 3,
                 "operations": [{k: v for k, v in op.items() if k != "element"} for op in ops],
                 "measurements": [{"qubit": q, "clbit": q} for q in range(3)],
                 "metadata": {"title": "Entanglement, three qubits", "origin": "image"}},
        "op_elements": [op["element"] for op in ops],
        "claims": CLAIMS,
    }
    (OUT / "lecture.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{video} {video.stat().st_size / 1e6:.2f} MB, {total:.1f} s; turns at",
          [t["start"] for t in turns], "drawn at", {e: round(drawn[e], 1) for e in ELEMENTS})


if __name__ == "__main__":
    main()
