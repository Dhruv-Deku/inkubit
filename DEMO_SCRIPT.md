# Inkubit demo video (2:47) and its voice-over

Two cuts of the same recording, both driven by a script through the real app, live on Meta's models:

| File | What it is |
| --- | --- |
| `docs/video/inkubit-demo-v6-voiceover.mp4` | **No captions**, for your own voice-over (2:47) |
| `docs/video/inkubit-demo-v6.mp4` | The same scenes with captions, if you upload without a voice (2:47) |

Each has a `.cues.txt` beside it: the time every scene starts and what its caption says.

```sh
# backend on :8000 in live mode; RECORD_JPEG_QUALITY=85 halves the temporary disk space a take needs (about 0.7 GB)
.venv/Scripts/python scripts/record_demo.py --out docs/video/inkubit-demo-v6-voiceover.mp4 --no-captions
.venv/Scripts/python scripts/record_demo.py --out docs/video/inkubit-demo-v6.mp4
```

Speed-ups are labelled on screen ("4x speed · sandbox run"), and every number on screen and in the script below is
read from the recorded results (`facts()` in the recorder), never typed in. The YouTube thumbnail is
`docs/thumbnail.png`.

## Recording your voice-over

On Windows, Clipchamp (built in) is enough: import `docs/video/inkubit-demo-v6-voiceover.mp4`, then Record & create,
Audio, and read each block below over its scene. Each block fits its scene at an easy pace, about 2.5 words a second;
start each one at the time in the first column. If a block runs long, cut words rather than stretching the video, so
it stays under 3:00. Export at 1080p.

| Time | On screen | Say |
| --- | --- | --- |
| 0:00-0:05 | Title card | "Inkubit: an AI quantum engineer that proves its work." |
| 0:05-0:17 | The opening scene: a pencil sketch, its parts outlined, the circuit rising off the paper, the histogram and the verdict | "A real pencil sketch. SAM 3.1 finds every drawn part, Muse Spark reads the circuit, a noisy run fills the histogram, and the verifier checks it against an exact prediction." |
| 0:17-0:32 | Mission control: "Secure two cities" is launched, the plan graph lights up, the report appears | "Mission control: one request becomes a plan of exact tools that Muse Spark runs in parallel. Every step is checked twice, and every number in the report is traced to the tool behind it." |
| 0:32-0:59 | Sketch to code: the Bell-pair photo is read, demo mode plants a bug, the run fails, is repaired and verified | "Where it started: a photo of a pen sketch. SAM 3.1 finds every drawn part and Muse Spark reads it into a circuit, each gate linked to its box. Demo mode plants a real bug. The verifier predicts the answer from the circuit, never from the code, so this run fails. Muse Spark gets the evidence, repairs the code, and attempt two is verified." |
| 0:59-1:15 | Feed-forward: the bit-flip code with a reused helper qubit and its dashed links, run and verified | "Feed-forward, the way real chips correct errors. A helper qubit measures the error syndrome halfway through, is reset and reused, and only the flipped qubit is fixed. Predicted exactly over every branch, and ready for IBM's chip as it is." |
| 1:15-1:32 | Lecture checker: a filmed lecture plays, the wrong claims are listed, the tracked board, the notes and the proven figure | "New: the lecture checker, with all five Meta models in one run. Muse Voice tells the speakers apart, SAM 3.1 tracks the drawing through the video, Muse Spark writes out every claim, and exact physics judges each one against the board at that moment. Both speakers' mistakes are caught." |
| 1:32-1:47 | Discovery lab: GHZ on all 7 qubits of an IBM chip | "In the discovery lab, AI proposes and physics proves. Muse Spark suggests layouts for all seven qubits of an IBM chip, an exact optimiser fits them, and Qiskit proves the winner: six CNOTs, where the textbook needs ten." |
| 1:47-1:57 | When does quantum win: RSA-2048, then a 64-bit key | "When does quantum win? Surface-code estimates against the best classical route, checked against the published RSA-2048 figure. And when classical wins, it says so." |
| 1:57-2:22 | Pulse lab, the learned decoder, the code lab, the live satellite planner | "Down to the hardware: DRAG pulses keep a fast X gate near one error in ten thousand, and a learned decoder beats minimum-weight matching. Muse Spark even designs error-correcting codes: for chips where phase flips dominate, one that needs nine of them to fail, three times the surface code. And out to orbit: today's real quantum-key satellite, every night pass weighed by the cloud forecast." |
| 2:22-2:42 | AI alone vs Inkubit, the AI referee, a real IBM quantum computer | "Why check at all? Alone, the model was exact on small circuits but on only three of six bigger ones. When Muse Wonder challenged it, debate fixed some answers and broke others. And on a real IBM quantum computer, a twin built from the chip's calibration predicted all four circuits best." |
| 2:42-2:47 | End card | "Inkubit. The AI proposes; exact physics has the last word." |

Scene times come from the voice-over take's own marks (opening scene 5.2 s, mission 16.7 s, sketch 31.9 s, feed-forward
58.3 s, lecture 75.0 s, discovery 91.9 s, estimator 106.7 s, hardware 116.8 s, evidence 141.1 s, total 167 s). A new
take can shift them by a second; check the `.cues.txt` of the take you use.

## Backup plan

- If the network is slow or the key is missing, set `INKUBIT_MODEL_PROVIDER=mock`: everything runs offline and the
  title card says the model answers are recorded mocks. Say "offline mode" in the voice-over rather than implying
  live calls.
- The guided tour (header button, or `/#tour`) is a second way to show the same highlights live, in under two minutes.
