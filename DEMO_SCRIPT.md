# Inkubit demo video (2:58) and its voice-over

The video is recorded by a script that drives the real app, live on Meta's models, and lays captions over it:

```sh
.venv/Scripts/python scripts/record_demo.py --out docs/video/inkubit-demo-v5.mp4   # backend on :8000 in live mode
```

It writes a 1080p MP4 and a thumbnail. Run it once to warm the response cache, then again for the take (the second
run is quicker and costs nothing). Speed-ups are labelled on screen ("4x speed · sandbox run"), captions name a Meta
model only when the backend reports live Meta mode, and every number in a caption is read from the recorded results
(`facts()` in the script), never typed in. The YouTube thumbnail is `docs/thumbnail.png`.

## Adding your voice

The captions carry the story on their own, but a voice-over helps. On Windows, Clipchamp (built in) is enough:
import `docs/video/inkubit-demo-v5.mp4`, record each block below over its scene (Record & create, then Audio),
export at 1080p. Each block fits its scene at an easy pace, about 2.5 words per second.

| Time | Scene | Say |
| --- | --- | --- |
| 0:00-0:05 | Title card | "Inkubit: an AI quantum engineer that proves its work." |
| 0:05-0:17 | The opening scene: a real pencil sketch, its parts outlined, the circuit rising off the paper, the histogram and the verdict | "A real pencil sketch: SAM 3.1 finds the parts, Muse Spark reads the circuit, a noisy run fills the histogram, and the verifier checks it against an exact prediction." |
| 0:17-0:33 | Mission control: "Secure two cities" is launched; the plan graph lights up; the report appears | "One request: connect two cities with quantum-secure keys. Muse Spark plans a graph of exact tools, and independent steps run in parallel. Every step passes physics checks and a second simulator, and every number in the report is traced." |
| 0:33-1:04 | Sketch to code: the Bell-pair photo is read, demo mode plants a bug, the run fails, is repaired and verified | "It started with a pen sketch. SAM 3.1 finds every drawn part, and Muse Spark reads the photo into a spec, each gate linked to the box it came from. Demo mode plants a real bug. The verifier predicts the answer from the spec, never from the code, so the broken run fails. Muse Spark reads the evidence, repairs the code, and attempt two is verified." |
| 1:04-1:22 | Feed-forward: the bit-flip code with a reused helper qubit, its dashed links, the run, verified | "Feed-forward, the way real chips correct errors: a helper qubit measures the syndrome halfway, is reset and reused, and only the flipped qubit is fixed. Predicted exactly over every branch, and ready for IBM's chip as it is." |
| 1:22-1:38 | Discovery lab: GHZ on 7 qubits of an IBM chip | "In the discovery lab, AI proposes and physics proves. Muse Spark suggests layouts for all seven qubits of an IBM chip, an exact optimiser fits them, and Qiskit proves the winner: six CNOTs, where the textbook needs ten." |
| 1:38-1:47 | An AI scientist that learns | "And it learns. With exact physics' verdicts as feedback, its circuits got shorter on every target; without them, it never improved." |
| 1:47-1:58 | When does quantum win: RSA-2048, then a 64-bit key | "When does quantum win? Surface-code estimates against the best classical route, checked against the published RSA-2048 figure. And when classical wins, it says so." |
| 1:58-2:04 | Reproduce a whole paper | "It reads whole papers too: eight experiments from a hundred pages, every number re-checked." |
| 2:04-2:33 | Pulse lab, the decoder at distance 3 and 5, the code lab, the live satellite planner | "Down to the hardware: DRAG pulses on a transmon, a learned decoder that beats matching, and at distance five the bigger code suppresses errors. Muse Spark even designs error-correcting codes: for chips where phase flips dominate, it found one that needs nine of them to fail, three times the surface code. And out to orbit, live: SpeQtre on today's real orbit, under the cloud forecast." |
| 2:33-2:53 | AI alone vs Inkubit, the AI referee, a real IBM quantum computer | "Why check at all? Alone, the model was exact on small circuits but on only three of six bigger ones. When Muse Wonder challenged it, debate fixed some answers and broke others. And on a real IBM quantum computer, a digital twin from the chip's calibration predicted all four circuits best." |
| 2:53-2:58 | End card | "Inkubit. The AI proposes; exact physics has the last word." |

Scene times come from the recorder's own marks (opening scene 5.3 s, mission 16.9 s, sketch 32.9 s, feed-forward 63.9 s,
discovery 82.5 s, learning 98.2 s, estimator 107.4 s, paper 117.8 s, hardware 123.8 s, evidence 152.6 s, total 178 s); a new take can shift them by a
few seconds, so check the printout of the take you use.

## Backup plan

- If the network is slow or the key is missing, set `INKUBIT_MODEL_PROVIDER=mock`: everything runs offline and
  the title card says the model answers are recorded mocks. Say "offline mode" in the voice-over rather than
  implying live calls.
- The guided tour (header button, or `/#tour`) is a second way to show the same highlights live, in under two minutes.
