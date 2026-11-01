# Q-Canvas demo video (1:56) and its voice-over

The video is recorded by a script that drives the real app, live on Meta's models, and lays captions over it:

```sh
.venv/Scripts/python scripts/record_demo.py --out docs/video/q-canvas-demo-v2.mp4   # backend on :8000 in live mode
```

It writes a 1080p MP4 and a thumbnail. Run it once to warm the response cache, then again for the take (the second
run is quicker and costs nothing). Speed-ups are labelled on screen ("3x speed · tools and model calls"), and
captions name a Meta model only when the backend reports live Meta mode.

## Adding your voice

The captions carry the story on their own, but a voice-over helps. On Windows, Clipchamp (built in) is enough:
import `docs/video/q-canvas-demo-v2.mp4`, record each block below over its scene (Record & create, then Audio),
export at 1080p. Speak at an easy pace: each block fits its scene at about 2.5 words per second.

| Time | Scene | Say |
| --- | --- | --- |
| 0:00-0:06 | Title card | "Q-Canvas. Meta's models turn a quantum idea into a plan, and exact physics checks every number." |
| 0:06-0:21 | Mission control: "Secure two cities" is launched; the plan graph lights up; the report appears | "One request: connect two cities with quantum-secure keys. Muse Spark plans a graph of exact tools, and independent steps run in parallel. Every step passes physics checks and a second simulator, and every number in the report is traced." |
| 0:21-0:49 | Sketch to code: the Bell-pair photo is read, demo mode plants a bug, the run fails, is repaired and verified | "It started with a pen sketch. SAM 3.1 finds every drawn part, and Muse Spark reads the photo into a spec, each gate linked to the box it came from. Demo mode plants a real bug. The verifier predicts the answer from the spec, never from the code, so the broken run fails. Muse Spark reads the evidence, repairs the code, and attempt two is verified." |
| 0:49-1:04 | Discovery lab: GHZ on 7 qubits of an IBM chip | "In the discovery lab, AI proposes and physics proves. Muse Spark suggests layouts for all seven qubits of an IBM chip, an exact optimiser fits them, and Qiskit proves the winner: six CNOTs, where the textbook needs ten." |
| 1:04-1:14 | When does quantum win: RSA-2048, then a 64-bit key | "When does quantum win? Surface-code estimates against the best classical route, checked against the published RSA-2048 figure. And when classical wins, it says so." |
| 1:14-1:41 | Pulse lab, the decoder at distance 3 and 5, the live satellite planner | "Down to the hardware: DRAG pulses on a three-level transmon. A learned decoder beats matching, and at distance five the bigger code suppresses errors almost six times per round, the effect Google's Willow chip showed. And out to orbit, live: SpeQtre on today's real orbit, every night pass over its ground stations, weighed by the cloud forecast." |
| 1:41-1:50 | AI alone vs Q-Canvas | "Why check at all? Alone, the same model was exact on small circuits, but on only three of six bigger ones, once 43% off with full confidence." |
| 1:50-1:56 | End card | "Q-Canvas. The AI proposes; exact physics has the last word." |

Scene times come from the recorder's own marks (mission 5.6 s, sketch 21.0 s, discovery 49.1 s, estimator 64.0 s,
hardware 74.3 s, evidence 101.5 s, total 115.9 s); a new take can shift them by a second or two, so check the
printout of the take you use.

## Backup plan

- If the network is slow or the key is missing, set `QCANVAS_MODEL_PROVIDER=mock`: everything runs offline and
  the title card says the model answers are recorded mocks. Say "offline mode" in the voice-over rather than
  implying live calls.
- The guided tour (header button, or `/#tour`) is a second way to show the same highlights live, in under two minutes.
