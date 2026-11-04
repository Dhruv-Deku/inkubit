# Inkubit demo videos and their voice-overs

Two cuts, both driven by a script through the real app, live on Meta's models, with no captions so a voice can go
over them:

| File | What it is |
| --- | --- |
| `docs/video/inkubit-demo-3min-voiceover.mp4` | **3-minute cut** for the submission (2:54): every core feature, including the Shor's algorithm lab and a whole paper reproduced |
| `docs/video/inkubit-demo-5min-voiceover.mp4` | **5-minute cut** for YouTube (4:55): the same story with 15 more panels (Rosetta, the AI scientist that learns, QAOA, H₂, BB84, bug hunt, IBM chip maps, pulse lab, code lab, distributed computer, proof sheet, observatory, proven illustrations) |

Each has a `.cues.txt` beside it: the time every scene starts and what its caption would say.

```sh
# backend on :8000 in live mode; RECORD_JPEG_QUALITY=85 halves the temporary disk space a take needs
.venv/Scripts/python scripts/record_demo.py --out take-3min.mp4 --no-captions
.venv/Scripts/python scripts/record_demo.py --out docs/video/inkubit-demo-5min-voiceover.mp4 --no-captions --long
# a take that ran long on a busy machine: shorten only its still stretches (cuts inside identical frames cannot be seen)
.venv/Scripts/python scripts/tighten_video.py take-3min.mp4 docs/video/inkubit-demo-3min-voiceover.mp4 --target 175
```

Every wait that is sped up is labelled on screen with its real factor ("8× speed · sandbox run", "8× speed ·
loading"), and every number on screen and in the script below is read from the recorded results (`facts()` in the
recorder), never typed in. Leave out `--no-captions` for a captioned cut. The YouTube thumbnail is
`docs/thumbnail.png`.

## 3-minute cut (submission): `docs/video/inkubit-demo-3min-voiceover.mp4` (2:54)

Start each line at its time. About 2.5 words a second; if you fall behind, drop words rather than slowing down.

| Time | On screen | Say |
| --- | --- | --- |
| 0:00 | Title card | "Inkubit: an AI quantum engineer that proves its work." |
| 0:05 | The pencil sketch rises into a 3D circuit | "A real pencil sketch. SAM 3.1 finds every drawn part, Muse Spark reads the circuit, and the verifier checks the run against an exact prediction." |
| 0:16 | Mission control: plan graph, report | "Mission control: one request becomes a plan of exact tools, run in parallel. Every step is checked twice, and every number in the report is traced." |
| 0:27 | Sketch to code: bug planted, caught, repaired | "From a photo of a pen sketch, Muse Spark reads a circuit, each gate linked to its box. Demo mode plants a real bug. The verifier predicts the answer from the circuit, never from the code, so this run fails. Muse Spark gets the evidence, repairs the code, and attempt two is verified." |
| 0:50 | Feed-forward error correction | "Feed-forward, the way real chips correct errors: a helper qubit measures the syndrome mid-circuit, is reset and reused, and only the flipped qubit is fixed. Predicted exactly over every branch." |
| 1:04 | Lecture checker | "The lecture checker uses all five Meta models in one run. Muse Voice tells the speakers apart, SAM 3.1 tracks the drawing through the video, Muse Spark writes out every claim, and exact physics catches both speakers' mistakes." |
| 1:21 | Discovery lab, then a whole paper | "In the discovery lab, AI proposes and physics proves: six CNOTs on an IBM chip, where the textbook needs ten. Give it a whole paper, and Muse Wonder finds the experiments for physics to check." |
| 1:37 | When does quantum win, then Shor's algorithm lab | "When does quantum win? Resource estimates against the best classical route, and an honest answer when classical wins. And Shor's algorithm itself: factoring fifteen, each reading turned into a period, on noisy qubits." |
| 1:52 | ML error-correction decoder | "Down to error correction: a learned surface-code decoder beats minimum-weight matching, the kind of decoder real quantum computers need." |
| 2:04 | Quantum internet on the 3D Earth | "And a quantum internet on the real Earth. Name the cities, and Muse Spark designs the network. Muse Wonder challenges it, learns from how physics scored its first try, and wins. Today's quantum satellites fly their real orbits, beaming entangled light to each city. Change any route, and physics answers at once." |
| 2:29 | Proof: AI alone vs Inkubit, the AI referee, real IBM hardware | "Why check at all? Alone, the model was exact on small circuits but on only three of six bigger ones. When Muse Wonder challenged it, debate fixed some answers and broke others. And on a real IBM quantum computer, a twin built from the chip's calibration predicted best." |
| 2:50 | End card | "Inkubit. The AI proposes; exact physics has the last word." |

## 5-minute cut (YouTube): `docs/video/inkubit-demo-5min-voiceover.mp4` (4:55)

