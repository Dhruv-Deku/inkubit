<img src="docs/brand/inkubit-mark.svg" width="72" alt="Inkubit logo: a drop of ink in a satellite's orbit, carrying an entangled photon">

# Inkubit

[![tests](https://github.com/Dhruv-Deku/inkubit/actions/workflows/ci.yml/badge.svg)](https://github.com/Dhruv-Deku/inkubit/actions/workflows/ci.yml)
· MIT · built during the Meta Global AI Developer Hackathon 2026 (Push the Frontier)

**Sketch it, say it or photograph it: Meta's models turn a quantum idea into a plan, and exact physics checks every
number before you see it.**

Inkubit is a quantum lab where the AI never gets the last word. Muse Spark, Muse Wonder, SAM 3.1, Muse Image and
Muse Voice read sketches, photos, papers, lectures and speech, plan multi-step experiments and propose circuits and
networks; exact simulation, independent re-runs and physics invariants verify every result, and every number in every
AI answer is traced back to a tool that computed it.

![A quantum internet on a 3D Earth: Muse Spark designs a key network between Delhi, Mumbai and London, Muse Wonder challenges it and wins its second round, exact physics and an exhaustive search agree; the real satellites fly overhead and a route is edited by hand](docs/screenshots/quantum-internet.gif)

<sub>Above: the quantum internet on a 3D Earth, recorded live on Meta's models. The real Sun's day and night,
SpeQtre and QUBE-II on today's orbits, gold pairs of entangled photons on every route.</sub>

### See it work

Every clip is recorded from the running app, live on Meta's models (sped-up stretches are labelled on screen).

<table>
<tr>
<td width="50%"><b>Mission control</b><br><sub>One request becomes a plan of exact tools that runs in parallel; every number in the report is traced.</sub><br><img src="docs/screenshots/mission-control.gif" alt="The opening scene replays the pipeline in 3D on a real pencil sketch; then Mission control: one request becomes a plan of exact tools that runs in parallel, every step verified and every number in the report traced"></td>
<td width="50%"><b>Sketch to verified code</b><br><sub>SAM 3.1 finds every drawn part, Muse Spark reads it; a planted bug fails, is repaired and verified.</sub><br><img src="docs/screenshots/sketch-to-verified.gif" alt="A photo of a pen sketch is read into a circuit, demo mode plants a bug, the verifier fails it, Muse Spark repairs the code and attempt two is verified"></td>
</tr>
<tr>
<td><b>Lecture checker</b><br><sub>All five Meta models in one run: every spoken claim judged against the board as it was.</sub><br><img src="docs/screenshots/lecture-checker.gif" alt="Lecture checker: the wrong claims from a filmed lecture, the tracked board, corrected notes and a proven figure"></td>
<td><b>Feed-forward error correction</b><br><sub>A helper qubit is measured mid-circuit, reset and reused; only the flipped qubit is fixed.</sub><br><img src="docs/screenshots/feed-forward.gif" alt="The bit-flip code with a reused helper qubit and feed-forward, run and verified over every branch"></td>
</tr>
<tr>
<td><b>Discovery lab</b><br><sub>Muse Spark proposes layouts, an exact optimiser fits them, Qiskit proves the winner: 6 CNOTs against 10.</sub><br><img src="docs/screenshots/discovery-lab.gif" alt="Discovery lab: GHZ on all 7 qubits of an IBM heavy-hex chip in 6 CNOTs, where the textbook circuit needs 10"></td>
<td><b>When does quantum win?</b><br><sub>Surface-code estimates against the best classical route, checked against the published RSA-2048 figure.</sub><br><img src="docs/screenshots/when-quantum-wins.gif" alt="When does quantum win: RSA-2048, then a 64-bit key where classical wins"></td>
</tr>
<tr>
<td colspan="2"><b>Why verify at all</b><br><sub>The model alone was exact on small circuits but on only 3 of 6 bigger ones; debate with Muse Wonder fixed some answers and broke others; on a real IBM quantum computer a twin from the chip's calibration predicted best.</sub><br><img src="docs/screenshots/why-verify.gif" alt="The proof sheet, AI alone vs Inkubit, the AI referee and the real IBM hardware runs"></td>
</tr>
</table>

### Five Meta models, each with a job

| Model | What it does in Inkubit | What checks it |
| --- | --- | --- |
| **Muse Spark** (`muse-spark-1.3`) | Reads sketches, photos and figures into circuits; plans missions; designs circuits, codes and quantum networks; repairs failing code; writes reports | Exact simulation, a second simulator, physics invariants; every report number traced to a tool |
| **Muse Wonder** (`muse-wonder-1.0`) | Challenges Muse Spark (the AI referee, the network designs); finds the experiments in a whole paper; writes corrected lecture notes | The same exact physics decides who was right |
| **SAM 3.1** (`sam-3.1`) | Finds every drawn gate in a photo; tracks each drawn part through a lecture video, frame by frame | Each gate is linked back to the box it was read from |
| **Muse Image** (`muse-image-1.0`) | Draws figures, and corrects them when the read-back names a mistake | Read back by SAM 3.1 and Muse Spark; shown only if it is exactly the same circuit |
| **Muse Voice** (`muse-voice-transcribe-1.0`) | Speech in everywhere; tells the speakers in a lecture apart | Each claim is tied to who said it and when |

### Results you can check in the app

| | Measured result |
| --- | --- |
| **A real IBM quantum computer** | The discovery lab's GHZ circuit for 7 qubits (Muse Spark's own layout) ran on IBM's ibm_fez next to the textbook circuit, on the same seven qubits: GHZ fidelity **0.814 against 0.795** (3.2 standard errors), both certifying genuine 7-qubit entanglement; for W and Dicke states the discovered circuits used 8 two-qubit gates against 17 and tied within shot noise. On four smaller circuits a digital twin from the chip's calibration beat the noiseless odds and the generic preset on 4 of 4 (distance 0.021 to 0.038), and Inkubit's new **calibrated preset**, built from the chip's median calibration, came closer still (0.013 to 0.027): [docs/DISCOVERY_HARDWARE.md](docs/DISCOVERY_HARDWARE.md), [docs/HARDWARE.md](docs/HARDWARE.md) |
| **IBM Quantum, in the app** | Live calibration maps of 3 IBM Heron chips, a placement advisor that scores every way to put a circuit on a chip, and **Run on IBM Quantum** from the editor. On ibm_fez the advisor's best, median and worst placements of the same GHZ-5 circuit measured **0.894, 0.814 and 0.285**, exactly its order; teleportation with real mid-circuit measurement and feed-forward reached an average fidelity of **0.924 ± 0.002** against the classical limit of 0.667 (0.499 without the corrections): [docs/IBM_EXPERIMENTS.md](docs/IBM_EXPERIMENTS.md) |
| **The proof sheet** | 11 independent checks of 9 kinds on any circuit in about eight seconds (two simulators of each kind, a physical density matrix, translation validation of Qiskit's compiler, OpenQASM read-back, a G-test, the generated code in the sandbox, metamorphic tests); over the whole gallery **299 passed and 0 failed**, and its first run found a real export bug: [docs/PROOFSHEET.md](docs/PROOFSHEET.md) |
| **27 algorithms in 8 categories** | Each checked against its known answer in a test: the newest are a bit-flip code that measures its syndrome with one reused helper qubit and fixes only the qubit the two syndrome bits point to, and teleportation with real feed-forward (X and Z only when the measured bits say so), then quantum counting, HHL (A⁻¹b in the ratio 9 : 1), a Fourier-space adder, hidden shift, Shor's nine-qubit code, Grover with two marked items and two nonlocal games (CHSH won cos²(π/8) of the time; the GHZ game won every time) |
| **Mission control** | A whole problem in words, a photo or speech becomes a plan of exact tools that runs live in parallel; in a 30-mission live benchmark every mission finished, all 68 steps were verified (one repaired by the model), 204 of 209 report numbers were traced to a tool result, median 15 s: [docs/MISSIONS.md](docs/MISSIONS.md) |
| **Quantum internet on a 3D Earth** | Name the cities (typed or spoken) and Muse Spark designs a key network: fiber, quantum-memory repeaters, or the quantum-key satellites in orbit today (SpeQtre and QUBE-II on their real orbits). Exact physics scores every route, Muse Wonder challenges the design with those numbers and learns from a second round, and an exhaustive search shows the best possible. On a globe you can grab: the real Sun's day and night, entangled photon pairs flying along each route, live satellites beaming to cities on their night passes, and every route editable with the physics answering at once |
| **Lecture checker** | A filmed explanation in, every spoken claim checked. On the sample lecture (a pen sketch drawn in stages while a teacher and a student talk), Muse Voice tells the two speakers apart, SAM 3.1 tracks each drawn part through the video (the two CNOTs appear at 13.5 s and 30.0 s), Muse Spark writes out 12 claims, and exact simulation finds the 3 wrong ones, one from each speaker, each judged against the board as it was when it was said. All five Meta models in one run of about a minute |
| **Proven illustrations** | A figure Muse Image draws is read back by SAM 3.1 and Muse Spark and must be exactly the same circuit before it is shown on its own. Over 20 small gallery circuits Muse Image was right first time on 5 and right after one correction on 1; the other 14 never matched within two corrections (gates on the wrong wires, missing or extra gates), so the exact drawing is shown instead |
| **Discovery lab** | Muse Spark proposes, physics proves: a GHZ state on all 7 qubits of an IBM heavy-hex chip in **6 CNOTs** (the textbook circuit compiled onto the chip: 10), W and Dicke states in **5** where Qiskit's compiler uses 11, each proven by Qiskit |
| **ML error-correction decoder** | On the distance-3 surface code a NumPy network makes **21% fewer logical errors** than minimum-weight matching at 1% noise, as learned decoders like AlphaQubit do. At **distance 5** the bigger code suppresses errors **5.9x** per round (Λ; Google's Willow measured 2.14), and a network on top of matching that sees both matchings' corrections makes 10% fewer errors again (paired test z = 7.8) |
| **An AI scientist that learns** | Muse Spark designs circuits in rounds and sees what exact physics said: with that feedback its best proven circuit improved on all three targets (6 to 5, 6 to 5 and 8 to 7 CNOTs); asked afresh it never improved on its first answer, and random wiring never reached a target: [docs/LEARNING.md](docs/LEARNING.md) |
| **AI-designed error-correcting codes** | For noise where phase flips dominate, Muse Spark found in its second round a 9-qubit code that needs **9 Z errors** to fail, three times the surface code's 3, while still correcting any single error, proven by an exact checker: [docs/CODES.md](docs/CODES.md) |
| **The AI referee** | Muse Wonder challenges Muse Spark's answers about a circuit: debate raised them from 17 to 19 of 24 right, but Wonder also raised 5 false alarms and talked Spark out of 2 right answers; only exact simulation knew which challenge was right: [docs/REFEREE.md](docs/REFEREE.md) |
| **Reproduce a whole paper** | Give it an arXiv id: Muse Wonder found 8 experiments in a 100-page paper, Muse Spark transcribed each, and exact simulation reproduced 3 of the 5 it could check (11 of 19 stated probabilities) in under two minutes |
| **ML verifier** | Predicts how much of a circuit survives noise in about 150 µs with a conformal error bar: **9x more accurate** than the usual rule of thumb, and checked exactly every time |
| **When does quantum win?** | Surface-code resource estimates against the best classical route; the model lands within 1.3x (qubits) and 2.3x (time) of Gidney and Ekerå's published RSA-2048 figure, and it says "classical wins" when it does |
| **Reproduce a paper** | Muse Spark read a printed figure's circuit, all 8 bar heights, the shot count and the bit order in 8 s; an exact re-run judged every claim against its error bar |
| **AI alone vs Inkubit** | The same model alone was exact on small circuits but only 3 of 6 on 6- to 8-qubit ones, once 43% off with full confidence: [docs/ARENA.md](docs/ARENA.md). That is why everything here is verified |

### Where things are

| Section | What is in it |
| --- | --- |
| Top of the page | **Mission control** (a whole problem, planned and verified) or a **quick question** to the same exact tools |
| Sketch to code | Photo or camera, words or voice, the **live board** (point a camera at a whiteboard), the **Quantum Rosetta** (Dirac, OpenQASM, Quil, Qiskit, Cirq and more, both ways) |
| Discover | **Discovery lab**, **an AI scientist that learns**, **when does quantum win**, **reproduce a paper** (a figure, or a **whole paper** from its PDF) |
| Hardware & networks | **IBM Quantum** (chip maps, placement advisor, run on IBM), **Pulse lab** (DRAG on a three-level transmon), **ML decoder**, **code lab** (AI-designed codes, check your own), error-correction lab, **distributed quantum computer**, **satellite planner** (SpeQtre and QUBE-II live on today's real orbits, under the cloud forecast) |
| Labs & games | Challenges, bug hunt (against Muse Spark), Shor, QAOA, H₂ from first principles, BB84 with a spy |
| Evidence | Simulation observatory (satellites vs fiber, Grover vs noise, entanglement growth, the memory wall, the ML verifier), AI alone vs Inkubit, **the AI referee** (Muse Spark against Muse Wonder) |

### Run it in two minutes

```bash
python3.13 -m venv .venv && source .venv/bin/activate     # Windows: py -3.13 -m venv .venv; .venv\Scripts\activate
pip install -r backend/requirements.txt
(cd frontend && npm ci && npm run build)
cd backend && python -m uvicorn inkubit.api.app:app --port 8000   # then open http://127.0.0.1:8000
```

Press **Guided tour** in the header (or open `/#tour`) for a walk through the highlights in under two minutes. Without a key
everything runs offline on labelled mock models; with `META_API_KEY` in `.env` the Meta models are
live. 626 backend tests, all offline except two opt-in live checks (`cd backend && python -m pytest -q`), and browser tests drive the built app
(`python -m pytest e2e`); CI runs both on every push. Every design decision is in [DECISIONS.md](DECISIONS.md) (D1 to D81); what was built on which day is in
[Built during the hackathon](#built-during-the-hackathon).

### Host it, and check it on real hardware

The `Dockerfile` runs Inkubit in public mode: code written by a model is never executed (the agent runs Inkubit's
own template code) and billed model calls stop at 300 a day, after which the labelled offline models answer. It fits
a free container (512 MB, a tenth of a CPU: about 260 MB in use, 385 MB at the peak of a sketch run with its sandbox),
and the slow, input-free results (the observatory, the pulse lab) are stored with the app (`scripts/precompute.py`)
so a cold start does not spend minutes on them. [Deploy it to Koyeb's free tier](https://app.koyeb.com/deploy?type=git&builder=dockerfile&repository=github.com/Dhruv-Deku/inkubit&branch=main&name=inkubit&ports=7860;http;/&instance_type=free&regions=was) in one click (add
`META_API_KEY` as a secret for the live models), or to a Hugging Face Space with `scripts/deploy_space.py` (Docker
Spaces need a PRO account). `scripts/discovery_hardware.py` runs the discovery lab's proven circuits on the same chip next
to the circuits they beat, `scripts/calibration_snapshot.py` turns the chip's calibration into the "Calibrated" noise
preset in the run bar, and `scripts/hardware_check.py` runs four circuits on
the least busy IBM quantum computer (with `IBM_QUANTUM_TOKEN` in `.env`) and compares the counts with the ideal odds,
Inkubit's generic preset and a digital twin built from the device's calibration; `--fake` rehearses it offline.

## The original pipeline: sketch to verified code

Draw a quantum circuit or a satellite link on paper and get running, verified code in seconds. Inkubit turns the
photo into a structured spec, writes Qiskit code for it, runs that code under realistic noise, and **proves the
result is right** by checking it against an independent simulation of the spec. When the code is wrong, a
self-repair agent diagnoses the failure in plain language, fixes it, and runs it again, live on screen.

![The agent catches a planted bug, repairs it and verifies the result](docs/screenshots/agent-repair.gif)

## Why it matters

Quantum programs fail silently. A reversed CNOT or a qubit index off by one still
runs and still prints a histogram; it is just the wrong histogram. Students and
researchers sketch circuits and network layouts on paper long before they write
code, and the jump from sketch to *correct* code is where time goes.

Inkubit closes that gap and refuses to fake success:

- Every run is compared with the **exact** distribution the spec predicts under
  the same noise model, computed by a separate code path that never sees the
  generated code.
- Failures are reported honestly. If the agent cannot fix the code, the result
  is marked **Not verified**, and the code and counts are labelled as unverified.
- Every model answer says which model produced it, and an offline mock is always
  labelled as a mock.

## What it does

| Step | What happens | Model |
| --- | --- | --- |
| Mission control | A whole problem in words, a photo and your voice ("connect two cities 1,200 km apart with quantum-secure keys, compare satellite and fiber, check whether a spy on 25% of photons is caught"). The photo is read by SAM 3.1 and Muse Spark; Muse Spark (or Muse Wonder) plans a dependency graph of up to 8 exact tools under a JSON schema, with circuits passed between steps by reference; independent steps run in parallel and stream to a live graph; a failed step is repaired once by the model; every result is verified by physics invariants and, for circuits, by two independent noisy simulators (our channels and Qiskit Aer, agreeing to 1e-6) plus the ML verifier; Muse Spark writes the report and every number in it is traced **Download report** saves the whole mission as one page: the plan, every step with its checks and arguments, the report with each number marked traced or not, and standalone Qiskit code for every circuit. | **Muse Spark 1.3** plans, repairs and reports, **Muse Wonder 1.0** in deep mode, **SAM 3.1** and **Muse Voice Transcribe 1.0** perceive |
| ML verifier | A neural-network ensemble (NumPy, `scripts/train_ml_verifier.py`) predicts in about 151 µs how much of a circuit's answer survives realistic noise, with an adaptive split-conformal interval, then exact simulation checks it: on 900 held-out circuits its average error is 0.010, 9 times smaller than the product-of-gate-fidelities rule of thumb (0.087) and below a global-depolarizing physics model (0.013); its 90% interval held for 90% of them and for 78% of 60 textbook cases it never saw (error 0.020). A miss grades the model, never the result | – |
| Algorithm library | Seven more textbook algorithms, each checked against its known answer: the QFT finding a period, Simon's algorithm, the swap test, entanglement swapping, a Trotterized quantum magnet (checked against the product formula), 3-qubit Grover (121/128) and a quantum half adder; Mission control runs any of them | – |
| Discovery lab | Muse Spark proposes CNOT layouts, spanning-tree and random layouts add more; every layout's rotations are fitted exactly and pruned, every winner is proven by Qiskit (overlap ≥ 1 − 1e-8), the ML verifier screens and exact noisy simulation decides. Found: GHZ on all 7 qubits of an IBM heavy-hex chip in 6 CNOTs (textbook compiled onto the wiring: 10; Qiskit's state preparation: 197), W and Dicke(4,2) states in 5 (compiler: 11), a random 3-qubit state in 3 (compiler: 4) | **Muse Spark 1.3** / **Muse Wonder 1.0** propose |
| Distributed quantum computer | One circuit on two small chips joined by a link from the network planner: exhaustive search for the split with the fewest remote CNOTs; each remote CNOT by gate teleportation with the link's Bell pairs (exact Pauli channel from pair fidelity, readout and local gates, idling while messages travel); process fidelity over all inputs against one chip and against long-lived memory qubits, from 10 m to 100 km | – |
| When does quantum win? | Describe a problem in words or by voice; Muse Spark maps it to factoring, search, simulation or no known speedup; a surface-code estimate (code distance, physical qubits, magic-state factories, runtime) meets the best classical route. Checked on every factoring result against Gidney & Ekerå's RSA-2048 figure (model: 26.6 million qubits, 18.5 hours; published: 20 million, 8 hours) | **Muse Spark 1.3** maps the problem |
| Live board | Point a camera at a whiteboard: the browser sends a frame only when the drawing has changed and holds still; SAM 3.1 and Muse Spark read it (about 35 s live for a new frame), exact simulation runs, and each qubit's odds are pinned to its wire in the photo | **SAM 3.1**, **Muse Spark 1.3** |
| Quantum internet | A 3D Earth (three.js) with about 60 cities: ask for a network in words or by voice, watch Muse Spark design it, Muse Wonder challenge it over two rounds, exact physics score each route and an exhaustive search find the best; switch between the designs; click a route to make it fiber, repeaters (with a memory-quality slider) or a satellite; add routes by clicking two cities; run time at 600x to watch the real satellites pass | **Muse Spark 1.3**, **Muse Wonder 1.0**, **Muse Voice Transcribe** |
| Lecture checker | Upload a short video of someone explaining a circuit at a board (or check the bundled sample): **Muse Voice Transcribe** in diarization mode gives who said what and when, **SAM 3.1** follows every drawn part through the video so the board's history is known, **Muse Spark** reads the finished board and writes each spoken claim out formally (probabilities, possible outcomes, entanglement, named states), **exact simulation** judges each one against the circuit as drawn at that moment, **Muse Wonder** writes corrected notes and **Muse Image** a figure that is read back and proven before it is shown. A timeline puts speech, drawing and verdicts on one axis; click a verdict to hear the claim | **all five Meta models** |
| Proven illustrations | Muse Image draws a figure without captions; Muse Spark picks what to look for, SAM 3.1 segments it, Muse Spark reads only what is drawn; the circuit read back must have the same unitary as the real one. A wrong figure goes to Muse Image's edit endpoint with the exact difference (at most twice); one that never matches is replaced by the exact drawing. Used for the lecture checker's figure; the Proof section shows the benchmark, figure by figure | **Muse Image 1.0**, **SAM 3.1**, **Muse Spark 1.3** |
| Satellite planner | The quantum-key satellites in orbit today, **SpeQtre** (UK–Singapore, 80 mm telescope) and **QUBE-II** (Germany, 85 mm), fly their real orbits: today's CelesTrak elements (checksummed, refreshed every two hours, with a labelled fallback) propagated by SGP4 from now, live on a canvas globe with Natural Earth coastlines, the real night side and the 15° footprint. Stations on the WGS84 ellipsoid; the frame chain matches Skyfield, an independent implementation, to 0.003° and 34 m. Every night pass over two ground stations in the next 24 hours, the key each gives through the satellite's own telescope, the **Open-Meteo cloud forecast** at each station and the key to expect, and a 7-day outlook. Micius re-entered on 25 January 2026, so its 2017 experiments replay on a modelled orbit (entangled pairs when both cities see it at once, or a trusted-node BB84 downlink; about 2 kbit/s at 1,200 km, the order Micius measured) | – |
| Reproduce a paper | Upload a figure from a paper: Muse Spark transcribes the circuit as OpenQASM (read by the exact parser, sketch pipeline as fallback) and the claimed odds, shots and bit order; the circuit is re-run exactly and every claim judged against shot-noise error bars, bit order inferred when unstated | **Muse Spark 1.3** reads the figure |
| ML error-correction decoder | Distance-3 rotated surface code, 3 rounds of phenomenological noise: exact minimum-weight matching against a NumPy network that also reads the X checks (Y errors correlate them). At 1% noise: 0.72% logical errors against 0.92% for matching (21% fewer, beyond the error bars at every noise level). **Distance 5** (25 qubits, 5 rounds; layout generated for any odd distance, matching by PyMatching, equal to the exact matcher on 20,000 distance-3 shots): per-round logical error 5.0 × 10⁻⁴ against 3.0 × 10⁻³ at distance 3, a suppression Λ = 5.9 at 1% noise (11.3 at 0.5%, 1.15 at 6%). A 172-256-256-1 network on top of matching, fed where each kind of matching put its corrections (a qubit in both is a Y error), makes 10% fewer logical errors at 1%: on the same shots it fixes 123 and breaks 27 (McNemar z = 7.8), significant at 8 of 9 noise levels. A first version without the corrections only learned to copy matching | – |
| Pulse lab | An X gate as the microwave pulse on a three-level transmon (anharmonicity −300 MHz, T1/T2 as Lindblad terms): Gaussian against calibrated DRAG; short Gaussians leak into |2⟩, DRAG reaches 1.1e-4 error at 15 ns where only T1/T2 is left, its calibrated β ≈ 0.5 matching first-order theory | – |
| Ask Inkubit | One assistant for the whole lab. Ask in words or by voice ("compare H₂ at 0.74 and 2.5 Å", "Eve listens to 30% of photons", "split these six people into two teams", "make a GHZ state and run it on noisy hardware"): the model calls nine exact tools (circuit simulation, optimizer, H₂, BB84, QAOA, Shor, network links, error correction, the Rosetta), in parallel when it needs several, and answers with live result cards. **Every number in the answer is traced to a tool result**; untraced numbers are flagged | **Muse Spark 1.3** with tool calling, **Muse Voice Transcribe 1.0** for voice |
| 1. Sketch | Upload a photo, take one with the camera, pick a sample, **describe it in words or say it out loud**, or paste JSON | **Muse Voice Transcribe 1.0** hears it, **Muse Spark 1.3** turns the description into a spec |
| 2. See the parts | The kind of diagram is identified and every drawn part is boxed | **Muse Spark 1.3** picks noun phrases, **SAM 3.1** segments each one |
| 3. Read it | The boxes and the photo become a validated JSON spec, each operation linked to its box | **Muse Spark 1.3** with structured output |
| 4. Correct it | Side-by-side photo overlay and editor (form or raw JSON); hover a box to find its line; live validation with readable errors. **Compose by clicking**: pick a gate from the palette, click a wire (control first for CNOTs), erase, undo; a **live state** strip (3D Bloch spheres you can turn, each qubit's path, amplitudes, and an **entanglement web**: gold threads between entangled pairs, arcs for entanglement with the rest) updates on every edit | exact simulation, no model |
| Shorten it | **Find a shorter circuit**: rewrite rules (each with a reason), the Qiskit compiler and Muse Spark each propose one; exact simulation proves each equal (same gate, same state, or same measured odds) or rejects it with the outcome that differs. Use it in one click; Undo brings yours back | **Muse Spark 1.3** proposes, gets one retry with the rejection reason |
| 5. Run and verify | The agent writes the code, runs it in a sandboxed subprocess, verifies, diagnoses, repairs, retries (up to 4 attempts) | **Muse Spark 1.3** writes and repairs code (or the **Muse Code** CLI, opt-in) |
| 6. Understand it | Histogram (predicted vs measured vs ideal), metrics, code with per-attempt diffs, plain-language explanation in 12 languages, clean diagram, one-file HTML report | **Muse Spark 1.3** explains, **Muse Image 1.0** draws |
| 7. Look inside | Step through the exact state gate by gate (amplitudes, phases, a Bloch sphere per qubit, the entanglement web), entanglement ideal vs noisy, error budget per noise source, how good the hardware must be for 99%, readout correction, **zero-noise extrapolation** (fold every gate to run at 3x and 5x the noise, extrapolate back to zero, with and without shot noise), a **Bell test** (CHSH for every entangled pair, Mermin for three qubits: can any classical explanation fake these correlations, ideal, noisy and from shots with error bars), **state tomography** (the state rebuilt from 27 simulated measurement settings, drawn as a 3D density-matrix cityscape next to the intended one), cost on real chip wirings, OpenQASM 2/3 export. Also available before running ("Step through") | exact simulation, no model |
| 8. Ask | Questions about this run, answered only from its numbers | **Muse Spark 1.3** |
| 9. What if | Drag the hardware quality from perfect to 10x worse and watch the exact outcome odds change | exact simulation, no model |
| Challenges | 11 puzzles in three levels (warm-up, entanglement, gate golf): build a target state or gate, scored exactly with par like golf, stars saved in the browser, a lesson on success. Solve them with the palette, a photo of your paper answer, or words | **Muse Spark 1.3** gives hints that never spell out the answer |
| Error-correction lab | The three-qubit bit-flip code against a bare qubit on log-log axes, perfect vs realistic gates; drag the gate quality and watch the break-even point move (the threshold idea); switch to phase flips to see the same code make things worse. One click opens the code, with an error, in the editor | exact simulation, no model |
| Quantum Rosetta | The language of quantum computing, translated both ways. Type, paste, say or photograph a state or a program: Dirac notation (`(|01⟩−|10⟩)/√2`, `cos(π/8)|0⟩ + e^(iπ/4) sin(π/8)|1⟩`, `|GHZ⟩`, LaTeX pasted from a paper), OpenQASM 2 or 3, Quil, Qiskit calls, other code (Cirq, PennyLane, Q#, Braket) or plain words. Out come the state in Dirac notation (independent qubits factored out, surds and phases recognised, LaTeX to copy) with which qubits are entangled, **a circuit proven to prepare it** (shortest textbook-gate circuit by exhaustive search, GHZ fan-out, or compiled state preparation; fidelity checked by exact simulation), what every gate does in words with the state after it, and the same program in **eight languages**: Qiskit, OpenQASM 2 and 3 and Cirq are run here and must reproduce the same state. A 28-word dictionary gives each term an example state computed exactly. The gate-by-gate inspector now shows the state in Dirac notation at every step | exact parsers and simulation; **Muse Spark** only for code it cannot parse exactly and for photos (transcribed, never solved), labelled |
| What it can do | Nine cards on the start page (sketch to code, debugging, chemistry, quantum security, optimization, satellite networks, cryptography, real hardware, trust), each a pen sketch on paper in the hand of the sample sketches (`scripts/make_card_sketches.py`) and each one click into the part of the app that does it | none |
| Simulation observatory | Five exact simulations of where quantum technology stands, each with its key number written out: **satellites vs fiber** (secret key between two cities from 25 to 3,000 km, the network planner's own model, satellite geometry from the Earth's curvature, Micius's 1,203 km marked); **Grover vs noise** (2 to 5 qubits compiled to CNOTs and evolved as exact density matrices under the realistic preset: at 5 qubits the noise erases the speedup); **quantum walk** vs a random walk (play it step by step; spread grows with t, not √t); **entanglement growth** in random circuits up to Page's limit; **the exponential wall** (memory for an exact state, laptop to supercomputer) | exact simulation, no model |
| Molecule lab (H₂) | The hydrogen molecule from first principles: STO-3G integrals computed in closed form (checked against Szabo and Ostlund), Hartree-Fock against the exact energy as the bond stretches, and VQE on one qubit with realistic noise, raw and with the calibrated noise undone (within shot noise of exact at every bond length). Shows why the classical shortcut fails when the electrons become correlated | exact simulation, no model |
| Catch the spy (BB84) | Quantum key distribution: random bits and bases, an intercept-resend eavesdropper on a share of photons you choose, sifting, the error-rate check and the 11% abort, privacy amplification. Eve on a share f adds f/4 to the error rate, so she is caught; each photon also opens as a circuit | exact simulation, no model |
| AI alone vs Inkubit | The same model, asked to predict circuits' outcome odds on its own like a chatbot, scored against exact simulation ([docs/ARENA.md](docs/ARENA.md)): exact on 13 of 13 textbook circuits and 10 of 11 new small ones, but only 3 of 6 bigger ones (6 to 8 qubits), with one confidently wrong answer that put 43% of the probability in the wrong place and one with no usable answer. "Ask the AI alone" under the editor runs the same test on any circuit; the models table says how each model step is checked | **Muse Spark 1.3** answers alone; exact simulation scores it |
| Bug hunt | One gate in a known circuit is wrong (wrong wire, control and target swapped, a look-alike gate, an angle slip, a stray gate). Compare what it should give with what it gave and click the culprit, against the clock. An exact search tries every one-gate edit, so any gate whose fix restores the odds counts, and rounds where too many gates would count are re-planted. Three levels; score and streak saved in the browser | Live, **Muse Spark 1.3** plays the same round in parallel from the same facts, and its pick and reasoning appear after yours |
| Split the party (QAOA) | Guests and feuds as a graph you edit by clicking; QAOA seats them at two tables (Max-Cut). Brute force gives the true best; the depth-1 landscape shows every angle pair with the optimizer's path, and you can click it to try your own angles; depths 1 to 3 are optimized exactly, with the odds of a best seating with perfect and with realistic qubits. The circuit opens in the editor | exact simulation, no model |
| Network mode | Physics model of every link, bottleneck search, fixes (relays, telescopes, memories, **entanglement purification**) re-simulated, before/after on an animated **network map** (entangled pairs in flight, thicker links deliver more, the weakest link marked) | **Muse Spark 1.3** explains, **Muse Image 1.0** draws |

<table>
<tr>
<td><img src="docs/screenshots/2-overlay.png" alt="Photo overlay and spec editor"></td>
<td><img src="docs/screenshots/4-results.png" alt="Verified result with metrics and histogram"></td>
</tr>
<tr>
<td><img src="docs/screenshots/6-inspector-entangled.png" alt="Gate-by-gate inspector with Bloch spheres"></td>
<td><img src="docs/screenshots/7-hardware.png" alt="How good the hardware must be for a 99% match"></td>
</tr>
<tr>
<td><img src="docs/screenshots/8-ask.png" alt="Questions answered from the run's numbers"></td>
<td><img src="docs/screenshots/7-layouts.png" alt="Cost on real chip layouts"></td>
</tr>
<tr>
<td><img src="docs/screenshots/10-challenge.png" alt="A solved challenge with stars and the lesson"></td>
<td><img src="docs/screenshots/11-compose.png" alt="Click-to-compose palette with the live state"></td>
</tr>
<tr>
<td><img src="docs/screenshots/12-network-map.png" alt="Animated network map"></td>
<td><img src="docs/screenshots/13-whatif.png" alt="What if the hardware were better"></td>
</tr>
<tr>
<td><img src="docs/screenshots/15-optimizer.png" alt="Shorter circuits, each proven equal or rejected"></td>
<td><img src="docs/screenshots/14-zne.png" alt="Zero-noise extrapolation"></td>
</tr>
<tr>
<td><img src="docs/screenshots/17-bell-test.png" alt="Bell test: the W state's pairs stay classical, the trio does not"></td>
<td><img src="docs/screenshots/18-tomography.png" alt="State tomography cityscape of a GHZ state"></td>
</tr>
<tr>
<td><img src="docs/screenshots/19-qec-lab.png" alt="Error-correction lab with the break-even point"></td>
<td><img src="docs/screenshots/16-entanglement-web.png" alt="Live entanglement web"></td>
</tr>
<tr>
<td><img src="docs/screenshots/20-bug-hunt.png" alt="Bug hunt: the player against the exact search and Muse Spark"></td>
<td><img src="docs/screenshots/21-qaoa.png" alt="Split the party: QAOA seats feuding guests at two tables"></td>
</tr>
<tr>
<td><img src="docs/screenshots/22-ai-alone.png" alt="The AI alone says every outcome is equally likely; the exact truth has four peaks"></td>
<td><img src="docs/screenshots/23-arena.png" alt="AI alone vs Inkubit: exact on small circuits, unreliable on bigger ones"></td>
</tr>
<tr>
<td><img src="docs/screenshots/24-molecule.png" alt="Molecule lab: Hartree-Fock fails as H2 is pulled apart; mitigated VQE follows the exact curve"></td>
<td><img src="docs/screenshots/25-catch-the-spy.png" alt="Catch the spy: an eavesdropper on 60% of photons pushes the error rate past 11%"></td>
</tr>
<tr>
<td colspan="2"><img src="docs/screenshots/26-use-cases.png" alt="What it can do: nine cards with pen sketches, one click each"></td>
</tr>
<tr>
<td colspan="2"><img src="docs/screenshots/43-quantum-internet.png" alt="Quantum internet on a 3D Earth: Muse Spark designed Delhi, Mumbai and London, Muse Wonder improved it in its second round, physics and an exhaustive search agree; live satellites overhead"></td>
</tr>
<tr>
<td colspan="2"><img src="docs/screenshots/41-lecture-checker.png" alt="Lecture checker: the wrong claims from a filmed lecture, the timeline of speech, drawing and verdicts, the tracked board, corrected notes and a proven figure"></td>
</tr>
<tr>
<td colspan="2"><img src="docs/screenshots/42-proven-illustrations.png" alt="Proven illustrations: each Muse Image figure read back and compared exactly; a corrected Toffoli, figures right first time, and the ones replaced by the exact drawing"></td>
</tr>
<tr>
<td><img src="docs/screenshots/27-observatory-satellites.png" alt="Simulation observatory: fiber gives no key beyond 500 km, the satellite still works at 2,400 km"></td>
<td><img src="docs/screenshots/28-observatory-grover.png" alt="Grover vs noise: at 5 qubits today's noise erases the speedup"></td>
</tr>
<tr>
<td><img src="docs/screenshots/29-mission-control.png" alt="Mission control: Muse Spark planned three parallel steps, all verified, and a report with every number traced"></td>
<td><img src="docs/screenshots/30-ml-verifier.png" alt="ML verifier: predictions hug the diagonal, the rule of thumb falls far below it"></td>
</tr>
<tr><td><img src="docs/screenshots/31-discovery.png" alt="Discovery lab: GHZ-7 on heavy-hex in 6 CNOTs"></td><td><img src="docs/screenshots/32-distributed.png" alt="Distributed computer: two chips and the fidelity against distance"></td></tr>
<tr><td><img src="docs/screenshots/33-when-quantum-wins.png" alt="When does quantum win: Grover search loses to a classical cluster at 64 bits"></td><td><img src="docs/screenshots/34-live-board.png" alt="Live board: odds pinned to the wires of a camera frame"></td></tr>
<tr><td><img src="docs/screenshots/35-satellite-planner.png" alt="Satellite planner: SpeQtre live on its real orbit, every pass over Chilbolton and Singapore under the cloud forecast"></td><td><img src="docs/screenshots/36-reproduce-a-paper.png" alt="Reproduce a paper: every claim within its error bar"></td></tr>
<tr><td><img src="docs/screenshots/39-ibm-chip-map.png" alt="IBM Quantum: three Heron chips mapped from their own calibration, every qubit and coupler coloured by its error"></td><td><img src="docs/screenshots/40-ibm-experiments.png" alt="Experiments on ibm_fez: the advisor's best, median and worst placements measured 0.894, 0.814 and 0.285; teleportation with real feed-forward 0.924"></td></tr>
<tr><td><img src="docs/screenshots/37-ml-decoder.png" alt="ML decoder at distance 3 and 5: the bigger code suppresses errors 5.9x per round"></td><td><img src="docs/screenshots/38-pulse-lab.png" alt="Pulse lab: DRAG against Gaussian"></td></tr>
</table>

## Architecture

```mermaid
flowchart LR
    photo[Photo of sketch] --> concepts[Muse Spark:<br/>kind + noun phrases]
    concepts --> sam[SAM 3.1:<br/>boxes per phrase]
    sam --> draft[Muse Spark:<br/>photo + numbered boxes<br/>-> spec draft JSON]
    draft --> validate{Validate<br/>spec}
    validate -- errors --> draft
    validate --> editor[User corrects<br/>spec in the UI]
    json[Paste JSON /<br/>example] --> editor
    editor --> kind{kind}
    kind -- circuit --> gen[Write code<br/>Muse Spark / template]
    gen --> run[Run in sandboxed<br/>subprocess, Aer + noise]
    run --> verify[Verify vs exact<br/>noise-aware prediction<br/>built from the spec]
    verify -- fail --> diag[Diagnose in<br/>plain language]
    diag --> repair[Repair<br/>Muse Spark / rules]
    repair --> run
    verify -- pass --> results
    kind -- network --> netmodel[Analytic link model]
    netmodel --> bottleneck[Find bottleneck,<br/>try fixes, re-simulate]
    bottleneck --> results[Results + explanation<br/>Muse Spark + diagram<br/>Muse Image]
    run -. SSE live log .-> ui[(Browser)]
    bottleneck -. SSE live log .-> ui
```

Backend: Python 3.11+, FastAPI, Qiskit 2.6 + qiskit-aer 0.18, pydantic v2, SSE.
Frontend: React 19 + TypeScript + Vite. No database; jobs live in memory.

```
backend/inkubit/
  spec/      versioned pydantic models, readable validation, schema.json, model-facing draft schema
  adapters/  model interfaces; meta (Meta Model API) and mock implementations, cache, fallback
  codegen/   deterministic template codegen, static safety check
  sim/       noise presets, sandboxed subprocess runner
  verify/    independent expected distributions, metrics, verdicts
  agent/     the loop, fault injection, diagnosis, rule-based repairer, event bus
  network/   physics, link model, fix search, network agent, explanation
  explain/   explanation templates, diagram rendering
  api/       FastAPI app and job store
frontend/src/  React app (start, overlay + editor, live log, results)
examples/      specs and sample sketches (with ground-truth fixtures)
```

## How each Meta model is used

All calls go to `https://api.meta.ai/v1` with `Authorization: Bearer $META_API_KEY`,
using only endpoints and fields documented in Meta's docs (list of pages in
[`docs/meta-api/SOURCES.md`](docs/meta-api/SOURCES.md)).

- **SAM 3.1** (`sam-3.1`, `POST /v1/responses`, streamed): one concept prompt per
  noun phrase with the photo as a data URL and `metadata.include_confidence: "true"`.
  The special-token output (`<0f>0<|box;x1=..;c=..|><|mask;...|>`) is parsed into
  boxes and confidences, scaled to the uploaded image. **On video** (the lecture
  checker) a 2-frames-a-second H.264 clip goes as an `input_video` data URL; SAM
  answers one line per frame and keeps each object's id across frames, so an
  object's first frame is when it was drawn ("square" and "circle" track pen
  sketches reliably).
- **Muse Spark 1.3** (`muse-spark-1.3`, `POST /v1/chat/completions`):
  1. looks at the photo and names what SAM should look for (`response_format`
     JSON schema, `reasoning_effort: low`), the pairing Meta's docs recommend;
  2. reads the photo plus a copy with numbered boxes (set-of-marks prompting)
     into a spec draft with structured output, linking every operation to a SAM
     box; invalid drafts are re-prompted once with the readable validation errors;
  3. writes the Qiskit script and, when verification fails, repairs it, given the
     spec, the code, the error, the verifier's verdict, the diagnosis and the
     history of earlier attempts;
  4. explains the final result to a student using the real numbers, in any of 12 languages;
  5. turns a plain-language description ("Bernstein-Vazirani with secret 1011", "300 km of fiber
     with 2 repeaters") into a validated spec with the same structured-output schema;
  6. answers questions about a finished run from that run's facts only, and says when
     the facts do not contain the answer;
  7. coaches a player through a challenge: it sees the goal, the player's circuit and
     its exact score (never the reference solution) and gives one next-step hint;
  8. proposes a shorter circuit with the same measured odds (structured output). Exact
     simulation accepts or rejects it; a rejected proposal goes back once with the
     outcome that differs, so the model can fix its own mistake.
  9. plays the bug hunt: given a broken circuit's operations, the intended odds and the
     observed counts (exactly what the player sees), it names the wrong gate, the fix and
     its reasoning (structured output); the exact search grades it like the player.
  10. answers alone, like a chatbot with no simulator, for the "AI alone vs Inkubit" comparison
     (structured output: every outcome and its probability), scored against exact simulation.
  11. runs **Ask Inkubit** with tool calling (`tools` on Chat Completions): it chooses among nine
      function tools, each a wrapper over an exact engine, gets their results back as `tool` messages and
      answers; every number in the answer is then traced to a tool result.
  12. reads for the **Quantum Rosetta** what Inkubit cannot parse exactly: code in Cirq, PennyLane, Q# or
      Braket (into the circuit spec, labelled as a model's reading) and photos of notation from a textbook,
      slide or whiteboard (`read_notation`: transcribed as text under a JSON schema, with an instruction not to
      solve or simplify; the exact parser then reads the text).
  13. runs **Mission control**: plans a whole problem as a dependency graph of exact tool steps under a
      JSON schema (`mission_plan`), fixes the arguments of a step that failed given the error and the tool's
      schema (`step_repair`), and writes the mission report from the step facts and their checks
      (`mission_report`); every number in the report is traced.
- **Muse Wonder 1.0** (`muse-wonder-1.0`, `POST /v1/chat/completions` with `tools`,
  `reasoning_effort: "medium"`): the deep mode of Ask Inkubit, for questions that
  take several steps ("plan a 1200 km satellite key link, then check whether a spy
  would be caught"). Same nine tools, same tracing, up to six rounds of tool calls.
  Muse Wonder is in preview; Muse Spark stays the fast default.
- **Muse Voice Transcribe 1.0** (`muse-voice-transcribe-1.0`, `POST /v1/asr/transcribe`,
  multipart, `PUSH_TO_TALK`): "Say it" records the microphone in the browser,
  encodes a mono 16 kHz WAV and sends it with a keyword list (qubit, Hadamard,
  CNOT, GHZ, Shor, ...) that biases the recogniser toward quantum words. The
  transcript then takes the describe-in-words path. Offline there is no speech
  model, so the browser's own recogniser is used and the server refuses to guess.
  The lecture checker uses **`DIARIZATION`** mode: the buffered answer lists each
  turn with its start, end and a speaker label.
- **Muse Image 1.0** (`muse-image-1.0`, `POST /v1/images/generations`,
  `response_format: b64_json`): a clean, annotated illustration of the final
  design. It is always shown next to the exact Qiskit drawing, so an imperfect
  illustration can never mislead. A figure that is shown on its own (the lecture
  checker's) is **proven first**: drawn without captions, read back by SAM 3.1 and
  Muse Spark, compared exactly with the circuit, and corrected with
  **`POST /v1/images/edits`** (the figure as a data URL plus the exact difference)
  when it is wrong; if it never matches, the exact drawing is shown instead.
- **Muse Code** (opt-in, `INKUBIT_CODE_BACKEND=muse-cli`): repairs are handed to
  the Muse Code agent headlessly (`muse exec --prompt-file task.txt
  --disable-approval --max-model-steps 12`) in a scratch workspace; Inkubit's
  verifier, not the CLI's exit code, decides whether the fix worked.

Responses are cached on disk by request hash (`backend/.inkubit_cache/`), so
repeated demos and runs cost nothing. Standard-mode model IDs are used, so
content is not used for training.

**Mock mode.** Every model sits behind an adapter with a deterministic offline
implementation (`INKUBIT_MODEL_PROVIDER=mock`, the default without a key): the
sample sketches are recognised by file hash and return their recorded
ground-truth boxes and spec, code comes from the template, repairs from a
rule-based repairer, explanations from a template filled with the real numbers,
diagrams from Qiskit's drawer. If a live call fails and
`INKUBIT_ALLOW_FALLBACK=1`, the mock answers and the UI badge says
**Mock fallback** with the error. Mock mode never pretends to read an unknown
photo; it says so.

## Run it

Requirements: Python 3.11+ (3.13 tested), Node 20+ (24 tested).

```sh
git clone <this repo> inkubit && cd inkubit
scripts/setup.sh          # venv + pinned Python deps, npm ci, frontend build, .env from .env.example
scripts/dev.sh            # backend :8000 + Vite :5173 -> open http://127.0.0.1:5173
```

On Windows run the scripts from Git Bash, or do the steps by hand:

```sh
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt
cd frontend && npm ci && npm run build && cd ..
cd backend && ../.venv/Scripts/python -m uvicorn inkubit.api.app:app --port 8000
# the built frontend is served at http://127.0.0.1:8000
```

**Live Meta models:** put your key in `.env` and switch provider:

```sh
META_API_KEY=LLM_...
INKUBIT_MODEL_PROVIDER=meta
INKUBIT_ALLOW_FALLBACK=1
```

The badge at the top right shows **Meta live**, **Mock**, or **Meta (no key: mock fallback)**.

**Command-line demo** (no browser): `scripts/demo.sh` runs the Bell circuit with
a planted bug and prints the live log. `scripts/demo.sh examples/specs/network_fiber_chain.json`
runs the network agent.

**Tests:** `cd backend && ../.venv/Scripts/python -m pytest -q` (626 tests, two opt-in live,
about 10 minutes, all offline). `python -m pytest e2e` (after `npm run build`) starts the server on the offline models
and drives the built app in Chromium: every section, a sketch to verified code, the guided tour, the satellite
planner, phone width (`E2E_BROWSER_CHANNEL=msedge` uses the system Edge). `pytest -m live` makes one cheap real call per
Meta model (skipped without a key; cached after the first run). `tests/test_claims.py` rebuilds every number this README and the
submission quote from the data file it comes from, so a document cannot drift from a result, and
`scripts/check_submission.py` checks everything the hackathon form needs.

## The spec format

One JSON document, discriminated by `kind`, version `1.0`. Full schema:
[`backend/inkubit/spec/schema.json`](backend/inkubit/spec/schema.json).

```json
{
  "kind": "circuit", "version": "1.0", "num_qubits": 2, "num_clbits": 2,
  "operations": [
    {"gate": "H", "targets": [0], "source": {"bbox": [310, 250, 410, 350], "confidence": 0.97, "segment_id": "s0"}},
    {"gate": "CX", "controls": [0], "targets": [1]}
  ],
  "measurements": [{"qubit": 0, "clbit": 0}, {"qubit": 1, "clbit": 1}],
  "metadata": {"title": "Bell pair", "origin": "image"}
}
```

Gates: `H X Y Z S T SDG TDG SX RX RY RZ CX CZ CP SWAP CCX MEASURE BARRIER` (enough for
Grover, Bernstein-Vazirani, Deutsch-Jozsa, QFT, phase estimation, teleportation and the W state;
all but QFT are in the example gallery, and QFT is one sentence away in "describe it in words").

**Feed-forward.** A `MEASURE` operation can sit in the middle of the list (a mid-circuit measurement), a measured qubit
can be used and measured again, `RESET` puts a qubit back to 0, and any gate can carry an optional `conditional`: it
runs only when classical bits written by earlier `MEASURE`s read the value. Several bits are a list, with the value read
in binary and the first listed bit lowest (Qiskit's register convention).

```json
{"gate": "MEASURE", "targets": [3], "clbits": [0]},
{"gate": "RESET", "targets": [3]},
{"gate": "MEASURE", "targets": [3], "clbits": [1]},
{"gate": "X", "targets": [1], "conditional": {"classical_register": [0, 1], "value": 3}},
{"gate": "Z", "targets": [2], "conditional": {"classical_register": 0, "value": 1}}
```

The generated code writes a condition as Qiskit's `with qc.if_test((qc.clbits[0], 1)):` (Qiskit 2 removed `c_if`),
nested one level per bit, and a reset as `qc.reset(q)`: the constructs IBM's chips run, so **Run on IBM Quantum** sends
them unchanged (both examples compile for ibm_fez with native `if_else` and `reset`). The verifier predicts it exactly, without
sampling, by deferred measurement: each mid-circuit measurement copies its qubit onto a record qubit, a conditioned gate
becomes the same gate controlled by its records, a reset swaps the qubit's state onto a fresh qubit nobody reads,
readout flips act on the record (the chip acts on the bit it read), and a conditioned gate's error acts only in the
branch where it fires. Against 200,000-shot Aer runs of the generated
`if_test` code that prediction agrees to the shot-noise floor, including under deliberately heavy noise with conditional
two-qubit gates, resets, reused qubits and two-bit conditions (`tests/test_feedforward.py`). The editor draws classical
bits as double lines, a reset as |0⟩, and each conditional gate with a dashed line down to the bits it reads (a filled dot
for 1, a hollow one for 0); per gate, "if c[x] = v" with + for another bit. Safety checks refuse a condition on a bit
nothing has measured yet (or measures later), on an out-of-range or repeated bit, a value that does not fit its bits, a
conditional `MEASURE`, `RESET` or `BARRIER`, a classical bit written twice, and a circuit whose added qubits would pass
10. Tools built on one state (step-through, live state, optimizer, proof sheet, Rosetta exports) refuse these circuits
in words rather than guess. Descriptions reach them too: offline, "teleportation with feed-forward", "bit-flip error
correction with a measured syndrome" and "active reset" route to the exact examples; live, Muse Spark fills a text-only
draft that can carry mid-circuit measurements and conditions (the sketch reader's format is unchanged). Examples:
`examples/specs/bit_flip_feedforward.json`, `teleportation_feedforward.json`, `active_reset.json`.

Networks list `nodes` (`ground_station`, `satellite`,
`repeater`, optional `memory_t2_ms`, `aperture_m`, `position`), `links`
(`from`, `to`, `fiber`/`free_space`, `length_km`, optional `loss_db`,
`depolarizing`), a `source`/`destination` pair and optional `purification_rounds`. Validation reports every
problem at once with a path, for example
`operations[2] (RX): target qubit 3 is out of range; this circuit has 2 qubits (qubits 0-1).`

## How the agent loop works

1. **Plan**, then **write** the script (Muse Spark, or the deterministic template offline).
2. In **demo mode**, attempt 1 is broken on purpose with a realistic bug (missing
   CNOT, reversed CNOT, wrong qubit, missing measurement, old import path, or a
   faked result) so the repair is always visible.
3. **Run** it in a fresh Python process: AST safety check first (only
   qiskit/qiskit_aer/json/math/numpy, no `open`/`eval`/`exec`), scratch folder,
   60 s timeout, API keys removed from the environment.
4. **Verify**: rebuild the circuit straight from the spec, compute the exact
   noise-aware distribution (density matrix + exact readout error), and compare
   with the measured counts. Pass iff total variation distance is within a
   three-sigma shot-noise bound (with a per-preset floor) and Hellinger fidelity
   is above the preset minimum (see `DECISIONS.md` D8).
5. **Diagnose** in plain language from the statistics, e.g. *"Attempt 1 failed:
   expected ~50% |00⟩ and 50% |11⟩, got 49% |00⟩ and 48% |01⟩. Bits c0 and c1
   should agree every time but come out independent; the entangling gate looks
   missing or points the wrong way. Repairing…"*
6. **Repair** with full evidence (spec, code, error, verdict, diagnosis, history),
   show the diff, and go back to 3. If the repairer returns the same code, stop:
   no fake retries. After 4 attempts the result is reported as **Not verified**.

Every step streams to the browser over SSE.

### Network mode

An analytic model (`backend/inkubit/network`): fiber at 0.2 dB/km; satellite
downlinks from diffraction plus turbulence spot size against the receiving
telescope, plus atmosphere and optics; Werner-state pairs whose fidelity drops
with accidental clicks; repeaters that swap pairs and store them in memories that
decohere as exp(-t/T2); BBM92 key rate from the error rate. The satellite preset
lands near the published Micius numbers (~66 dB, ~0.8 pairs/s over 1,200 km).
The agent finds the bottleneck (lossiest link, or memories too short for the
waiting time), tries every applicable fix (midpoint relay, rebalanced repeater
spacing, higher-elevation pass, bigger telescope, better memories) as a new,
validated spec, re-simulates each, keeps the best, and repeats for up to three
rounds. Purification (BBPSSW: two noisy pairs in, one better pair out) is one of
the fixes; because it halves the pair rate, pairs wait longer in memory, so the
agent learns to upgrade memories first. The fiber chain preset goes from no
secret key to 0.39 bit/s; the 600 km chain from none to 0.05 bit/s (memories,
then purification); the satellite preset from 0.013 to 1.9 bit/s.

### Inside the circuit

After every circuit run (or before it, with **Step through**), Inkubit computes
from the spec alone: the exact state after each gate with a Bloch sphere per
qubit (a shrinking arrow means the qubit is entangled), pairwise concurrence ideal
vs noisy (GHZ states are recognised as group entanglement), the fidelity each
noise source costs on its own, the noise level the hardware would need for a 99%
match, readout-error correction of the measured counts, and the cost of compiling
onto all-to-all, line and heavy-hex chips. The noisy analyses evolve the density
matrix with the verifier's own error channels and are tested to agree with Aer to
1e-8.

### Shorter circuits, proven equal

**Find a shorter circuit** (in the editor) runs up to four optimizers:
rewrite rules, the Qiskit transpiler at level 3, the two together, and
(live) Muse Spark. Each rule comes with a reason a student can check: H·H = 1;
S then S becomes Z; H on both sides turns CX into CZ; a CNOT whose control is
still |0⟩ never fires; a CZ whose partner is |1⟩ is a Z on the other qubit
(phase kickback); a diagonal gate right before measurement changes nothing a
measurement can see; a SWAP before measurement becomes a relabelling of the
classical bits; gates that never reach a measured qubit go. Every proposal is
then simulated exactly against the original and labelled with the strongest
claim that holds: the same gate for every input (process fidelity), the same
final state, or the same measured odds; anything else is rejected with the
outcome where it differs. The rules are fuzz-tested on random circuits and
never change the odds. Cheaper means fewer two-qubit gates first (CX 1, CP 2,
SWAP 3, Toffoli 6), then fewer gates; the panel also shows the exact match to
the ideal on realistic hardware before and after. When the result only flips
bits, it says so: the circuit's answer was fixed in advance (phase estimation
of a known phase shrinks to one X), which is true and worth knowing, not a
trick for unknown inputs.

### Zero-noise extrapolation

Readout error is undone first; then the circuit is run at 1x, 3x and 5x its gate
noise by folding (U, then U U⁻¹ U, then U U⁻¹ U U⁻¹ U: the same ideal result
with three and five times the gates) and every outcome's probability is
extrapolated back to zero noise with Richardson weights (15/8, -5/4, 3/8). With
exact probabilities a Grover search goes from 0.882 as measured to 0.999. The
panel also repeats it with 4,000 sampled shots per level, because on hardware
extrapolation amplifies shot noise (about 5.2x the shots for the same error
bars); for some circuits that eats the gain, and the panel says so.

### Bell test

For every entangled pair, the CHSH value under the best measurement settings
(Horodecki criterion: S = 2 sqrt(m1 + m2) from the pair's correlation matrix;
classical theories allow at most 2, quantum mechanics 2.83); when exactly three
qubits are entangled, the Mermin value over all measurement directions
(classical at most 2, quantum 4). Each comes three ways: ideal; the noisy
state measured with the settings planned for the ideal one; and 4,000 sampled
shots per setting with readout error, with a standard error. A Bell pair gives
2.828 ideal and 2.395 ± 0.025 on realistic hardware, 16 standard errors above
classical. A GHZ state has no entangled pair at all, yet reaches Mermin 4. A W
state's pairs are entangled but stay classical (1.886), while the trio
reaches 3.046, the known value.

### State tomography

Up to three qubits: measure along X, Y or Z in all 27 combinations (1,000 shots
each, readout error included and then inverted), estimate every Pauli
expectation, invert to a density matrix and project it onto physical states
(Smolin, Gambetta and Smith 2012). Shown as two 3D cityscapes, intended vs
rebuilt, with the fidelity, the purity and how much of the gap is hardware noise
and how much is finite shots.

### Error-correction lab

A logical qubit spread over three, every qubit flipped with probability p, then
decoded (two CNOTs and a Toffoli: syndrome measurement and correction in
deferred form). With perfect gates the logical error is 3p² − 2p³, simulated
and checked against that formula; with realistic gates the code's own gates
put a floor under it, so it only beats a bare qubit above a break-even rate
(10.8% today, 0.87% with gates ten times better). Against phase flips the same
code is worse than no code. The bit-flip code example in the gallery shows a
single error being corrected, gate by gate.

### Challenges

Each puzzle is defined by a reference circuit kept on the server: its state (or,
for gate puzzles, its unitary) is the target, compared up to global phase, so
any correct answer counts. Solved means fidelity at least 0.999; stars are
solved, within par + 2, at or under par. Near misses get a specific note: "the
probabilities are already right; a relative phase is off", or "2 of 4 basis
inputs already map correctly". On success the panel shows what the puzzle
teaches and how much of the state survives realistic noise; Run then sends the
answer through the full agent and verifier. Puzzles: fair coin, minus sign,
quarter turn, NOT without X (H and Z only), Bell pair, singlet, hidden phase
(a graph state), GHZ, SWAP from CNOTs, CZ from one CNOT, and the W state.

### Benchmark

[`docs/BENCHMARK.md`](docs/BENCHMARK.md): every example circuit, clean and with
every fault that can be planted in it, under realistic noise. **55 of 55 runs end
correctly**: all 37 repairable faults verified after one repair, all 9 faked
results caught. Regenerate with `scripts/benchmark.py`.

## Limitations (stated honestly)

- Verification compares measurement statistics. It cannot see a pure phase error
  that does not change the outcome distribution, and it does not catch changes
  smaller than the threshold (e.g. an angle off by a few degrees). See D8.
- Feed-forward (mid-circuit measurement, reuse, reset, conditions on several bits) is supported in the run, the
  verifier, the editor, descriptions and IBM runs, but each classical bit is written once, a reset cannot itself be
  conditional (measure and flip instead), and the tools built on a single state (step-through, live state, optimizer,
  proof sheet, Rosetta exports) refuse these circuits. Sketches do not produce conditions yet; add them in the editor.
  Circuits are capped at 12 qubits (10 counting the qubits the exact model adds).
- The code sandbox is a guard rail (AST check, subprocess, timeout, scrubbed
  environment), not an OS-level sandbox. Run untrusted model output on a machine
  you control.
- The network model is analytic and simplified: purification is the simple BBPSSW
  recurrence (no nested schemes), no multi-pair emission, no time-varying satellite passes, lumped atmospheric loss.
  Its numbers are order-of-magnitude, not engineering predictions.
- Offline mode recognises only the three bundled sketches; reading your own photo
  needs the live Meta models. Offline, descriptions in words are limited to named
  algorithms, gate lists and simple networks, explanations are English only, and
  questions are answered by topic from the run's facts. The live adapters were
  exercised end to end against the Meta Model API with fallback off (D34);
  `pytest -m live` repeats a cheap check of each model.
- The Muse Code CLI backend is opt-in and untested here (the CLI was not installed).
- The quantum internet scores fiber over the great-circle distance (real cables run longer), uses the network
  model's first-generation repeaters, and treats a satellite as a trusted node scored by its clear-sky key from the
  next 24 hours of real passes; its numbers change with the orbits and the weather.
- The lecture checker reads the board from its last frame, so a part erased during the lecture is not judged; it takes videos of at most 60 seconds, and claims outside its five kinds (probability, possible outcomes, entangled, not entangled, a named state) are listed as not checkable. The bundled sample uses synthetic voices. Offline, only that sample can be checked.

## Built during the hackathon

Everything in this repository, and everything the demo video shows, was built
during the hackathon's building period (Oct 27 to Nov 4, 2026). Nothing was
carried over from an earlier project. The git history is the record: the first
commit (`a892217`, the spec format) is from Oct 27, 2026 at 14:57 ET. Until Nov 3
the project's working name was Q-Canvas, which older commit messages still use; it
was renamed because an unrelated QCanvas already exists (decision D82).

| Day (ET) | What was built |
| --- | --- |
| Oct 27 | Spec format, code generation, noise-aware verification, the self-repair agent, sketch reading with SAM 3.1 and Muse Spark, the API, the React app, explanations and diagrams, the quantum network model |
| Oct 28 | Algorithm gallery, gate-by-gate inspector and circuit analyses, entanglement purification, describe in words, ask about a run, chip routing, 12 languages, HTML reports, the planted-fault benchmark |
| Oct 29 | Challenge mode, 3D Bloch spheres, the optimizer with exact proofs, zero-noise extrapolation, Bell tests, tomography, the error-correction lab, voice input |
| Oct 30 | First live run against the Meta Model API, Shor's algorithm, Muse Voice Transcribe, the QAOA party lab, the bug hunt |
| Oct 31 | AI alone vs Inkubit, the molecule lab, the BB84 spy lab, use cases with Muse Image photos, Ask Inkubit (tool calling) with a Muse Wonder deep mode, the demo video |
| Nov 1 | The Quantum Rosetta: Dirac notation both ways, exact OpenQASM, Quil and Qiskit readers, proven state preparation, eight output languages, the quantum dictionary, photos of notation; the simulation observatory; Muse Image illustrations for the use-case cards; mission control (multimodal planning, parallel execution, repair, verification, traced reports); the ML verifier; seven more algorithms; the discovery lab, distributed computer, resource estimator, live board, satellite planner, paper reproducibility checker, ML decoder and pulse lab |
| Nov 3 | IBM Quantum in the app (live calibration maps, a placement advisor, runs from the editor), the proof sheet, eight more algorithms and a calibrated noise preset; the rename to Inkubit; the opening scene in 3D; feed-forward (mid-circuit measurement, conditions on several bits, reset and reuse) in the format, the verifier, the editor and IBM runs; the redesign |
| Nov 4 | The lecture checker (Muse Voice diarization, SAM 3.1 video tracking, claims judged exactly, Muse Wonder notes) and proven illustrations (Muse Image figures read back and corrected with image edits) |

## Third-party code and assets

- **Libraries**, installed from PyPI and npm and never copied into the repo:
  Qiskit and Qiskit Aer (Apache-2.0), NumPy (BSD), Matplotlib (PSF-based),
  pylatexenc (MIT), Pillow (MIT-CMU), pydantic (MIT), FastAPI (MIT), Uvicorn
  (BSD), sse-starlette (BSD), python-multipart (Apache-2.0), python-dotenv
  (BSD), httpx (BSD), qiskit-qasm3-import (Apache-2.0), pytest (MIT); React (MIT), three.js (MIT), Vite (MIT), TypeScript
  (Apache-2.0). Playwright (Apache-2.0) and imageio-ffmpeg (BSD) are used only
  by the screenshot and video scripts; Cirq (Apache-2.0) only by the tests and the Rosetta's check of its Cirq
  output, when installed.
- **Fonts:** IBM Plex Sans and IBM Plex Mono from Google Fonts (SIL Open Font License).
- **Images:** the sample sketches, the section tabs' doodles and the use-case cards' sketches are drawn by
  `scripts/make_sketches.py`, `scripts/make_tab_sketches.py` and `scripts/make_card_sketches.py`; the screenshots
  and the video are of this app. (`scripts/make_usecase_art.py` made the earlier Muse Image card art, kept for the
  record.)
- **Science:** physical constants and textbook values (STO-3G basis parameters,
  the H₂ reference energies, the Micius satellite geometry, the BB84 abort
  threshold) are facts from the cited literature, implemented from scratch.
- **Meta docs:** the Meta Model API pages were read while building
  (`docs/meta-api/SOURCES.md` lists them); they are not redistributed here.

## License

MIT, see [LICENSE](LICENSE).

## Repository guide

- `PROGRESS.md`: what is done, what is next. `DECISIONS.md`: every design decision and why.
- `DEMO_SCRIPT.md`: the 2-3 minute video shot list.
- `docs/hackathon/SUMMARY.md`: dates, tracks and judging criteria.
- `scripts/make_sketches.py`: regenerates the sample sketches and fixtures.
- `scripts/capture_ui.py`: drives the UI headlessly and refreshes `docs/screenshots/`.
- `scripts/record_demo.py`: records the captioned demo video from the real app.
- `scripts/benchmark.py`: the planted-fault benchmark (`docs/BENCHMARK.md`).
- `SUBMISSION.md`: ready-to-paste hackathon submission text.
