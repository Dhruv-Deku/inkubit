# Submission text (ready to paste)

Fill the two links, then paste each block into the matching form field.
Every number below comes from a run of this repo; re-check them after the
live-mode recording.

**Track:** Indie developer · **Theme:** Push the Frontier

**Demo video:** `<YouTube / Loom link>` · **Code:** `<GitHub link>`

## Project name

Q-Canvas

## Tagline (one line)

Draw a quantum circuit or a satellite link on paper; get a simulation that is
checked, repaired and explained.

## Short description (about 50 words)

Q-Canvas turns a photo of a hand-drawn quantum circuit or quantum network into a
running simulation. SAM 3.1 finds every drawn part, Muse Spark reads the sketch
into a spec and writes the Qiskit code, and an independent verifier proves the
result is right. When it is wrong, the agent diagnoses the failure and repairs
the code, live on screen.

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
   numbers; Muse Image draws a clean diagram, always shown next to the exact
   Qiskit drawing so it can never mislead.

**Quantum networks.** The same canvas plans entanglement-distribution networks.
Q-Canvas models every link from physics (fiber attenuation; satellite downlinks
with diffraction, turbulence and atmosphere; Werner-state fidelity; quantum
memory decoherence; entanglement swapping; BBM92 secret-key rate), finds the
bottleneck, tries real fixes (relays, higher passes, bigger telescopes, better
memories), re-simulates each one and keeps the best. On the bundled satellite
case, close to the 2017 Micius experiment's geometry, the agent raises the
secret-key rate from 0.013 to 1.87 bit/s (pairs 0.83 to 7.4 per second,
fidelity 0.86 to 0.94), and every result passes physics sanity checks.

**Honest by design.** Every model answer in the UI names the model that produced
it. If a live call fails, the app falls back to a deterministic offline mock and
labels the result "mock fallback". Responses are cached on disk, so demos are
repeatable and cheap.

## How we used Meta's models

| Model | Job |
| --- | --- |
| **SAM 3.1** (`/v1/responses`) | Concept-prompted segmentation of every drawn part, with confidences, scaled onto the photo |
| **Muse Spark 1.3** (`/v1/chat/completions`, JSON-schema output) | Chooses what SAM should look for; reads photo plus numbered boxes into the spec (re-prompted with validation errors if invalid); writes and repairs the Qiskit code; explains the result |
| **Muse Image 1.0** (`/v1/images/generations`) | Clean illustration of the final circuit or network |
| **Muse Code** (opt-in, experimental) | Alternative repair backend: the verifier, not the agent's exit code, decides if a fix worked |

## How it's built

Python 3.13, FastAPI, Qiskit 2.6 + Aer, pydantic v2, server-sent events for the
live agent log; React 19 + TypeScript + Vite. 116 offline tests (spec
validation, codegen, verification statistics, the repair loop with every planted
fault, network physics, API). Every model sits behind an adapter with a real and
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

Running verified circuits on real quantum hardware, purification in the network
model, and multi-page lab-notebook sketches.