| Time | On screen | Say |
| --- | --- | --- |
| 0:00 | Title card | "Inkubit: an AI quantum engineer that proves its work." |
| 0:05 | The pencil sketch rises into a 3D circuit | "It starts with a real pencil sketch. SAM 3.1 finds every drawn part, Muse Spark reads the circuit, and the verifier checks the run against an exact prediction." |
| 0:16 | Mission control | "Mission control: one request, typed, photographed or spoken, becomes a plan of exact tools that Muse Spark runs in parallel. Every step is checked twice, and every number in the report is traced back to the tool that computed it." |
| 0:31 | Sketch to code: bug planted, caught, repaired | "Where it started: a photo of a pen sketch. SAM 3.1 finds every drawn part and Muse Spark reads it into a circuit, each gate linked to the box it came from. Demo mode plants a real bug. The verifier predicts the answer from the circuit, never from the code, so this run fails. Muse Spark gets the evidence, repairs the code, and attempt two is verified." |
| 0:57 | Feed-forward error correction | "Feed-forward, the way real chips correct errors. A helper qubit measures the error syndrome halfway through, is reset and reused, and only the flipped qubit is fixed. It's predicted exactly over every branch, and it runs on IBM's chip as it is." |
| 1:14 | Quantum Rosetta | "The Quantum Rosetta translates any circuit between Dirac notation, OpenQASM, Qiskit, Cirq and more, both ways." |
| 1:21 | Lecture checker | "New: the lecture checker, with all five Meta models in one run. Muse Voice tells the speakers apart, SAM 3.1 tracks the drawing through the video, Muse Spark writes out every claim, and exact physics judges each one against the board at that moment. Muse Wonder writes corrected notes." |
| 1:40 | Discovery lab | "In the discovery lab, AI proposes and physics proves. Muse Spark suggests layouts for all seven qubits of an IBM chip, an optimiser fits them, and Qiskit proves the winner: six CNOTs, where the textbook needs ten." |
| 1:54 | An AI scientist that learns | "And it learns: shown what physics said about each round, Muse Spark's best circuit got shorter on every target." |
| 2:01 | Reproduce a whole paper | "Give it a whole paper: Muse Wonder found eight experiments in a hundred pages, and physics checked the numbers." |
| 2:08 | When does quantum win? | "When does quantum win? Surface-code estimates against the best classical route, checked against the published RSA-2048 figure. And when classical wins, it says so." |
| 2:18 | Shor's algorithm lab | "Shor's algorithm itself, factoring fifteen. Each measured reading becomes a period, step by step, and exact noisy simulation shows how many runs it really takes to get three times five." |
| 2:30 | Labs: QAOA, H₂, catch the spy, bug hunt | "The labs make it hands-on. QAOA seats feuding guests at two tables. The hydrogen molecule from first principles, where the classical approximation fails as the bond stretches. Catch a spy listening to quantum keys by the errors she leaves. And a bug hunt: find the wrong gate before Muse Spark does." |
| 2:57 | ML error-correction decoder | "Down to error correction: a learned surface-code decoder beats minimum-weight matching, beyond its error bars." |
| 3:05 | IBM Quantum, pulse lab, code lab, distributed computer | "Real hardware: IBM's chips mapped from their own calibration, with an advisor that places each circuit on the best qubits. Below the gates, a pulse lab. A code lab, where Muse Spark designs error-correcting codes and an exact checker proves them. And a distributed quantum computer: two chips joined by entanglement." |
| 3:32 | Quantum internet on the 3D Earth | "And a quantum internet on the real Earth. Name the cities, and Muse Spark designs the network: fiber, quantum repeaters or satellites. Muse Wonder challenges it, learns from how physics scored its first try, and wins. Today's quantum satellites fly their real orbits, beaming entangled light to each city on its night pass. Change any route, and physics answers at once." |
| 4:03 | Proof sheet, observatory, proven illustrations | "Every result is proven. The proof sheet runs eleven independent checks on every circuit in the gallery. The observatory sweeps the physics: fiber against satellites, Grover against noise. And every figure Muse Image draws is read back, and shown only if it's exactly the same circuit." |
| 4:28 | AI alone vs Inkubit, the AI referee, real IBM hardware | "Why check at all? Alone, the model was exact on small circuits but on only three of six bigger ones. When Muse Wonder challenged it, debate fixed some answers and broke others; only exact simulation knew which. And on a real IBM quantum computer, a twin built from the chip's calibration predicted all four circuits best." |
| 4:50 | End card | "Inkubit. The AI proposes; exact physics has the last word." |

## Adding your voice (Clipchamp, built into Windows)

1. Open Clipchamp, create a new video, import the mp4.
2. Record & create → Audio: record one block at a time and drag it to its start time.
3. Export at 1080p. Upload the 3-minute one for the hackathon and the 5-minute one to YouTube, both with `inkubit-thumbnail.png`.
