# Submission text (ready to paste)

Fill the video link, then paste each block into the matching form field.
Every number below comes from a run of this repo.

**Track:** Indie developer · **Problem statement:** Push the Frontier (accelerate a scientific experiment; understand and control a physical system)

**Demo video:** `<YouTube / Loom link>` · **Code:** https://github.com/Dhruv-Deku/inkubit (public, MIT) · **Try it:** `<hosted app link>` (public mode: model-written code is never executed, live calls capped per day)

## At a glance (for judges)

Inkubit is a quantum lab where Meta's models read, plan and propose, and exact physics checks every number before
anyone sees it. Press **Guided tour** in the app for the best of it in under two minutes.

| Criterion | What to look at |
| --- | --- |
| **Creativity** | An **AI scientist that learns under proof**: Muse Spark designs circuits in rounds, sees what exact physics said, and its best proven circuit improves on every target, where the same model without feedback never does. **AI-designed error-correcting codes**: a 9-qubit code that needs 9 phase-flip errors to fail, three times the surface code. **Mission control** turns one request (typed, spoken or photographed) into a live graph of exact tools that runs in parallel and verifies itself. A **discovery lab** where Muse Spark proposes circuits and Qiskit proves them (a GHZ state on 7 qubits of an IBM chip in 6 CNOTs; the textbook circuit needs 10). The quantum-key **satellites in orbit today** flown live on their real orbits under tonight's cloud forecast. A camera on a **whiteboard**; a **whole paper** from its PDF re-run claim by claim; an **AI referee** where Muse Wonder challenges Muse Spark and exact simulation decides |
| **Technical ambition** | Exact density-matrix simulation, checked against Qiskit Aer. A **distance-5 surface code**: the bigger code suppresses errors 5.9x per round (Λ; Google's Willow measured 2.14), and a network on top of matching makes 10% fewer logical errors (paired test z = 7.8). A three-level transmon with **DRAG** pulses. **SGP4** orbits matching Skyfield to 0.003°. Surface-code **resource estimates** within 1.3x (qubits) and 2.3x (time) of the published RSA-2048 figure |
| **Does it work** | **On a real IBM quantum computer** (ibm_fez): Muse Spark's discovered GHZ circuit beat the textbook circuit on the same seven qubits, GHZ fidelity 0.814 against 0.795 (3.2 standard errors), both certifying genuine 7-qubit entanglement; a noise preset calibrated from the chip predicted its counts closer than a digital twin on 4 of 4 circuits. A 30-mission **live benchmark**: 30 of 30 finished, 68 of 68 steps verified, 204 of 209 report numbers traced to a tool, median 15 s. **546 backend tests and 6 browser tests** run in CI on every push; a fresh clone runs from the README alone. The hosted copy above |
| **Use of Meta models** | **Five Meta models**, each where it is strongest: Muse Spark plans, reads photos, writes and repairs code, calls tools and writes traced reports; Muse Wonder takes the long multi-step questions; SAM 3.1 segments sketches and whiteboards; Muse Image illustrates; Muse Voice Transcribe takes speech (Muse Glimmer, Meta's open-weight model, also runs on a laptop through the same client, but at about 1.6 tokens a second it is too slow to drive the app). And the measured reason none of their answers reaches you unchecked: alone, Muse Spark was exact on small circuits but on only 3 of 6 bigger ones, once 43% off with full confidence |

## Built during the hackathon

Everything in the repository and in the video was built during the building period, Oct 27 to Nov 4, 2026, by one developer. Nothing was carried over from an earlier project: the first commit (the spec format) is from Oct 27 at 14:57 ET, and the README has a day-by-day table taken from the git log. Until Nov 3 the working name was Q-Canvas, which older commit messages still use; it was renamed because an unrelated QCanvas already exists. Third-party code is limited to open-source libraries installed from PyPI and npm (Qiskit, Qiskit Aer, FastAPI, React and others, all listed in the README); the images were generated with Muse Image or drawn by the repo's own scripts.

## Project name

Inkubit

## Tagline (one line)

Sketch it, say it or photograph it: Meta's models turn a quantum idea into a
plan, and exact physics checks every number before you see it.

## Short description (about 50 words)

Inkubit is a quantum lab where the AI never gets the last word. Meta's models
read sketches, photos, papers and speech, plan multi-step experiments and
propose circuits; exact simulation, independent re-runs and physics checks
verify every result, from a drawn Bell pair to a distance-5 surface code and
real satellites in orbit tonight.

## Full description

**The problem.** A wrong quantum program still runs. A reversed CNOT or an
off-by-one qubit index prints a perfectly plausible histogram; it is just the
wrong one. Students and researchers sketch circuits and network layouts on paper
long before they write code, and the jump from sketch to *correct* code is where
the time goes.

**What Inkubit does.**

1. **Reads the sketch.** Muse Spark looks at the photo and decides what to look
   for; SAM 3.1 boxes every gate, dot, circle and meter; Muse Spark reads the
   photo plus the numbered boxes into a validated JSON spec, with every
   operation linked to the box it came from. The user can check and correct it
   side by side, with readable validation as they type.
2. **Writes and runs the code.** Muse Spark writes a standalone Qiskit script,
   which runs in a sandboxed subprocess under a realistic superconducting noise
   model.
3. **Proves it.** A separate code path computes the exact distribution the spec
   should produce under the same noise (density matrix plus exact readout
   error), never looking at the generated code. The run passes only if its
   distance from that prediction is inside a threshold derived from shot noise.
   Example: Bell pair, distance 0.004 against a limit of 0.040.
4. **Repairs itself.** On a failure the agent explains why in plain words
   ("the two bits should agree and don't, so the entangling gate is missing"),
   hands Muse Spark the spec, the code, the error and that evidence, and runs
   the fix. Up to four attempts; if it cannot fix the code it says **Not
   verified** instead of faking success. Demo mode plants one of six real bugs
   so judges can watch the loop work.
5. **Explains it.** Muse Spark explains the result to a student using the real
   numbers, in any of 12 languages; Muse Image draws a clean diagram, always
   shown next to the exact Qiskit drawing so it can never mislead. You can then
   ask Muse Spark questions about the run ("why did attempt 1 fail?"), answered
   only from that run's numbers.
6. **Shows what happens inside.** Step through the exact quantum state gate by
   gate, with a Bloch sphere per qubit; see how much entanglement survives the
   noise, which noise source costs the most, how much better the hardware must
   get for a 99% match (a Bell pair needs about 7x), what readout correction
   recovers, and how many SWAPs real chip wirings add.

**Ask it anything.** "Ask Inkubit" is one assistant for the whole lab, typed
or spoken (Muse Voice Transcribe). Muse Spark, or Muse Wonder for questions that
take several steps, chooses among nine exact tools (circuit simulation, the
optimizer, the H₂ molecule, BB84 key distribution, QAOA Max-Cut, Shor's
algorithm, network links, error correction, the Rosetta), calls them in parallel when it
needs several, and answers with live result cards. The model is told never to
work out a result itself, and afterwards every number in its answer is matched
against the tool results: the page shows "13 of 13 numbers traced" or lists the
ones that were not. Every live answer so far traced completely (3 of 3, 5 of 5,
14 of 14; Muse Wonder 13 of 13, with two tool calls in parallel, in 8.9 s).

**Speak quantum: the Quantum Rosetta.** The hardest part of quantum computing
for newcomers is its language: kets, gates, five programming languages. The
Rosetta translates between all of them, both ways, and checks every
translation. Type, paste, say or photograph a state or a program: Dirac
notation such as (|01⟩ − |10⟩)/√2 or LaTeX pasted from a paper, OpenQASM 2 or
3, Quil, Qiskit, Cirq, PennyLane, Q#, Braket, or plain words. Out comes the
state written like a textbook (independent qubits factored out, which qubits
are entangled, LaTeX to copy), a circuit that prepares it, proven by exact
simulation (fidelity 1.000000), a sentence for every gate saying what it did to
this state, and the same program in eight languages; the Qiskit, OpenQASM and
Cirq versions are run and must reproduce the same state. Muse Spark is used only
where an exact parser cannot be: other code languages and photos of a textbook
or whiteboard, which it transcribes without solving. A 28-word dictionary gives
every term an example state computed exactly.

**Why check at all? We measured it.** Asked to predict circuits on its own, the
way a chatbot answers, Muse Spark was exact on 13 of 13 textbook circuits and 10
of 11 new small ones. On bigger new circuits (6 to 8 qubits) it was exact on 3
of 6, and once confidently put 43% of the probability in the wrong place
(docs/ARENA.md). Inkubit never relies on that: the model drives the
simulation, and the simulation gives the answer.

**Three labs from first principles.** *Chemistry:* the H₂ molecule from
closed-form integrals. Stretched to 2.5 Å, Hartree-Fock is off by 233 mHa; VQE
on realistic noisy hardware is off by 21 mHa, and undoing the calibrated noise
brings it to 0.8 mHa from the exact energy (shot-noise error bar 2.1 mHa at
4,000 shots). *Security:* BB84 with an eavesdropper; her measurements raise the
error rate, above 11% the key is thrown away, and below it the key is shortened
to what she cannot know. *Optimization:* QAOA seats feuding guests at two
tables (Max-Cut, the shape of scheduling and routing problems) with a clickable
landscape of angles; three layers find a best seating 95% of the time with
perfect qubits and about half the time with realistic noise.

**Bug hunt.** One gate in a circuit is wrong; the player finds it from the
histogram, against the clock and against Muse Spark playing the same round. An
exact search of every one-gate edit grades it, so any gate whose fix restores
the odds counts.

**An AI scientist that learns under proof.** Muse Spark proposes circuit layouts in rounds; an exact optimiser
judges each one and Qiskit proves every winner; the verdicts go into the next prompt. With that feedback its best
proven circuit improved on all three targets (6 to 5, 6 to 5 and 8 to 7 CNOTs); the same model asked afresh never
improved on its first answer and kept repeating itself; random wiring of the same lengths never reached a target.

**AI-designed error-correcting codes.** An exact checker scores any stabilizer code (commutation, independence, the
distance by brute force over every error, and the distances against X-only and Z-only noise), the textbook codes
included. Muse Spark designed the five-qubit perfect code and a [[7,1,3]] CSS code in its first round, and for
hardware where phase flips dominate it found, in its second round, a 9-qubit code that needs 9 Z errors to fail,
three times the surface code's 3, while still correcting any single error.

**Reproduce a whole paper.** Give an arXiv id or a PDF: Muse Wonder reads the whole paper and lists its experiments,
Muse Spark transcribes each from its pages, and exact simulation judges every stated probability. On a 100-page
paper (arXiv:1804.03719) it found 8 experiments and reproduced 3 of the 5 it could check, 11 of 19 numbers, in
under two minutes, and said which circuits the paper does not specify completely instead of guessing them.

**The AI referee.** Muse Spark answers three questions about a circuit, Muse Wonder challenges, and exact simulation
grades every position. Over 24 answers, debate raised Muse Spark from 17 to 19 right, but Muse Wonder also raised 5
false alarms and talked it out of 2 right answers: models arguing catch mistakes and make new ones, and only the
simulator knows which. That is why Inkubit checks instead of debating.

**IBM Quantum, from calibration to experiment.** The app maps 3 IBM Heron chips qubit by qubit from their own calibration,
and an advisor scores every way to place a circuit on them. On ibm_fez, the same 5-qubit GHZ circuit on the advisor's best,
median and worst qubits measured 0.894, 0.814 and 0.285, exactly its order (on the worst it no longer shows
entanglement). Teleportation with real mid-circuit measurement and feed-forward reached an average fidelity of 0.924
over the six axis states, against 0.667 for any classical scheme. With a token, any circuit in the editor runs on IBM.

**On a real quantum computer.** The discovery lab's proven circuits ran on IBM's ibm_fez next to the circuits they beat
(23 circuits, 4096 shots each). On seven qubits wired like a heavy-hex chip, Muse Spark's GHZ circuit used 6 two-qubit gates
where the textbook needs 10, and a parity-oscillation measurement gave a GHZ fidelity of 0.814 against 0.795, 3.2 standard
errors apart; both are above 1/2, so both certify genuine 7-qubit entanglement. For W and Dicke states the discovered
circuits used 8 two-qubit gates against 17 and tied within shot noise, and the page says tie. A fourth noise preset,
calibrated from the chip's own reported errors, predicted four earlier circuits closer than a digital twin did.

**Discovery lab: AI proposes, physics proves.** Muse Spark proposes CNOT layouts, an exact optimiser fits
them, Qiskit proves every winner, the ML verifier screens and exact noisy simulation decides. It found a GHZ state on
all 7 qubits of an IBM heavy-hex chip in 6 CNOTs (the textbook circuit compiled onto the chip needs 10) and W and
Dicke(4,2) states in 5 CNOTs where Qiskit's compiler uses 11.

**Down to the hardware and out to orbit.** A distributed quantum computer splits a circuit over two chips joined by
a link from our network model and shows what every remote CNOT costs from 10 m to 100 km. A pulse lab simulates the
X gate as the microwave pulse on a three-level transmon (DRAG: 1.1e-4 error at 15 ns). A satellite planner flies the
quantum-key satellites in orbit today (SpeQtre, QUBE-II) live on their real orbits, from today's CelesTrak elements
with SGP4, and weighs every night pass by the cloud forecast; Micius, re-entered in January 2026, replays 2017. A neural surface-code
decoder makes 21% fewer logical errors than minimum-weight matching at 1% noise, beyond its error bars; at
distance 5 the bigger code suppresses errors 5.9x per round and a network on top of matching, fed where both kinds of
matching put their corrections, makes 10% fewer logical errors again (paired test z = 7.8).

**Honest about where quantum wins.** Describe a problem; Muse Spark maps it to an algorithm and a surface-code
resource estimate meets the best classical route, checked against Gidney and Ekerå's RSA-2048 figure. Brute-force
search on 2^64 keys: classical wins. Upload a figure from a paper: Muse Spark transcribes circuit and claims, an
exact re-run judges every number against its error bar. Point a camera at a whiteboard: the odds appear on the wires.

**Mission control: whole problems, planned, run live and verified.** Type, say or
photograph a whole problem ("connect two cities 1,200 km apart with quantum-secure
keys, compare satellite and fiber, and check whether a spy on 25% of the photons is
caught"). SAM 3.1 and Muse Spark read the photo; Muse Spark plans a dependency graph
of exact tools under a JSON schema; independent steps run in parallel and light up
a live graph; a failed step is repaired once by the model; every result is checked
by physics invariants and, for circuits, by two independent noisy simulators and the
ML verifier; Muse Spark writes the report and every number in it is traced. In a
30-mission live benchmark every mission finished, all 68 steps were verified and 204 of
209 report numbers were traced to a tool result (docs/MISSIONS.md); median 15 seconds.

**ML verifier.** A neural-network ensemble trained on 6000 circuits labelled by
exact simulation predicts in about 151 µs how much of an answer survives
today's noise: on 900 held-out circuits its average error is 0.010, 9 times smaller than the product-of-gate-fidelities rule of thumb (0.087) and below a global-depolarizing physics model (0.013); its 90% interval held for 90% of them and for 78% of 60 textbook cases it never saw (error 0.020). Every prediction up to 10 qubits is checked exactly, and a
miss is shown as a note about the model, never a change to the result.

**25 algorithms in 8 categories.** From the QFT finding a period and Simon's algorithm to quantum counting, an HHL
solver (A⁻¹b in the ratio 9 : 1), a Fourier-space adder, hidden shift, Shor's nine-qubit code correcting a Y error and
two nonlocal games (CHSH won cos²(π/8) of the time; the GHZ game won every time), each checked against its known answer.

**The proof sheet.** One button runs 11 independent checks of 9 kinds on any circuit: two simulators of each kind,
a physical density matrix, translation validation of Qiskit's compiler, OpenQASM read-back, a G-test on sampled
shots, the generated code in the sandbox and metamorphic tests. Over the gallery: 299 passed, 0 failed.
Its first run found a real bug: the OpenQASM 2 export used gates the standard library does not define.

**What it can do.** Nine cards on the start page (sketch to code, debugging,
chemistry, quantum security, optimization, satellite networks, cryptography,
real hardware, trust), each illustrated by Muse Image in the same flat technical
style as the pipeline's diagrams, and each one click into the real feature.

**Simulation observatory.** Five exact simulations of where quantum technology
stands, each with its key number written out. Satellites vs fiber: from the
network planner's own model, fiber gives no secret key beyond 500 km while a
satellite 500 km up still delivers 0.017 bits per second at 2,400 km (Micius's
1,203 km marked). Grover vs noise: 2 to 5 qubits compiled to CNOTs and evolved
as exact density matrices; at 5 qubits (72 CNOTs per query) today's noise erases
the speedup. A quantum walk you can play step by step, entanglement growing to
Page's limit in random circuits, and the exponential memory wall.

**Shorter circuits, proven equal.** One click races rewrite rules (each with
a reason a student can check), the Qiskit compiler and Muse Spark to find a
cheaper circuit. Exact simulation then proves each proposal gives the same gate,
the same state or the same measured odds, or rejects it with the outcome that
differs; a rejected Muse Spark proposal goes back once with that reason. Fewer
gates means less noise, and the panel shows by how much (phase estimation goes
from 15 two-qubit gates to none, and the panel explains why: its answer was
fixed in advance).

**Error mitigation.** Zero-noise extrapolation folds every gate to run the
circuit at 3x and 5x its noise, then extrapolates back to zero: a Grover search
goes from a 0.882 match as measured to 0.999. It is shown with exact
probabilities and with 4,000 shots per level, because extrapolation amplifies
shot noise and the honest question is whether it pays off.

**Is it really quantum?** For every entangled pair Inkubit runs a Bell test
(CHSH; Mermin for three qubits) ideal, with realistic noise, and from simulated
shots with error bars: a Bell pair still beats every classical explanation by
16 standard errors on realistic hardware, and a W state shows that no pair
needs to violate for the trio to. State tomography rebuilds the state from
27 measurement settings, as a lab must, and draws it as a 3D density-matrix
cityscape. An error-correction lab shows where the bit-flip code starts to beat
a bare qubit, and how that break-even point falls as the gates improve.

**Play with it.** Eleven challenges (make a Bell pair, a singlet, a W state;
build SWAP from CNOTs or NOT from H and Z) are scored exactly against a hidden
reference, with par like golf, stars, and a lesson on success. Muse Spark gives
hints from the player's exact score without ever seeing the solution. You can
solve them by clicking gates onto wires, by describing the answer, or by
drawing it on paper and taking a photo. A live state strip shows 3D Bloch
spheres (drag to turn) with each qubit's path and an entanglement web (gold
threads between entangled pairs; GHZ states drawn as one group), recomputed on every edit, and a
slider shows how the outcome changes as the hardware gets better or worse.
Network results are drawn as an animated map, before and after the fix.

**More ways in.** Besides a photo or the camera, you can describe a design in
words (typed or spoken) ("Bernstein-Vazirani with secret 1011", "300 km of fiber with 2
repeaters") and Muse Spark builds the spec. The gallery includes Grover search,
Bernstein-Vazirani, Deutsch-Jozsa, phase estimation, superdense coding,
teleportation, the W state and a Toffoli AND, each verified against its textbook
answer. Any design can be shared as a link or downloaded as a one-file HTML
report.

**Quantum networks.** The same canvas plans entanglement-distribution networks.
Inkubit models every link from physics (fiber attenuation; satellite downlinks
with diffraction, turbulence and atmosphere; Werner-state fidelity; quantum
memory decoherence; entanglement swapping; BBM92 secret-key rate), finds the
bottleneck, tries real fixes (relays, higher passes, bigger telescopes, better
memories, entanglement purification), re-simulates each one and keeps the best. On the bundled satellite
case, close to the 2017 Micius experiment's geometry, the agent raises the
secret-key rate from 0.013 to 1.87 bit/s (pairs 0.83 to 7.4 per second,
fidelity 0.86 to 0.94), and every result passes physics sanity checks. On a
600 km repeater chain that cannot make a key at all, it discovers that
purification only pays off after the memories are upgraded, and gets there.

**Reliability.** A benchmark plants every fault in every gallery circuit: 55 of
55 runs end correctly (37 of 37 repairable bugs fixed, 9 of 9 faked results
caught).

**Honest by design.** Every model answer in the UI names the model that produced
it. If a live call fails, the app falls back to a deterministic offline mock and
labels the result "mock fallback". Responses are cached on disk, so demos are
repeatable and cheap.

## How we used Meta's models

| Model | Job |
| --- | --- |
| **SAM 3.1** (`/v1/responses`) | Concept-prompted segmentation of every drawn part, with confidences, scaled onto the photo; the same for each new frame of the live whiteboard camera |
| **Muse Spark 1.3** (`/v1/chat/completions`, JSON-schema output) | Chooses what SAM should look for; reads photo plus numbered boxes into the spec (re-prompted with validation errors if invalid); turns a plain-language description into a spec; writes and repairs the Qiskit code; explains the result in 12 languages; answers questions about a run from its facts; gives challenge hints; proposes shorter circuits that exact simulation must prove; drives Ask Inkubit with tool calling over nine exact tools; plans, repairs and reports Mission control's tool graphs under JSON schemas; proposes circuit layouts in the discovery lab; maps a problem in words to an algorithm and hardware for the resource estimator; transcribes a paper's figure, circuit and claims for the reproducibility checker; reads the whiteboard; reads Cirq, PennyLane, Q# and Braket code and photos of notation for the Quantum Rosetta (transcribed, never solved); plays the bug hunt; predicts circuits alone for the AI-alone comparison |
| **Muse Wonder 1.0** (`/v1/chat/completions`, tools, `reasoning_effort: medium`) | Deep mode of Ask Inkubit: plans longer chains of tool calls (up to six rounds) for questions that take several steps; same tools, same number tracing |
| **Muse Image 1.0** (`/v1/images/generations`) | Clean illustration of the final circuit or network, always shown next to the exact drawing; the nine use-case photos |
| **Muse Voice Transcribe 1.0** (`/v1/asr/transcribe`) | Voice input for the assistant and for describing a design: a 16 kHz WAV recorded in the browser, with quantum keywords (qubit, Hadamard, CNOT, GHZ, Shor) to bias the recogniser |
| **Muse Code** (opt-in, experimental) | Alternative repair backend: the verifier, not the agent's exit code, decides if a fix worked |

Tested live end to end: all three sample sketches read correctly (SAM 3.1 finds
the parts, Muse Spark fills in what it missed and says so), Muse Spark's Qiskit
code verified on the first attempt, and explanations come back in each
language's own script. On the two-qubit Grover example, whose answer is fixed
in advance, Muse Spark noticed the circuit only ever produces |11> and proposed
two X gates; exact simulation proved it, where rewrite rules plus Qiskit's
level-3 transpiler stopped at 7 gates.

## How it's built

Python 3.13, FastAPI, Qiskit 2.6 + Aer, PyMatching, SGP4, pydantic v2, server-sent events for the
live agent log; React 19 + TypeScript + Vite. 546 offline backend tests (spec
validation, codegen, verification statistics, the repair loop with every planted
fault, exact insights checked against Aer, network physics, orbits against Skyfield, the live adapters
against recorded request shapes, API) and 6 end-to-end browser tests of the built app, all in CI on every
push. Every model sits behind an adapter with a real and a mock implementation; a Dockerfile and a deploy
script publish the public mode to a Hugging Face Space.

## Challenges

- Making verification trustworthy: the threshold has to separate a real bug
  from shot noise, so it is derived from the multinomial standard error and
  justified in DECISIONS.md, never loosened to make a test pass.
- Hand-drawn strokes are hard for a photo-trained segmenter, so Muse Spark also
  reports its own box for each element; the overlay labels which model found
  what.
- Keeping the network model physical rather than decorative: every fix is
  re-simulated, and results are checked against physical bounds.

## What's next

Calibrated twins per device and per qubit patch (the median-calibrated preset already beats the generic one), circuit-level
noise for the decoders, mid-circuit measurement (teleportation, error-correction codes), and multi-page lab-notebook
sketches.
