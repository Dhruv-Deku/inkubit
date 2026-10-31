# Submission text (ready to paste)

Fill the video link, then paste each block into the matching form field.
Every number below comes from a run of this repo.

**Track:** Indie developer · **Problem statement:** Push the Frontier (accelerate a scientific experiment; understand and control a physical system)

**Demo video:** `<YouTube / Loom link>` · **Code:** https://github.com/Dhruv-Deku/q-canvas (public, MIT)

## Built during the hackathon

Everything in the repository and in the video was built during the building period, Oct 27 to Nov 4, 2026, by one developer. Nothing was carried over from an earlier project: the first commit (the spec format) is from Oct 27 at 14:57 ET, and the README has a day-by-day table taken from the git log. Third-party code is limited to open-source libraries installed from PyPI and npm (Qiskit, Qiskit Aer, FastAPI, React and others, all listed in the README); the images were generated with Muse Image or drawn by the repo's own scripts.

## Project name

Q-Canvas

## Tagline (one line)

A quantum lab you can draw on and talk to: Meta's models drive exact
simulations, and every number they say is checked.

## Short description (about 50 words)

Q-Canvas is a quantum lab you can draw on, talk to, and read: it translates
the language of quantum computing both ways. Sketch a circuit or a satellite
link, write a ket, describe it, or ask by voice: SAM 3.1, Muse Spark, Muse Wonder
and Muse Voice Transcribe turn it into exact simulations of circuits, molecules,
secret keys and networks, and every number the AI says is checked against them.

## Full description

**The problem.** A wrong quantum program still runs. A reversed CNOT or an
off-by-one qubit index prints a perfectly plausible histogram; it is just the
wrong one. Students and researchers sketch circuits and network layouts on paper
long before they write code, and the jump from sketch to *correct* code is where
the time goes.

**What Q-Canvas does.**

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

**Ask it anything.** "Ask Q-Canvas" is one assistant for the whole lab, typed
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
(docs/ARENA.md). Q-Canvas never relies on that: the model drives the
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

**Who it is for.** Nine use cases on the start page (teacher, student, chemist,
security, logistics, network planner, cryptographer, researcher, skeptic), each
with a photo generated by Muse Image and a button that opens the real feature.

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

**Is it really quantum?** For every entangled pair Q-Canvas runs a Bell test
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
Q-Canvas models every link from physics (fiber attenuation; satellite downlinks
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
| **SAM 3.1** (`/v1/responses`) | Concept-prompted segmentation of every drawn part, with confidences, scaled onto the photo |
| **Muse Spark 1.3** (`/v1/chat/completions`, JSON-schema output) | Chooses what SAM should look for; reads photo plus numbered boxes into the spec (re-prompted with validation errors if invalid); turns a plain-language description into a spec; writes and repairs the Qiskit code; explains the result in 12 languages; answers questions about a run from its facts; gives challenge hints; proposes shorter circuits that exact simulation must prove; drives Ask Q-Canvas with tool calling over nine exact tools; reads Cirq, PennyLane, Q# and Braket code and photos of notation for the Quantum Rosetta (transcribed, never solved); plays the bug hunt; predicts circuits alone for the AI-alone comparison |
| **Muse Wonder 1.0** (`/v1/chat/completions`, tools, `reasoning_effort: medium`) | Deep mode of Ask Q-Canvas: plans longer chains of tool calls (up to six rounds) for questions that take several steps; same tools, same number tracing |
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

Python 3.13, FastAPI, Qiskit 2.6 + Aer, pydantic v2, server-sent events for the
live agent log; React 19 + TypeScript + Vite. 355 offline tests (spec
validation, codegen, verification statistics, the repair loop with every planted
fault, exact insights checked against Aer, network physics, the live adapters
against recorded request shapes, API). Every model sits behind an adapter with a real and
a mock implementation.

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

A hosted public demo, running verified circuits on real quantum hardware, mid-circuit measurement
(teleportation, error-correction codes), nested purification schemes, and
multi-page lab-notebook sketches.
