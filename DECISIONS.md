# Decisions

Each entry: what was decided, and why. Newest last.

## D1. Project location and identity (2026-10-28)
No project folder, `.env` or `docs/meta-api/` existed. Created the project (under the working name Q-Canvas, see
D82) with its own git repo (branch `main`). Commits
use repo-local identity `DHRUV <alwaysworking.7077@gmail.com>`; change with
`git config user.email` if you prefer another address. No AI attribution lines.

## D2. Meta API docs were fetched, not invented
`docs/meta-api/` was empty, so the official Markdown docs were downloaded from
`https://dev.meta.ai/docs/*.md` (see `docs/meta-api/SOURCES.md`). All adapter code
cites those files. The docs call the key `MODEL_API_KEY`; we read `META_API_KEY`
first (the mission's name, also what Muse Code reads) and fall back to
`MODEL_API_KEY`.

## D3. Which Meta model does which job
| Job | Model ID | Endpoint |
| --- | --- | --- |
| Find drawn parts (boxes, circles, dots, dishes) | `sam-3.1` | `POST /v1/responses` |
| Read the sketch into a spec; explain results | `muse-spark-1.3` | `POST /v1/chat/completions` with `response_format` json_schema |
| Write and repair Qiskit code | `muse-spark-1.3` by default (`INKUBIT_CODE_MODEL`, e.g. `muse-wonder-1.0`) | `POST /v1/chat/completions` |
| Optional: repair through the Muse Code agent itself | `muse exec` headless CLI | local binary, opt in with `INKUBIT_CODE_BACKEND=muse-cli` |
| Clean annotated diagram | `muse-image-1.0` | `POST /v1/images/generations` |

"Muse Code" in the mission is Meta's coding agent product, which is built on
Muse Spark. Inside our app the repair agent is our own loop calling Muse Spark,
which the docs describe as the model "for agentic and coding work". Standard
mode IDs are used (not `-contributor`) so judges' and users' content is not used
for training.

## D4. Spec design
- Discriminated by `kind` (`circuit` | `network`), version `1.0`, pydantic v2,
  `extra="forbid"` so typos are reported, not silently ignored.
- Single-qubit gates may list several targets (broadcast, e.g. H on 0 and 1).
- Terminal measurements only (no gate after a qubit is measured). This keeps the
  independent expected distribution exact (statevector / density matrix).
- A circuit with no measurement is invalid: nothing to verify.
- Common aliases (`CNOT`, lower case) are normalised, because hand labels and
  model output use them.
- Validation collects every issue with a path like `operations[2] (RX)`.
- Network links use `from`/`to` in JSON (`from_node`/`to_node` in Python).
- `kind_schema()` inlines `$ref`s so structured output gets a plain-object root.

## D5. Python 3.13 venv
System Python is 3.10 (too old for the mission's 3.11+). The `py` launcher has
3.13, which Qiskit 2.6.1 and qiskit-aer 0.18.2 ship wheels for.

## D6. Generated code runs in a guarded subprocess
`sim/runner.py` runs scripts with `python -I -X utf8` in a scratch folder under
`backend/.inkubit_runs/`, a 60 s timeout, and an environment with every
`*KEY*`/`*TOKEN*`/`*SECRET*` variable removed (so model-written code can never
read the Meta key). Before running, `codegen/safety.py` parses the AST and rejects
imports outside qiskit/qiskit_aer/json/math/numpy and calls such as `open`,
`eval`, `exec`. This is a guard rail, not a full sandbox; stated in the README.

## D7. Noise presets
| preset | 1q depol | 2q depol | readout 0->1 / 1->0 | T1 / T2 |
| --- | --- | --- | --- | --- |
| ideal | 0 | 0 | 0 / 0 | none |
| low_noise | 0.05% | 0.5% | 0.5% / 1% | none |
| realistic | 0.1% | 1.5% | 2% / 4% | 100 us / 80 us (50 ns 1q, 400 ns 2q gates) |
These are ordinary numbers for current superconducting devices (readout error
larger for |1> because of T1 decay during readout). Seeds fixed: simulator and
transpiler seed 1234, 4096 shots.

## D8. Verification method and thresholds
- The verifier rebuilds the circuit from the spec with its own builder
  (`verify/expected.py`), never from generated code.
- Expected distribution is **exact and noise-aware**: density-matrix simulation
  with the preset's gate noise, then readout error applied exactly per bit.
  The ideal (statevector) distribution is also reported as "cost of noise".
- Pass iff TVD(measured, expected) <= max(floor, shot-noise bound) AND Hellinger
  fidelity >= minimum.
  - Shot-noise bound: 3/2 * sum_i sqrt(p_i (1-p_i) / N), i.e. three standard
    deviations of sampling error on every outcome at once. For Bell at 4096
    shots this is about 0.023, so honest runs essentially never fail.
  - Floors: ideal 0.02, low_noise 0.03, realistic 0.04; minimum fidelity 0.99 /
    0.985 / 0.98. Noisier presets spread probability over more outcomes, which
    adds sampling variance, so their floors are slightly higher. The floors also
    absorb float/ordering differences between two independent constructions.
  - Real faults are far outside these limits: a missing or reversed CNOT on Bell
    gives TVD ~0.46-0.5.
- Known blind spot, stated honestly: an error that moves the distribution by
  less than the threshold (for example an angle off by a few degrees) is not
  caught. Measurement-basis statistics cannot see a pure phase error either.

## D9. Agent loop design
- Steps: plan, generate, (demo) inject, then per attempt run -> verify ->
  diagnose -> repair; max 4 attempts. Every step is a plain-language event.
- Statistical diagnosis (`agent/diagnose.py`) reads the verdict: lost
  correlations ("the entangling gate looks missing or points the wrong way"),
  wrong marginals ("a gate may act on the wrong qubit"), a single outcome where
  noise should spread them ("counts look hard-coded").
- **No-progress stop:** if the repairer returns identical code, the loop stops
  and reports failure instead of burning attempts on the same script.
- The offline repairer is rule-based and deliberately limited: import-path
  fixes and line-level alignment of gate/measure calls with the spec (missing,
  extra, wrong qubit, reversed CNOT). It has no rule for tampered results
  (`fake_result`), which is how the "honest failure" path is demonstrated and
  tested. Muse Spark gets the same evidence and can fix that one too.
- Demo fault default (`auto`): missing CNOT if the circuit has one, else wrong
  qubit index, else wrong import.
- Every attempt keeps its code and a unified diff, so the UI can show exactly
  what each repair changed.

## D10. Muse Code CLI backend is optional and untested here
`INKUBIT_CODE_BACKEND=muse-cli` drives `muse exec` headlessly (flags from the
docs). The CLI is not installed on this machine, so this path is untested; the
default backend is the Model API (`muse-spark-1.3`).

## D11. Sketch understanding pipeline
1. Muse Spark looks at the photo and picks the diagram kind plus 1-4 noun
   phrases for SAM (the docs recommend exactly this pairing: "let Muse Spark
   interpret a scene and decide what to segment, then hand the concept to SAM").
2. SAM 3.1 runs once per phrase (concept prompts, `include_confidence`), boxes
   parsed from its token grammar. Masks are not decoded: the overlay only needs
   boxes.
3. Muse Spark gets the photo, a copy with numbered red boxes (set-of-marks
   prompting) and the box list, and fills a **flat draft schema** (every field
   required, no tuples or optional objects), which is the most reliable shape for
   constrained decoding. `spec/draft.py` converts it to a real spec, attaches the
   SAM boxes as `source`, and validates. On failure it re-prompts once with the
   readable validation errors.
- Uploads are EXIF-rotated and capped at 1600 px on the long side.
- Offline mode recognises the three bundled sketches by SHA-256 (fixtures drawn
  by `scripts/make_sketches.py` with exact element boxes). Any other photo gets
  an honest "needs live mode" message instead of an invented reading.
- Sample sketches use the Windows "Ink Free" font when present; the font file
  is not copied into the repo.

## D12. Network model assumptions (P9)
Analytic and pure Python (`network/physics.py`, `network/model.py`). Every
number is a stated assumption:
- Fiber: 0.2 dB/km at 1550 nm, light at 2e5 km/s, detectors 80% efficient,
  dark-click probability 1e-7 per gate.
- Free space at 810 nm: diffraction spot from a 0.30 m satellite transmitter
  (1.22 lambda/D) broadened by 8 urad of turbulence and pointing jitter, compared
  with a 1.0 m ground telescope (geometric loss); plus 4 dB atmosphere per
  satellite pass (0.1 dB/km for ground-to-ground), plus 8 dB optics and coupling.
  Detectors 60%, background + dark 1e-5 per gate. This gives ~66 dB for the
  1100 + 1600 km dual downlink and ~0.8 pairs/s, in line with Micius (64-82 dB,
  ~1 pair/s over 1,200 km). Calibrated to that public result, not to tests.
- Pairs: 1e8 pulses/s, 10% pair probability per pulse, intrinsic Werner
  fidelity 0.98. Accidental coincidences from dark/background clicks lower the
  visibility, so long links lose fidelity as well as rate.
- Segments split at repeaters. A satellite in a segment is the pair source
  (dual downlink, no memory). Repeater segments herald at L/c with 100
  multiplexed modes; end-to-end rate = 0.5^swaps / (H_n / slowest segment rate).
- Memory decoherence: each stored pair waits (T_all - its own wait) and its
  Werner parameter decays as exp(-t/T2). Swapping multiplies Werner parameters
  times 0.99 per swap. F = (3w+1)/4, QBER = (1-w)/2.
- Key: BBM92 asymptotic, sifting 1/2, R = 0.5 R_pairs (1 - 1.16 h(e) - h(e)),
  clamped at 0.
- **Limitation:** no entanglement purification or multi-pair terms, so long
  chains with many swaps accumulate errors (a 6 x 100 km chain reaches 12% QBER
  and no key). This is documented and tested, not hidden.

## D13. Bottleneck search
- Bottleneck = memory decoherence if any stored pair waits longer than 0.3 T2,
  otherwise the highest-loss link.
- Fixes: midpoint relay (terrestrial links only), move a repeater to balance
  spans (city positions never move), higher-elevation satellite pass (slant
  range x0.75, never below 500 km), bigger ground telescope (x1.5, capped at
  1.8 m, the Lijiang telescope used with Micius), memories x10 T2 (cap 10 s).
- Each candidate is a new, validated spec, re-simulated from scratch. Score:
  secret key rate; while there is no key at all, pairs/s x (F - 0.25), so a fix
  that makes progress (e.g. a relay before the memories are good enough) still
  counts. Apply the best only if it improves by more than 1%; up to 3 rounds.
- Sanity checks after the search: fidelity in [0.25, 1], key <= half the pair
  rate, no key above 11% QBER, and lengthening the weakest link must not raise
  the rate.

## D14. When SAM finds nothing on a real sketch
SAM 3.1 is trained on photos; pen strokes on paper may give few or no masks for
some phrases. The draft schema therefore also asks Muse Spark for each element's
box on its documented 0-1000 grid. If an element has no matching SAM segment, that
box (scaled to pixels) is used as its source with confidence 0.6 and shown in the
overlay labelled "seen by muse-spark-1.3", so the overlay is never empty and never
claims SAM found something it did not. Elements with neither get no location.

## D15. Result timing
The verified result is stored (and the UI shows it) as soon as the agent
finishes; the Muse Spark explanation and the Muse Image diagram then run in
parallel and fill in when ready. Muse Image can take tens of seconds.

## D16. Automated demo video
`scripts/record_demo.py` drives the real app in headless Edge and records the
browser's own screencast (1920x1080, H.264 via the ffmpeg bundled in
imageio-ffmpeg), with caption cards and a visible cursor laid over the page.
Rules that keep it honest: every number on screen comes from the run being
recorded; captions name a Meta model only when `/api/health` reports live Meta
mode (offline recordings say so on the title card); waits for the sandbox or
for model calls are sped up 4x only with an on-screen "4× speed" tag. Demo mode
now paces the network log too (0.35 s per step, as for circuits), so a viewer
can follow it.

## D17. New gates and the algorithm gallery
Added S†, T†, √X, controlled-phase (CP, one angle) and Toffoli (CCX). They let
the gallery hold real algorithms: Grover search, Bernstein-Vazirani,
Deutsch-Jozsa, phase estimation of T (inverse QFT built from CP), superdense
coding and a Toffoli AND; each has a test that checks the textbook answer.
Noise: CP gets the same two-qubit error as CX. A Toffoli is charged six CNOTs'
worth of depolarizing error, 1 - (1 - p2)^6, plus thermal relaxation for six
two-qubit gate times, because that is how it compiles on today's hardware. The
generated script and the verifier build that error identically.

## D18. Circuit insights
After a circuit runs, Inkubit also reports, exactly and from the spec alone:
the state after every gate (amplitudes with phases relative to the largest
amplitude, since a global phase is unobservable, and one Bloch vector per
qubit; a qubit whose vector is shorter than 1 is entangled with the others);
pairwise concurrence ideal vs noisy, plus each qubit's entanglement entropy
(so GHZ states, which have no pairwise entanglement, are described correctly);
an error budget (fidelity lost to each noise source acting alone); a sweep of
fidelity vs a noise scale factor with the scale needed for a 99% match
(bisection); readout correction of verified counts by inverting each bit's
known confusion matrix (clipped and renormalised); OpenQASM 2/3 exports.
These analyses evolve the density matrix gate by gate with the same error
channels as the verifier's Aer model, built in closed form (the generic
three-qubit conversion takes seconds); tests check both agree to 1e-8.
Above 10 qubits the noisy analyses are skipped with a note.

## D19. Entanglement purification
Networks can now purify: `purification_rounds` (0-3) applies BBPSSW to every
segment's fresh pairs before swapping. Each round turns two Werner pairs of
fidelity F into one of fidelity (F^2 + e^2) / p with success probability
p = F^2 + 2Fe + 5e^2, e = (1 - F)/3 (output twirled back to Werner), so the
segment rate is multiplied by p/2; rounds stop helping at F <= 1/2. The slower
rate means longer memory waits, which the existing decoherence model charges
for, so purification can hurt with poor memories: on the 600 km chain the agent
first upgrades memories and only then adds a round (key 0 -> 0.05 bit/s). We
assume the segment ends can hold the two pairs a round needs and ignore the
classical round-trip of the purification itself. The agent proposes it only
when the error rate, not the pair rate, is what blocks the key.

## D20. Describe it in words, camera, share links
A third way in: type a description. Live, Muse Spark fills the same flat draft
schema as for photos (`TEXT_SYSTEM` prompt, validated, one re-prompt). Offline,
`inkubit/textspec.py` is a deterministic parser for named algorithms, gate lists
("h 0; cx 0 1; rz pi/4 1") and simple networks; anything else is a 422 that
lists what it understands, never a guess. The kind is chosen by keywords
(satellite, fiber, km, repeater...). The camera button captures a frame in the
browser (getUserMedia) and sends it through the normal photo path. A share link
carries the whole spec in the URL hash (deflate-raw + base64url, photo boxes
dropped), so nothing is stored on a server.

## D21. Ask about a result
`POST /api/jobs/{id}/ask` answers a question about a finished run from that
run's facts only (`inkubit/ask.py`: spec without photo boxes, verdict, attempts
with diagnoses and fixes, insight summaries, or network before/after, fixes and
checks). Live, Muse Spark gets those facts and is told to say when they do not
contain the answer. Offline, answers are assembled from the same facts by topic
(repair, entanglement, noise budget, hardware, readout, verification,
bottleneck, key rate); a question outside those topics gets a plain "can't
answer that offline", never a loosely related paragraph.

## D22. Chip layouts
Insights also compile the circuit (Qiskit `transpile`, optimization level 1,
fixed seed) to IBM-style native gates on three wirings: all-to-all (trapped-ion
style), a line, and heavy-hex (the 7-qubit Falcon map, or the 19-qubit
distance-3 heavy-hex above 7 qubits). Extra SWAPs = extra CNOTs / 3 against the
all-to-all compile. The success figure is labelled rough: it multiplies gate and
readout fidelities of the preset and ignores decoherence; the verified numbers
remain the exact ones.

## D23. Explanations in 12 languages
The run bar has an "Explain in" choice (English, Hindi, Spanish, French, German,
Portuguese, Japanese, Chinese, Arabic, Bengali, Tamil, Indonesian). Live, Muse
Spark writes the explanation in that language and keeps numbers, qubit names
and bitstrings untouched. Offline templates exist only in English, so an offline
run shows the English text with a note saying so, rather than pretending.

## D24. Challenge mode
Eleven puzzles (`backend/inkubit/challenges.py`), each defined by a reference
circuit that never leaves the server. State puzzles compare |<target|psi>|^2;
gate puzzles compare the process fidelity |Tr(U_t^dagger U)|^2 / d^2, so global
phase never counts and any correct construction is accepted. Solved means at
least 0.999. Stars are golf-like (solved; within par + 2; at or under par) so a
long-winded answer is still rewarded, and each reference solution is tested to
reach exactly par. Allowed-gate lists turn gate identities (HZH = X, three
CNOTs = SWAP, H CX H = CZ) into puzzles. Feedback distinguishes "right odds,
wrong phase" from low overlap, and gate puzzles count correctly mapped basis
inputs. Hints: offline, the author's hints in order; live, Muse Spark gets the
goal, the player's circuit, the exact score and the author's hint for that
stage, never the solution, and is told to name at most one gate. Progress is
kept in localStorage: per-viewer, nothing to lose. A challenge stays active
while the player photographs or describes an answer, so a paper solution is
scored the moment it reaches the editor.

## D25. Click-to-compose and the live state
The editor's palette adds a gate by clicking wires (controls first, the target
last; a ghost shows where it will land, at the column the layout will really
give it). Erase removes a clicked gate; Undo covers palette edits. Every valid
edit calls `POST /api/state`, which returns each step's exact ideal state
(tens of milliseconds for small circuits), shown as Bloch spheres with each
qubit's path through the circuit plus the amplitudes. The spheres are drawn in
3D (SVG projection, front and back halves of each great circle drawn
differently) and share one camera, so turning one turns all and they stay
comparable.

## D26. What-if slider and network map
The hardware sweep panel has a slider over the same noise scaling as the sweep
(0 = perfect, then 0.01x to 10x on a log scale); each position asks
`/api/state` for the exact noisy distribution, so the histogram is exact, not
interpolated between sweep points, and a line on the sweep chart tracks the
slider. The network map draws the path with satellites above the ground line,
link width on a log scale of pairs per second, free-space links dashed, and gold
dots for entangled photons flying from each pair source (the satellite, or mid-
span on fiber). Dots are a picture of the rate, not a simulation of photons;
the numbers next to them are the model's. Motion is off under
prefers-reduced-motion. The weakest link is drawn brighter, not yellow, so it is
never confused with gold, which stays reserved for entanglement.

## D27. Optimizer: proposals are proven, never trusted
`backend/inkubit/optimize.py`. Rewrite rules, the Qiskit transpiler (level 3,
converted back into spec gates, with its qubit relabelling applied to the
measurements), rules + Qiskit, and live Muse Spark each propose a circuit.
`prove()` compares it with the original exactly: process fidelity
|Tr(U^dagger V)|^2/d^2 (up to 8 qubits), state fidelity from |0...0>, and the
total variation distance of the measured odds. The thresholds are floating
point, not physics: 1 - F < 1e-12 (states within 1e-6) and TVD < 1e-9. Only
"same measured odds" or stronger is accepted, because that is what the
verifier and the user see; the label always says which level holds, so a
circuit proven only on |0...0> is never presented as the same gate. Rules come in
three classes (any input; starting state |0...0>, tracked as known basis states;
measured odds: light cone of the measured qubits, diagonal gates and SWAPs
before measurement) and are applied one at a time so each reason describes the
circuit as it stood. A fuzz test runs 300 random circuits (all rules fire) and
requires every rewrite to keep the odds; locally 4,000 more passed. Muse Spark
sees the circuit, the measured qubits, its cost and the best cost so far (never
another optimizer's circuit) and, if rejected, gets one retry with the exact
reason. Cost order: two-qubit gates (CX/CZ 1, CP 2, SWAP 3, CCX 6), then gates,
then depth. Hidden in challenge mode, where it would give answers away.

## D28. Zero-noise extrapolation by global folding
Folding (U (U^-1 U)^k) is what hardware can actually do, unlike scaling the
noise model, so the simulation uses it: the folded circuit runs through the
same per-gate channels as everything else. Readout error is inverted first, so
extrapolation only has to undo gate noise. Richardson at 1x, 3x, 5x. Reported
twice: exact probabilities (the method's ceiling) and 4,000 seeded shots per
level, compared against readout correction alone from the same shots, since
the honest question is whether extrapolation pays for its extra shots. Skipped
above 8 qubits or 150 gates.

## D29. Entanglement web
Each step's state now carries every qubit's entanglement entropy and the
concurrence of each entangled pair (Wootters formula in numpy, tested against
Qiskit's), so the live strip and the step inspector can draw who is entangled
with whom. Pairs get gold threads (width by concurrence); a qubit's gold arc
is its entropy. Group entanglement with no pair entangled on its own (GHZ) is
drawn as a dashed hull and named, because concurrence alone would show nothing.
Listed up to 8 qubits.

## D30. Bell tests
`backend/inkubit/insights/bell.py`. CHSH uses the Horodecki closed form for the
maximum and its explicit settings (tested against brute-force search), so
there is no optimisation to trust. Mermin has no closed form; six directions are
optimised with BFGS from 16 fixed starts (deterministic) and the panel says the
settings are found, not proven optimal. Settings are chosen for the ideal state
and then applied to the noisy one, because that is what an experiment does.
Shot estimates include readout error and use 4,000 shots per setting with a
binomial standard error per correlator; "N standard errors above classical" is
reported only above 3. Pairs are tested only when entangled (concurrence >
0.01): separable states can sit exactly at S = 2 and would add noise to the panel.

## D31. State tomography
Linear inversion over all 3^n settings, readout error inverted per setting,
then the Smolin-Gambetta-Smith projection to the nearest physical state.
Limited to 3 qubits (27 settings) to keep the panel readable and the cost
trivial. The settings' rotations are taken as perfect; the summary separates the
fidelity lost to hardware noise (perfect tomography of the noisy state) from the
part that is shot noise.

## D32. Error-correction lab
Exact 3-qubit density matrices with the same gate channels; the flip channel is
applied in numpy and the decoder as one superoperator, so a whole curve takes
milliseconds (a test checks it against the plain Qiskit evolution). Readout error
is left out because it is identical for the bare qubit and the code. The
break-even point is the first crossing below the bare-qubit line, interpolated
in log p; the meeting at p = 1/2, where both are 50%, is not a crossing.

## D33. Say it
The describe box has a "Say it" button using the browser's own speech
recognition (hidden where unavailable). The transcript goes through the same
describe-in-words path as typed text. Its tooltip says the browser may send audio
to its maker's service; Inkubit itself never receives audio.

## D34. First live run
2026-10-30, every path with `INKUBIT_ALLOW_FALLBACK=0` so nothing could hide
behind the mock: sketch reading (concepts, SAM 3.1, draft) on the three samples,
a run (code, verification, explanation, Muse Image diagram), ask, text to spec
for a circuit and a network, the optimizer and a challenge hint. Two fixes came
out of it. The circuit draft schema allowed MEASURE as an operation but had no
classical-bit field, and Muse Spark put the GHZ sketch's meters there, so the
spec could never validate: MEASURE is out of the draft's gate enum, the prompt
says meters go in measurements, and a MEASURE operation that still arrives is
converted. Hindi came back transliterated into Latin letters: the prompt now
names each language's script, checked live for Hindi and Arabic. SAM's
confidences on the hand-drawn samples were lower than on the offline fixtures
(0.5 to 0.8, and it missed some boxes); Muse Spark's own boxes cover those and
are labelled as such. Total cost of the run, from the cached usage: about $0.40.

## D35. Say it with Muse Voice Transcribe
Live, "Say it" records the microphone with Web Audio, averages it down to
16 kHz, encodes a mono 16-bit WAV in the browser and posts it to
`/api/transcribe`, which checks the format and forwards it to Muse Voice
Transcribe (`PUSH_TO_TALK`, with quantum keywords for biasing). The browser does
the encoding so the server needs no ffmpeg. Recordings stop at 30 s. Offline the
endpoint answers 409 and the button uses the browser's recogniser (D33); the
mock never invents a transcript. The banner over the spec credits both the voice
model and Muse Spark. Checked live: three Windows-TTS clips through a fake
microphone in headless Edge, transcribed in 3 to 4 s and turned into the right
GHZ, Shor and satellite specs.

## D36. Split the party (QAOA Max-Cut)
The QAOA lab simulates the ansatz directly in NumPy (|+>^n, the cost phase
exp(-i gamma C), then exp(-i beta X) on every qubit) because the optimizer calls it
hundreds of times; a test checks it against Qiskit's Statevector of the generated
spec. The cost layer is CX-RZ(-gamma)-CX per edge, so the circuit uses only spec
gates and runs through the normal pipeline. Depth 1 is a 48 x 24 grid over
[0, pi] x [0, pi/2] (a full period after the E(g, b) = E(-g, -b) symmetry), then
BFGS from the best cell; depths 2 and 3 start from INTERP (Zhou et al. 2020) and
from the previous optimum padded with a zero layer, so more layers never do
worse. Splits are folded with their complements (swapping the tables changes
nothing). Brute force over every split gives the true answer, and the summary
says plainly that at this size QAOA shows the mechanism, not a speedup. Noise
uses the realistic preset's density-matrix simulation (about 2 s per graph,
cached). Checked: the 6-ring at depth 1 gives exactly 3/4 of the best cut, the
known value, and depth 3 solves it.

## D37. Bug hunt
Rounds are stateless: (level, seed) regenerates the same round, so the server
stores nothing and the page never receives the answer before it guesses. Bugs
are planted at the spec level as realistic mistakes and must move at least 20%
of the probability (total variation), so they can be seen in 1,000 shots.
Grading is by exact search, not by matching the planted index: every one-gate
edit (delete, swap the gate, move it, flip control and target, change the angle)
is simulated, and any gate whose edit restores the intended odds exactly counts.
Some circuits have many such gates (Bell has two gates; Shor measures 3 of 7
qubits, so 22 of its 28 gates counted), so a round is re-planted when more than
50%, 40% or 25% (by level) of its gates would count. Shor left the pool, and
the QAOA party circuit (31 gates, every qubit measured) joined Hard. The search
runs once while planting and is reused for grading. Live, Muse Spark plays the
same round in parallel with structured output (index, fix, reason) from exactly
what the player sees; offline it does not play, rather than a mock pretending.
Checked live: it found the bug in 4 of 4 rounds, in 9 to 24 s.

## D38. AI alone vs Inkubit, measured instead of claimed
The pitch that a chatbot hallucinates and Inkubit does not is tested, not
asserted. The same model (Muse Spark, medium effort, 24k tokens) gets each
circuit as data with no title or notes and no simulator, and predicts every
outcome's probability with structured output; exact simulation scores it by
total variation distance (exact < 1%, close < 5%). The first run disproved the
easy version of the claim: it was exact on all 13 textbook circuits and on 10 of
10 new seeded small circuits (3 to 5 qubits, arbitrary angles), so the page says
so. It failed where hand calculation gets exponentially harder: no usable answer
for the 31-gate QAOA circuit, and on six bigger seeded circuits (6 to 8 qubits,
all in superposition first, 4 measured) exact on 3, close on 1, no answer on 1,
and one confident answer (every outcome 1/16, described as a near-maximally
mixed marginal) that put 43% of the probability in the wrong place. The recorded
run is examples/arena_benchmark.json (shown offline, dated, with the model id);
"Ask the AI alone" repeats the test live on any circuit, and offline it refuses
rather than inventing an answer. The models table now names the check behind
every model step.

## D39. Molecule lab (H2 from first principles)
No chemistry package: the STO-3G integrals for two s functions have closed
forms (Szabo and Ostlund ch. 3), so they are computed directly and tested
against the book's values at 1.4 bohr (S12 0.6593, h11 -1.1204, (11|11) 0.7746,
E_HF -1.1167, full CI -1.1373) and the dissociation limit (2 x -0.46658). By
symmetry two configurations remain, so the problem is one qubit, H = a I + b Z +
c X; the page says so rather than dressing it up. VQE measures Z and X; noise
comes from the realistic preset's density matrices. A noise channel that does
not depend on the angle maps the Bloch vector affinely, so three simulations
fix the noisy expectation for every angle (checked against direct simulation to
1e-5), which took the lab from 110 s to under 4 s. Under realistic noise raw
VQE is worse than Hartree-Fock near equilibrium; undoing the calibrated map
(what calibration circuits measure on hardware) lands within shot noise of
exact at all 28 bond lengths.

## D40. Catch the spy (BB84)
Per-photon outcomes follow the measurement rule (same basis: the bit; other
basis: a coin flip) with a seeded generator, and the tests check that rule
against Qiskit on the photon circuit, including Eve as a CX onto her own qubit.
Half of the sifted bits are revealed to estimate the error rate; abort above
11% (one-way BB84); the kept key shrinks to n (1 - 2 h(QBER)). Eve on a share f
gives QBER = f/4 plus channel noise (minus the overlap), and at f = 1 she guesses
75% of the bits, both checked statistically.

## D41. Who it is for
Nine use-case cards open the existing features directly (scroll to a panel by
its heading, load a sample sketch, or load an example spec), so the breadth is
visible in the first screen without new navigation.

## D42. Ask Inkubit: tools, not answers
The assistant is Muse Spark with tool calling on Chat Completions
(docs/meta-api/tool-calling.md: the full assistant message goes back before
each tool result, tool_choice stays auto, parallel calls are executed in
order). Eight function tools wrap exact engines already in the repo; tool
errors go back to the model as data so it can fix its arguments. The system
prompt forbids computing a quantum result without a tool. After the answer,
every number in it is matched against the numbers in the tool results (at the
precision written, or as a percentage) and in the question; small counts and
bitstrings are skipped. The page shows "n of n traced" or lists what was not.
First live runs: 3 of 3, 5 of 5 and 14 of 14 numbers traced, with two parallel
molecule calls in one turn. Offline, a keyword router reaches the same tools
and is labelled as such.

## D43. Images from Muse Image
The nine use-case cards carry photographs generated by Muse Image 1.0 with one
restrained style (studio light, charcoal background, one blue accent, no text,
no glow), resized to 720x405 WebP (about 15 KB each) and credited on the panel.
Generation is a script, cached, about $0.01 per image.

## D44. Muse Wonder as the assistant's deep mode
Muse Wonder (`muse-wonder-1.0`) is Meta's most capable model, built for
multi-step agentic work with parallel tool calls (docs/meta-api/models.md). Ask
Inkubit keeps Muse Spark as the fast default and offers Muse Wonder as a toggle
for questions that chain several tools. It uses the same eight tools, the same
system prompt and the same number tracing, with `reasoning_effort: "medium"`, up
to 16k output tokens and six tool rounds instead of four. It costs about four
to five times as much per token ($4 / $20 per 1M input / output tokens against
$1.25 / $4.25), so it is opt-in. First live run: "plan a 1200 km satellite key
link, then check whether a spy on 20% of the photons would be caught" called the
link planner and BB84 in parallel and answered in 8.9 s, 13 of 13 numbers traced.

## D45. Hackathon rules
The rules ask for a public repository, work built during the event, and a demo
that makes the new work clear. The git history starts on Oct 27, 2026 (all
commits by the author), so the README and SUBMISSION.md state that everything
was built during the hackathon, with a day-by-day table taken from the log, and
list every third-party library, font and image source. The code is MIT
licensed. The project answers the "Push the Frontier" problem statement: the
models never produce a physical result themselves; they choose and drive exact
simulations, and every number they say is checked against one.

## D46. The Quantum Rosetta
Quantum computing is written in several languages at once (Dirac notation, circuit
diagrams, five or more programming languages), and newcomers stall on the
notation before the physics. The Rosetta translates between them and checks
every translation instead of trusting it.
- Reading is exact wherever a grammar exists: a recursive-descent parser for
  Dirac notation (implicit products, ⊗, √, π, e^(iφ), named states, simple LaTeX
  such as \frac and \rangle, normalisation reported), Qiskit's OpenQASM 2 and 3
  importers, and small line parsers for Quil and Qiskit gate calls. Muse Spark is
  used only for code without a parser here (Cirq, PennyLane, Q#, Braket) and for
  photos, which it transcribes under a schema and an instruction not to solve;
  the transcription then goes through the exact parser. Model readings are
  labelled.
- Writing Dirac notation: independent qubits are found by testing the purity of
  reduced states over qubit subsets (up to 8 qubits) and the factoring is
  accepted only if the tensor product rebuilds the state; magnitudes are written
  as surds when the squared magnitude is a fraction with denominator up to 1024
  (to 1e-9), phases as multiples of π/12 or less; the first term is made real and
  positive, as textbooks do.
- A state gets a circuit from the cheapest of: one rotation per independent qubit,
  a CNOT fan-out for two-term (GHZ-like) groups, a breadth-first search over
  H, X, Z, S, T, their inverses, CX and CZ for groups of up to 3 qubits whose
  amplitudes such gates can reach, Qiskit's StatePreparation compiled at
  optimization level 3, and any gallery circuit that makes the same state. The
  result must reach fidelity 1 - 1e-8 by exact simulation or the request fails.
- Eight output languages are written by fixed rules from the spec. Qiskit and
  OpenQASM 2/3 are executed or re-imported and Cirq is run when installed; each
  must give the same state, and the page says which were run. PennyLane, Q#, Quil
  and Braket are labelled "not run here" (Quil is read back by our own reader).
- Every step's effect sentence is derived from the exact states before and after
  (new or lost entanglement groups, more or fewer outcomes, phase-only changes,
  idle controls), not generated by a model. The same Dirac writer now labels
  every step of the gate-by-gate inspector, and Ask Inkubit gained a ninth tool,
  translate_notation.
Live checks: Muse Spark transcribed a printed singlet equation exactly and read a
three-qubit Cirq program gate by gate; the assistant chose the new tool on its
own, 3 of 3 numbers traced.

## D47. The simulation observatory, and diagram-style card art
The start page gained five exact simulations, each with its key number written
into one sentence from the data (backend/inkubit/observatory.py, /api/observatory,
computed once per process in about 1 s):
- Satellites vs fiber: secret-key rate between two cities from 25 to 3,000 km,
  using the network planner's own model (D12) on generated specs. The satellite
  sits 500 km over the midpoint; slant range and elevation come from spherical
  geometry, and the curve stops where either station would see it below 15
  degrees. Micius's 1,203 km (2017) is marked for scale; the finding says the
  number is the model's, since Micius's real geometry was less favourable. A
  repeater chain was tried and left out: with this model's memories it never
  beats direct fiber at these distances, so it added a line without a message.
- Grover vs noise: 2 to 5 qubits, one marked item, transpiled to CX/RZ/SX/X and
  evolved as a density matrix with the verifier's gate channels (realistic
  preset), then readout error; a test checks the noiseless circuit against
  sin^2((2k+1)θ). Classical comparison: check k items, then guess.
- Quantum walk: Hadamard walk vs binomial walk, all frames sent so the page can
  play it; spread checked against the known t·sqrt(1 - 1/sqrt2).
- Entanglement growth: 10-qubit brickwork of Haar-random two-qubit gates (8
  seeds), half-chain entropy against Page's formula (tested for two qubits).
- The exponential wall: 16·2^n bytes, with laptop and supercomputer lines.
Charts follow the existing palette (blue/orange validated for colour-blind
separation; the ideal curve is a dashed neutral reference; gold only for
entanglement), measure their real width so text stays 11 px, and each has a
crosshair readout, a legend and a "Show the numbers" table.
The nine use-case cards are now named by topic, not by persona, and their art
was regenerated with Muse Image in the flat technical style of the pipeline's
own diagrams (dark charcoal, off-white lines, one gold accent, no text).

## D48. Mission control: plan, run in parallel, repair, verify, trace
One request can carry words, a photo and speech (already transcribed by Muse Voice).
The photo goes through the sketch pipeline (SAM 3.1 + Muse Spark into a validated
spec), or, if it is not a drawing, through the Rosetta's notation reader. Muse Spark
(Muse Wonder in deep mode) then plans up to 8 steps under a JSON schema: tool,
arguments as a JSON string (each tool has its own schema), dependencies, purpose.
Circuits pass between steps by reference (`circuit_from`: a step id or "photo"),
so a proven shorter circuit from the optimizer can feed the ML verifier without the
model copying gates. Before anything runs, unknown tools are dropped and
dependencies must point to earlier steps, which rules out cycles. A thread pool runs
every step whose dependencies are done; each change is an event on the existing
EventBus and streams as server-sent events to a live graph. A failed step gets one
repair: Muse Spark sees the error and the tool's schema and returns new arguments.
Verification does not trust the tools: physics invariants per tool (variational
principle for H2, QAOA never above brute force, Shor's factors multiply to 15,
link fidelity in [1/4, 1], the 11% rule) and, for circuits, two independent noisy
simulators (closed-form channels vs Qiskit Aer's density matrix, to 1e-6). The ML
verifier also runs on every circuit, but a miss grades the model, not the result,
so it is a note and never flags the step. The report is written by Muse Spark from
the facts and the check texts, which also join the tracer's pool. Offline, a
keyword planner covers the sample missions, labelled. Live runs in the UI took 12 to
23 s (two cities, photo to hardware, a molecule at three bond lengths, RSA, exams).

## D49. The ML verifier
Target: the Hellinger fidelity of the realistic preset (times a scale from 0.05 to 5)
against the ideal distribution, the number the verifier and hardware sweep report.
Inputs (16): structure (qubits, measured, gates by size, depth, two-qubit depth,
busiest qubit), the ideal distribution (entropy, largest outcome, outcomes above
1e-3), log scale, the rule of thumb (product of gate and readout success) and two
physics-informed inputs computed on the ideal distribution alone: exact readout
errors, and a global depolarizing model (ideal mixed with uniform by one minus the
gates' product, then readout). Those two were added after the first model was
systematically optimistic on textbook circuits: structure alone cannot see that a
Bell pair's outcomes are two flips apart, so every readout error leaves the answer.
Data: 6000 random circuits of 1 to 7 qubits in five styles (gate soup,
layered, few gates, mirror circuits with certain answers, reversible logic), labelled
by exact density-matrix simulation (19 ms each on average). Model: five tanh MLPs
(16-48-48-1, sigmoid output) trained full-batch with Adam in NumPy; the mean is the
prediction. Interval: adaptive split conformal, |error| / (ensemble spread + 0.01)
on 900 calibration circuits, 90th percentile. Results on 900 held-out circuits:
error 0.0099 (physics model 0.0127, rule of thumb 0.0867), coverage
0.903, mean half-width 0.021; on 60 textbook cases never seen: error
0.0201 (physics 0.0216, rule 0.0839), coverage 0.78. The
guarantee is for circuits like the training set, which is why every prediction up
to 10 qubits is checked exactly. About 151 µs per prediction, 128 times faster than the
exact label. No new dependency: scikit-learn is not installed and NumPy suffices.

## D50. Seven more algorithms
qft_period, simon, swap_test, entanglement_swapping, ising_trotter, grover3 and
half_adder, written by a script that checks each against its textbook answer
before saving; tests pin the answers (Grover 121/128 exactly) and check the Trotter
circuit against the product of matrix exponentials. They join the gallery,
Mission control's run_algorithm tool and the ML verifier's textbook evaluation.

## D51. Discovery lab
Target: prepare a state with as few CNOTs as possible on the chip's wiring (two-qubit gates carry 15x the error).
Layouts from Muse Spark (JSON schema, invalid pairs dropped, credited when they win), spanning trees and random
pairs, tried from the fewest CNOTs up; rotations fitted by L-BFGS with restarts on a NumPy statevector (checked
against Qiskit in a test), then pruned (rotations under 1e-3 zeroed and the rest re-fitted). A winner must reach
overlap 1 - 1e-8 in Qiskit's Statevector of the rebuilt spec. Baselines: the textbook circuit and Qiskit's
StatePreparation, both compiled at level 3 onto the same coupling map. "Fewest found" is not a minimality proof.

## D52. Distributed quantum computer
Remote CNOT by gate teleportation (Eisert et al. 2000). With a Werner pair of fidelity F the ideal CNOT is followed
by X on the target, Z on the control, or both, each (1 - F)/3 (derived from where Pauli errors on the pair
propagate; a test checks it); ancilla readout flips add X_t or Z_c; the two local CNOTs are charged as 2 x p2
depolarizing; every data qubit idles under T1/T2 for a round trip of messages. Score: process fidelity, by running
the circuit on half of n Bell pairs (so at most 5 qubits); state or outcome fidelity were rejected because a
relaxed qubit can be steered back to the right answer by later gates. Split: exhaustive over placements.

## D53. When does quantum win?
Surface-code model in the style of Beverland et al. 2022 (P_L = 0.03 (p/0.01)^((d+1)/2), 2d^2 per patch, routing
2Q + sqrt(8Q) + 1, one logical step per d cycles, 1% budget; factories of 25 patches per T every 10 d cycles, two
15-to-1 rounds). Algorithms: Gidney & Ekera 2021 formulas for factoring; Grover with a stated oracle cost for search;
first-order Trotter with the rigorous ||[A,B]|| <= 8n bound and Ross-Selinger rotation costs for a 2D Ising magnet
(a worst case, said on the page). Classical: GNFS scaled from RSA-250 by the L-function, N/2 checks, the memory wall.
Every factoring result shows the model against the published RSA-2048 figure (26.6M qubits, 18.5 h vs 20M, 8 h).

## D54. Live board
Change detection in the browser (80 x 60 grey frames every 0.5 s; a read when the frame differs from the last read
by more than 10 grey levels and has been still for 1.5 s), so the slow model pass runs only when needed. Wires are
placed from overlay boxes: one-qubit gates directly, multi-qubit gates' boxes matched top to bottom to their qubits,
duplicate detections (one symbol under two concepts, IoU > 0.7) merged, a lone box given to the target.

## D55. Satellite planner
Circular 500 km orbit at 97.4 degrees with J2 nodal drift (sun-synchronous, tested to 0.02 degrees a day), GMST
rotation, NOAA solar position (tested at the solstice), spherical Earth. Passes need 15 degrees and the Sun below
-12 degrees. Atmosphere 4 dB x air mass relative to 45 degrees. Entanglement windows use the network model on the
two real slant ranges; trusted-node downlinks use decoy BB84 with mu = 0.5 at 100 MHz and a night background of
2e-6 per gate (the network model's 1e-5 includes stray light and gave zero key at 1,200 km, unlike Micius).
Coastlines: Natural Earth via the world-atlas package (land-110m), drawn on a canvas orthographic projection.

## D56. Reproduce a paper
Muse Spark transcribes, never computes: OpenQASM for the circuit (exact parser; the sketch pipeline if it fails)
and the claimed odds, shots, hardware and bit order. Error bars: 3 sigma of shot noise (at least 0.01) with a
known shot count, else 0.03 for hardware and 0.005 for ideal claims; hardware claims may also sit between our ideal
and realistic values. Unknown bit order: both are tried and the better fit is used, labelled as inferred.

## D57. ML error-correction decoder
Rotated d = 3 code, Z-basis memory, 3 rounds, phenomenological depolarizing noise (stim is not installed; sampling
is exact in NumPy). MWPM: exact minimum-weight perfect matching by DP over Z-check events on the space-time graph
with log-likelihood weights. Network: 25-128-128-1 ReLU, inputs every event of both check types and log p, trained
on 1.8M shots at six noise levels, tested on 200,000 new shots per level. Result at p = 1%: 0.00722 against
0.00917 (21% fewer); the gain holds at every tested p and exceeds both 95% intervals.

## D58. Pulse lab
Three-level transmon, RWA, alpha = -2 pi 300 MHz; truncated Gaussian pi pulse (sigma = T/4, area pi); DRAG
quadrature -beta dOmega/dt / alpha with beta from a golden-section search (it lands near 0.5, the first-order
optimum for phase errors); Lindblad T1/T2 from the realistic preset; 400 exact steps of the 9 x 9 superoperator;
average gate fidelity of the qubit-subspace channel with leakage as error. The sweep takes about 30 s and is cached.

## D59. Focus pass: one hero, five sections
The start page had grown to more than twenty stacked panels. Mission control now leads, with a switch to a quick
question (Ask Inkubit) in the same place, both kept mounted so a running mission survives the switch. Everything
else sits in five sections that mount only when opened (so the 11 s pulse sweep and other heavy requests no longer
start on page load): Sketch to code (photo, words, voice, live board, Rosetta, the use-case cards), Discover
(discovery lab, when does quantum win, reproduce a paper), Hardware and networks (pulse lab, ML decoder,
error-correction lab, distributed computer, satellite planner), Labs and games (challenges, bug hunt, Shor, QAOA, H2,
BB84) and Evidence (observatory with the ML verifier, AI alone vs Inkubit). The section is kept in the URL as
#tab=..., except when a #s= share link is present. A card or a Rosetta "see it" link to a panel in another section
switches section and scrolls twice (again after the panels above have loaded); sections end with 45vh of space so
the last panel can reach the top. The pulse sweep was made 3x faster (200 steps, 12 calibration iterations; same
results to four digits) and, with the observatory, is computed in a background thread at server start.

## D60. Guided tour and CI
A 95-second tour (header button or /#tour) steps through ten panels across the sections, each with one sentence
and a number the page itself computes; it starts a real mission and a real discovery run early and returns to their
results, which is why opened sections now stay mounted (hidden) instead of unmounting. GitHub Actions runs the
offline test suite (mock models, no key) and the frontend type-check and build on every push.

## D61. Public mode and the hosted copy
INKUBIT_PUBLIC=1 switches the agent to Inkubit's own template code generator (model-written code is never executed
on a shared host; the planted-fault repair demo still works because the faults go into our own code) and caps
billed model calls at INKUBIT_DAILY_CALLS (300) per UTC day, counted only on cache misses, after which the labelled
offline fallback answers. The Dockerfile builds the frontend with Node and serves everything from Python 3.13 as a
non-root user on port 7860; scripts/deploy_space.py stages the files (never .env), seeds the cache with the small
cached answers and uploads to a Hugging Face Space, optionally storing the key as an encrypted Space secret.

## D62. Mission benchmark and the hardware check
scripts/mission_bench.py ran 30 varied missions live (three hard on purpose): 30 of 30 finished with Muse Spark's
own plan, 68 of 68 steps verified (one repaired), 204 of 209 report numbers traced; the untraced ones are rounding
the tracer refuses to guess about (docs/MISSIONS.md). scripts/hardware_check.py compares real IBM counts with the
ideal odds, the generic preset and a digital twin from the device's calibration; a --fake rehearsal on
FakeSherbrooke checks the pipeline and is never shown as hardware data.

## D63. Real satellites instead of a modelled one
Asked to swap the modelled orbit for Micius's real elements, CelesTrak's catalogue showed Micius re-entered on
25 January 2026 (and Jinan-1 on 15 April 2025), so there are none to fetch. The quantum-key satellites in orbit now
are SpeQtre (NORAD 66769, RAL Space and SpeQtral, 12U, entangled-photon source, 80 mm telescope, one photon measured
on board so the satellite is a trusted node) and QUBE-II (NORAD 69023, German 8U CubeSat, 85 mm telescope,
prepare-and-measure); both fly on their real orbits and Micius stays as the labelled 2017 replay. Elements come from
CelesTrak GP as TLEs, checked against checksums and catalogue number, cached two hours (CelesTrak's update rate),
then the last good copy, then a snapshot shipped in the repo, each labelled. SGP4 (the sgp4 package, Vallado's
code) gives TEME; IAU-82 GMST takes it Earth-fixed (polar motion and UT1-UTC left out). Stations moved from a sphere
to WGS84 with the geodetic vertical, for Micius too. Against Skyfield on a day of SpeQtre passes: elevation and
azimuth within 0.0035°, range within 34 m (a test asserts 0.01° and 0.1 km). The downlink model now takes the
satellite's transmit aperture (8 cm spreads the beam about 1.7x wider than Micius's 30 cm). Open-Meteo's hourly total
cloud cover at each station scales each pass's key by the clear fraction, a first approximation (a low pass looks
through more sky than the zenith the forecast describes). The window starts at now (to 10 minutes) for 24 hours,
with a 7-day outlook per 24 hours; the globe follows the real clock and draws the 15° footprint. Key bits remain
estimates (the real payloads' source rates and protocols differ); pass times, elevations and clouds are real data.
Tests never touch the network: CelesTrak and Open-Meteo are stubbed and the snapshot flies.

## D64. Fresh-clone check and a history scan before going public
A clean clone with a new virtual environment, following the README exactly (requirements.txt only, npm ci, build,
no .env): the server starts in offline mode, every feature endpoint answers, and 442 backend tests pass (the 2
skipped need the dev extras, Skyfield and Cirq). Before the repository is made public, all 78 commits were searched
for key patterns (Meta, Hugging Face, GitHub, AWS, private keys) and for the literal Meta key from .env: no hits
anywhere in history, tracked files or the built frontend; .env was never committed.

## D65. End-to-end browser tests in CI, and the bug they found
e2e/test_ui.py starts the server on the offline models and drives the built app in Chromium: every section shows its
panels, a sample sketch goes all the way to Verified, the guided tour lands on every step and leaves a finished
mission and discovery run, the satellite planner flies a real satellite, and no section scrolls sideways at 390 px.
The section list and the tour steps are read from App.tsx and Tour.tsx so the tests follow the app. A third CI job
runs them. They caught a real bug: on a cold server the tour scrolled to the decoder before the pulse lab above it
had loaded, which then grew and pushed the decoder 878 px down. scrollToPanel now holds the panel in place for up to
15 s while the layout above it settles, released the moment the visitor scrolls, clicks or types.

## D66. Distance 5: error suppression, and a network that fixes what matching gets wrong
layout(d) generates the rotated surface code for any odd distance (it reproduces the distance-3 lists exactly; at
d = 5, 12 X and 12 Z checks, commuting, rank 24, one logical qubit). Matching at any distance uses PyMatching on the
same space-time graph and weights; it agreed with the exact bitmask matcher on all 20,000 distance-3 shots tried
(detectors in time-major order; check-major order gave 80%, which is how the order was pinned down). Memory
experiments of d rounds, per-round error from 1 - 2P = (1 - 2e)^rounds: distance 5 suppresses errors by Lambda = 5.9
at 1% noise (11.3 at 0.5%), shrinking to 1.15 at 6%. A first network that saw the events of both kinds and
matching's verdict learned only to copy matching (+0% at every noise level). The second also sees where matching put
its X corrections and where a second matching on the X checks put Z corrections: a qubit in both is a Y error, which
matching on one kind cannot see. It makes 10% fewer logical errors at 1% (16% at 0.75%); since both decoders run on
the same shots, significance uses a paired (McNemar) test on the shots one gets right and the other wrong: at 1% it
fixes 123 and breaks 27 (z = 7.8), significant at 8 of 9 noise levels (not at 6%). 12 million fresh training shots,
none seen twice.

## D67. Meta's open-weight models, tried on this laptop
Muse Spark Open is an 816B-parameter mixture of experts: out of reach of an 8 GB GPU. Muse Glimmer (27.9B, 4-bit,
`ollama pull muse-glimmer`, 18 GB with its vision projector) runs through Ollama's OpenAI-compatible endpoint with the
same Meta client (base URL, model name and a longer timeout are settings), split 71% CPU and 29% GPU, at about 1.6
tokens a second: a reasoned answer takes about five minutes. It answered the Bell pair exactly, under the JSON schema.
That is too slow to drive the app, so the hosted models stay. `scripts/arena_bench.py --glimmer` runs the AI-alone
benchmark on it and writes separate files, and the Arena panel gains a model toggle when they exist; a full run
takes hours and was stopped after one circuit when the machine ran low on memory, so no Glimmer results are
claimed.

## D68. A new video of under three minutes
scripts/record_demo.py keeps its recorder (browser screencast, labelled speed-ups, captions that name a Meta model
only in live mode) with new scenes for the current app: Mission control, sketch to verified code with a planted bug,
the discovery lab (CNOT counts read from the page), when quantum wins, the pulse lab, decoder and live satellites,
and the AI-alone evidence. DEMO_SCRIPT.md has a voice-over timed to the scenes.

## D69. Presentation, and our own numbers held to the app's rule
The README opens with a 15-second GIF of mission control cut from the video (960 px, 8 fps, 96 colours, 1.6 MB),
and docs/thumbnail.png (1280x720) is the video's thumbnail: name, promise, the verified mission graph and the
models. A finished mission downloads as one self-contained page (inkubit/mission_report.py): the plan, every step
with its results, checks and arguments, the report with each number marked green when the tracer found it in a tool
result and amber when not, the model calls, and standalone Qiskit code for each circuit. tests/test_claims.py
rebuilds 18 numbers that README and SUBMISSION quote (decoders, benchmarks, the ML verifier, the RSA-2048 check)
from their data files and fails if a document quotes anything else: the rule the app applies to a model's answer,
applied to our own. scripts/check_submission.py lists what the form needs (public repo, video and demo links,
video length, thumbnail, test counts, claims, secrets, CI, deadline); its first run caught the docs quoting 448
tests after the suite had grown to 468.

## D70. Hosting on a free container
Hugging Face now asks for a PRO account to run a Docker Space, so the free route is a container host's free tier
(Koyeb or Render: 512 MB, a tenth of a CPU, asleep when idle). Measured in public mode: 206 MB after start, 223 MB
after the labs and a mission, 255 MB during a discovery run, 385 MB for the server plus the sandbox at the peak of a
sketch run (verified on attempt 2), so it fits. The tenth of a CPU makes heavy actions about ten times slower
(about a minute or two for a sketch run or a discovery), and the start-up warm-up would have spent minutes of that
CPU after every wake. The input-free results (the observatory, the pulse sweep and its DRAG calibrations) are
therefore stored with the app (inkubit.precomputed, 37 KB, rebuilt by scripts/precompute.py) and a test checks they
equal a fresh computation. Koyeb is preferred: it wakes in seconds and sleeps after an hour (Render: 30-60 s after
15 minutes). A deploy link in the README fills in the repository, the Dockerfile, port 7860 and the free instance.

## D71. An AI scientist that learns under proof
inkubit/learning.py: Muse Spark proposes up to four CNOT layouts per round for a target state; the exact optimiser
fits each and Qiskit proves every one that reaches the target. Three conditions with the same number of proposals:
with feedback (every earlier layout and its verdict in the next prompt), without (the same model asked afresh,
numbered so no answer is reused) and random wiring of the feedback run's lengths. Live, five rounds, three targets
(scripts/learning_bench.py, docs/LEARNING.md): with feedback the best proven layout improved on every target (W on 4
qubits 6 to 5 CNOTs, Dicke(4,2) 6 to 5, W on 5 qubits in a line 8 to 7); without feedback the model never improved on
its first round (6, 6, 7; on the line its first answer was already 7), and repeated itself; random wiring never
reached a target. With feedback fewer of its layouts worked (10-15% against 10-35%): it aimed below its best and
missed more often, which is how it found the shorter ones. A first run died on a truncated answer; a cut-off answer is
a successful HTTP response and is cached, so the retry doubles the token budget and marks itself, which changes the
request, while the first attempt stays identical and keeps its cache.

## D72. Reproducing a whole paper
inkubit/paper.py takes a PDF or an arXiv id. One pass over a hundred-page paper (Muse Wonder with the whole PDF) was
fragile: it listed repeat runs of one Bell circuit, dropped numbers into its notes, and once returned truncated JSON.
Two passes work: Muse Wonder lists up to eight experiments on different circuits with their pages; pypdf cuts those
pages (and the next) into a small PDF and Muse Spark transcribes each experiment alone, in parallel. Circuits go
through the exact parser and claims through the figure checker's judge. A test caught a silent error on the way: the
QASM extractor stopped at the first statement it did not know, so a circuit with an opaque gate became an empty
circuit, and P(000) = 1 was then "reproduced". spec_from_qasm now refuses any statement acting on qubits that it
cannot read, and comments are stripped first. On arXiv:1804.03719 (Quantum Algorithm Implementations for Beginners):
eight experiments listed, five with a complete circuit and stated odds, three reproduced (a Bell state, two Hadamard
tests), Shor's algorithm for 15 and a quantum walk not (hardware data the realistic preset does not reach), three
reported as not completely specified on their pages; 11 of 19 stated probabilities check out; 107 s live.

## D73. Code lab: AI-designed error-correcting codes
inkubit/codes.py checks any stabilizer code exactly in the symplectic picture: commuting, independent generators,
k = n - rank, and the distance d, dX and dZ by brute force over every Pauli error from weight 1 up. The five-qubit,
Steane, Shor, rotated surface and XZZX surface codes are scored by the same checker (all d = 3). Muse Spark designed
codes in four rounds per target with every earlier verdict in the prompt (scripts/codes_bench.py, docs/CODES.md): the
[[5,1,3]] perfect code and a [[7,1,3]] CSS code in round 1 (the best possible, so no curve), and for Z-biased noise
on 9 qubits standard dZ = 3 codes in round 1, then in round 2 a [[9,1,3]] code with dZ = 9 and dX = 7: a logical
error from Z noise alone needs all nine qubits, three times the surface code's dZ = 3, while any one-qubit error is
still corrected. Anyone can check their own code on the page.

## D74. The AI referee
inkubit/referee.py: Muse Spark answers three questions about a circuit, Muse Wonder agrees or disputes each with its
own value, Muse Spark stands or concedes, and exact simulation grades every position (probabilities within 0.02,
the most likely outcome with ties, entanglement by the negativity of the two-qubit reduced state). When Muse Spark
chose its own claims it chose safe ones (right on 3 of 3 every time), which tests nothing, so the referee now asks
the same three questions of every circuit: the most likely outcome, the probability of the second most likely one
(picked from the exact odds; the models are not told why) and whether a given pair is entangled. On the six bigger
circuits from the AI-alone benchmark and two smaller new ones (scripts/referee_bench.py, docs/REFEREE.md): Muse Spark
was right on 17 of 24 answers as first stated and 19 after the debate; Muse Wonder caught 4 of its 7 wrong answers but
raised 5 false alarms and talked it out of 2 right answers. Debate between models helps on balance and adds errors of
its own; only the simulator can tell which challenge was right, which is why Inkubit checks instead of debating.

## D75. A real IBM quantum computer
scripts/hardware_check.py ran the Bell pair, GHZ-3, Bernstein-Vazirani and 2-qubit Grover on ibm_fez (IBM Quantum
Platform, Open plan, the least busy device; job dbjkc0pkdqps7390opdg, 4096 shots each, done 10 s after submission),
transpiled at optimisation level 3 (one or two two-qubit gates each). Against what the chip measured, by total
variation distance: the digital twin (Qiskit Aer with NoiseModel.from_backend, the device's own calibration, on the
same transpiled circuit) was closest on 4 of 4 (0.021 to 0.038); Inkubit's generic
realistic preset was 0.046 to 0.079, further off than the noiseless prediction on every circuit: it is
calibrated to an older, noisier class of chip, and this one is better. The app keeps the generic preset as its default
(it is a fair middle for a sketch) and says, on the Evidence page, that a calibrated twin is what predicts a given chip.

## D76. AI-discovered circuits on a real quantum computer
scripts/discovery_hardware.py reruns the discovery lab for GHZ on 7 qubits of heavy-hex wiring, W on 4 qubits and
Dicke D(4,2) (live models when configured, seeded heuristics always), and sends each goal's best proven circuit to the
chip with the baselines it beat: 23 circuits on ibm_fez (job dbjpr9pffo6c73ba4adg, 4096 shots each). GHZ-7 runs on
seven physical qubits wired like a 7-qubit Falcon chip (118, 109, 108, 110, 98, 111, 112, chosen by Qiskit's noise-aware layout for the
discovered circuit), and every variant is compiled onto that same patch, so the textbook circuit pays the SWAPs the lab
counted (10 two-qubit gates on the chip against 6). Z-basis odds cannot tell a GHZ state from a classical mixture of
all-0 and all-1, so inkubit/hardware.py also measures a parity oscillation over 8 phases and estimates
F = (P(0…0) + P(1…1))/2 + |coherence|, with shot-noise error bars (tested against exact states and against repeated
sampling); above 1/2 certifies genuine 7-qubit entanglement. Result: Muse Spark's own layout reached F = 0.814 against
0.795 for the textbook circuit, 3.2 standard errors apart, and both certify genuine 7-qubit entanglement;
Qiskit's generic state preparation (197 two-qubit gates) kept an outcome fidelity of 0.34. For W and Dicke,
compiled freely for the chip, the discovered circuits used 8 two-qubit gates against 17, yet their measured odds tied
with Qiskit's within shot noise (-1.2 and -0.3 standard errors): computational-basis odds do not see phase errors,
much of what fewer gates save, and the page says tie, not win. The digital twin was optimistic on every circuit this
time (GHZ 0.903 predicted, 0.814 measured) but ranked them the same way.

## D77. A calibrated noise preset from a real chip
The real IBM run (D75) showed the generic preset is calibrated to an older, noisier class of chip. scripts/calibration_snapshot.py
reads ibm_fez's reported calibration (IBM Quantum Platform) and keeps the median over its 156 qubits and couplers:
sx error 2.89e-04 (24 ns), cz error 2.49e-03 (68 ns), readout
0.68% / 1.46%, T1 135 µs, T2 101 µs (data/calibration.json). inkubit.sim.noise turns it into
a fourth preset, "calibrated": a reported gate error is an average infidelity that already includes decoherence during
the gate, so the thermal part (T1/T2 over the gate time, which the preset adds anyway) is taken out first and the rest
becomes depolarizing, p = r d/(d - 1), as NoiseModel.from_backend does; a test checks the composed error of each gate
equals the reported one. The codegen, the verifier and every analysis take it like any other preset; its verification
floors are low_noise's (0.03, 0.985). Rescored on D75's stored counts (complete, at most 8 outcomes each;
hardware_check.py --rescore): distance 0.013 to 0.027, closer than the twin on 4 of 4 (0.021 to 0.038)
against a floor of 0.003 to 0.009 that shot noise alone would give, so part of the chip's behaviour is still unmodelled. Two cautions, stated in the panel: the snapshot
was taken a few hours after the run (a later calibration of the same device), and medians describe a typical qubit,
not the best patch a compiler picks. The generic preset stays the default for sketches; "Calibrated" sits beside it
in the run bar.

## D78. Eight more algorithms, in categories
scripts/make_algorithms.py writes hidden shift (a bent function's shift in one query), Grover with two marked items
(found with certainty in one query), quantum counting (phase estimation of the Grover operator: k = 2 or 6, M = 2), a
Draper adder (5 + 6 in Fourier space), HHL on a 2x2 system (with t = 3π/4 the eigenphases are exactly 1/4 and 1/2, so
the ancilla = 1 branch holds A⁻¹b ∝ (1, 1/3) exactly), Shor's nine-qubit code correcting a Y error, the CHSH game
(won cos²(π/8)) and the GHZ game (won every time). Each answer is derived on paper in the builder's docstring and the
script refuses to save a circuit whose exact distribution differs from it by more than 1e-9; tests pin every answer
(the games by their win rates). Building them caught two traps in Qiskit's library: PhaseEstimation leaves the most
significant bit on its first evaluation qubit (the opposite of the order assumed), and transpiling at levels 2 and 3
may remove SWAPs and record a final permutation that a spec cannot carry, so the builder compiles at level 1 and
asserts no permutation is left. The gallery is now grouped into 8 categories (entanglement & communication, nonlocal games, oracles & hidden structure, search & counting, fourier & phase, arithmetic & logic, linear algebra & simulation, error correction), 25 algorithms in all;
mission control's run_algorithm tool can run every one.

## D79. The proof sheet
inkubit/proofsheet.py runs 11 independent checks of 9 kinds on any circuit, each named by the mistake it would catch:
the spec validator; two ideal engines (Qiskit's quantum_info and Aer's C++ statevector, to 1e-9) and two noisy ones
(closed-form channels and Aer's density matrix, to 1e-6); a physical density matrix (trace, Hermiticity, no negative
eigenvalue, purity); translation validation of Qiskit's compiler (the circuit compiled for all-to-all, line and 7-qubit
heavy-hex wiring must be the same unitary, routing and spare qubits included: Operator.from_circuit against the original
padded with idle qubits); OpenQASM 2 and 3 exports read back by Qiskit's strict parsers; 4,096 sampled shots against
the shot-noise bound and a G-test; the generated script verifying in the sandbox (run in a thread while the others run,
about 8 s in all); two metamorphic tests (renaming every qubit n − 1 − q, and inserting H·H, X·X and CX·CX, must leave the
odds unchanged); and the ML verifier's interval (a miss is a note about the model). A test breaks Qiskit's transpile on
purpose and requires the compilation check to fail. Its first run found a real defect: the OpenQASM 2 export wrote sx,
cp and swap, which the standard qelib1.inc does not define, so strict readers rejected circuits with them; the Rosetta's
own read-back had used Qiskit's lenient LEGACY_CUSTOM_INSTRUCTIONS and hidden it. The export now defines the three
gates in the file from standard ones, and both readers accept it. Over the gallery (scripts/proofsheet_bench.py,
docs/PROOFSHEET.md): 299 passed, 0 failed, 1 skipped with the reason, 8 notes.

## D80. IBM Quantum in the app: chip maps, a placement advisor, runs from the editor
scripts/device_snapshot.py stores each device the account can use (ibm_fez, ibm_kingston, ibm_marrakesh; Heron r2, 156 qubits) in full:
every qubit's T1, T2, readout errors and sx error, every coupler's two-qubit error, the queue and the calibration time
(data/devices, about 21 KB each). inkubit/chip.py draws the heavy-hex lattice from the coupling graph alone (runs of
consecutive qubits joined by couplers are rows; a lone qubit is a bridge drawn between its neighbours; a test checks every
coupler joins neighbours on the drawing) and advises placement: every embedding of the circuit's two-qubit-gate graph in
the chip's working couplers (rustworkx VF2) is scored by the chance that no gate or readout fails, from that chip's own
numbers (a CX is one native CZ, a CP two, a SWAP three; idle decoherence left out, so it ranks rather than predicts); a
Toffoli's triangle has no embedding in heavy-hex and the advisor says routing is needed. The IBM Quantum panel shows the
fleet (medians, live queues and the QPU time left when a token is configured), the map coloured by any calibration number
(grey best, orange worst, unusable couplers dashed red) and the advisor's best, median and worst placement on every chip.
With a token and outside public mode, "Run on IBM Quantum" sends the circuit in the editor to the least busy chip on the
advisor's qubits (level-1 compile with that initial layout; level 3 when the circuit does not embed), polls the job and
compares the counts with the ideal odds and the calibrated preset, next to the distance shot noise alone would leave; runs
are capped at 10 a day and logged. A race found while testing: qiskit-ibm-runtime imported by a request thread while the
warm-up thread imported other Qiskit modules came out half-initialised; the warm-up now imports it first, under a lock.

## D81. Placement and teleportation on a real chip
scripts/ibm_experiments.py, one job on ibm_fez (dbk6mf1kdqps7391s3q0, 63 circuits). Placement: the advisor scored
804 placements of a 5-qubit GHZ chain from a snapshot taken minutes before; the best-, median- and worst-scored ran
on exactly those qubits, each with a parity oscillation for the fidelity. Measured: 0.894 ± 0.003, 0.814 ± 0.004 and
0.285 ± 0.006, the advisor's order exactly; best against worst 95 standard errors apart, and the worst placement no longer
certifies entanglement (below 1/2). The twin (NoiseModel.from_backend) ranked them the same way and was optimistic on all
three. Teleportation with dynamic circuits: Bell measurement mid-circuit, X and Z applied by if_test only when the bits
say so, on the advisor's best 3-qubit chain (110, 109, 118); the six axis states sent and the receiver measured in X, Y and Z. The
six axis states form a 2-design, so their average fidelity equals the average over all pure states: 0.924 ± 0.002,
against 2/3 for the best classical (measure and prepare) scheme; without the corrections 0.499 ± 0.005, as theory says. This
also answers a stated limitation: Inkubit's simulator has no mid-circuit measurement, but the chip does.

## D82. Renamed to Inkubit, and led with proof and real hardware (2026-11-03)
The project was built under the working name Q-Canvas. An unrelated product called QCanvas (qcanvas.org) already
exists: a browser canvas for teaching quantum computing with drag-and-drop circuits, notes and quizzes. To avoid the
clash the project is now Inkubit (ink + qubit: it starts from a pencil sketch). Everything was renamed: the Python
package (`inkubit`), environment variables (`INKUBIT_*`), the API title, the report, the GitHub repository and the
video. Older commit messages keep the working name. Model prompts that named the app changed with it, so their
cached responses no longer match and the first live run of each makes a fresh call.

The overlap was more than the name, so the start page now leads with what QCanvas does not do: an assistant that
plans and runs whole missions, proves every number against an independent exact simulation, and runs circuits on real
IBM chips. Sections are ordered sketch, hardware, proof, discovery, labs, and the games and puzzles sit last.

## D83. Feed-forward in the format, the verifier, the editor and IBM runs (2026-11-03)
The teleportation run on ibm_fez (D81) used mid-circuit measurement and feed-forward from a script; the app's own format
allowed terminal measurements only. Now any gate may carry `"conditional": {"classical_register": c, "value": v}` and a
`MEASURE` may sit mid-circuit. Choices:

- **Qiskit `if_test`, not `c_if`.** `c_if` was removed in Qiskit 2.0; `if_test` is what IBM's dynamic circuits run, so
  the generated code, the drawing and **Run on IBM Quantum** share one construct (`verify.expected.physical_circuit`).
- **Exact prediction by deferred measurement** (`verify/dynamic.py`): one record qubit per mid-circuit measurement, a
  conditioned gate controlled by its record, readout flips on the record, and a conditioned gate's error channel only in
  the branch where it fires (a Kraus channel blocked by the record's projectors). Against 200,000-shot Aer runs of the
  generated code it agrees at the shot-noise floor for every preset and for a stress preset (p1 6%, p2 12%, readout
  7%/10%) with conditional CX/CZ and value-0 conditions, where the noiseless prediction is 0.15 away.
- **Refuse, never guess.** `append_operation` raises on a conditional operation, so every tool that reads gates into one
  unitary or state (step-through, live state, optimizer, proof sheet, Rosetta exports, ML verifier, arena, distributed)
  answers 422 in words instead of applying the gate unconditionally; the first version of the live state did exactly
  that, which is why the guard sits at the lowest level.
- **Scope.** No qubit reuse after measurement, one bit per condition, at most 10 qubits including records. Model prompts
  change only for feed-forward circuits, so every cached response for other circuits still matches.

## D84. Reuse, reset, conditions on several bits, and descriptions that ask for feed-forward (2026-11-03)
D83 left four limits; three are lifted and the fourth (sketches) is left on purpose.

- **Reuse.** A measured qubit may be used and measured again. The deferred-measurement model already handles it: the
  record is never touched after the copy, so the qubit carries on in its post-measurement state. A circuit counts as
  feed-forward (`CircuitSpec.is_dynamic`) when a gate is conditioned, a qubit is reset, or a qubit is used or measured
  again after a measurement; a `MEASURE` at the end, or followed only by gates on other qubits, stays an ordinary
  terminal measurement.
- **Reset.** `RESET` (Qiskit `reset`) swaps the qubit's state onto a fresh qubit that is never read: exactly "forget it
  and start from 0", with no error channel, as in the run's noise model. It cannot be conditional; an active reset is a
  measurement and a conditional X (`active_reset`).
- **Several bits.** `classical_register` may be a list, `value` read in binary with the first listed bit lowest. The
  code nests one `if_test` per bit rather than an aliased classical register (which would split Aer's counts keys) or a
  classical expression; the exact model controls on all the records and applies the gate's error only where every bit
  matches.
- **The showcase** (`bit_flip_feedforward`): one helper qubit measures both parities, reset in between, and the two-bit
  syndrome fixes only the qubit it points to, on the chip. It compiles for ibm_fez (3 `if_else`, 1 `reset`); its
  prediction matches 200,000-shot Aer runs under heavy noise.
- **Descriptions.** Offline, feed-forward phrases route to the exact examples. Live, text gets its own circuit draft with
  `clbits`, `condition_bits` and `condition_value`; the sketch draft is unchanged, so no cached sketch reading is lost.
  Muse Spark wrote correct feed-forward teleportation and the reset-and-reuse bit-flip code from plain descriptions on
  the first try (`pytest -m live`).
- **Sketches** would need a drawn double-line convention, a new sample and new segmentation phrases, and would change
  the sketch prompt that every cached reading depends on; left for after the hackathon.

## D85. A second pass against the generated look (2026-11-03)
The first pass (db26601) only cut words. The page still read as generated: AI-drawn card art with a gold
accent, a template hero (heavy headline, two buttons, four big counting numbers), Inter everywhere, dashboard tiles,
a wall of bordered buttons and panels fading in on scroll.

- **Cards** now carry pen sketches on paper, drawn by `scripts/make_card_sketches.py` with the same pen as the sample
  sketches and the tab doodles, each saying something true about its feature (7^x mod 15 repeating every 4, the H2
  energy well, a 25% error rate under a full intercept, the heavy-hex patch with three qubits picked). The eyebrow tags
  and question titles are gone. Muse Image still draws the pipeline's diagram; it no longer decorates the start page.
- **Type**: IBM Plex Sans and Plex Mono in place of Inter and JetBrains Mono; headings at weight 500.
- **Hero**: one button, the tour as a text link, the four figures as a plain record (mono value, label) with no count-up.
- **Figures** in every lab (`.tile`) are a hairline and a mono number, not filled boxes.
- **Gallery** is a three-column index of plain links; pasting JSON is folded under it.
- **Motion** that only decorates is gone (panels fading in on scroll, cards lifting on hover); motion that carries
  meaning stays (data flowing into a running step, a check passing).
- **The opening's figures** each sit over a small chart of the data they are computed from (`/api/headline` now
  returns it, `tests/test_headline.py` checks the chart against the figure): teleportation fidelity per input state on
  ibm_fez with and without feed-forward against the classical limit, the 30 benchmark missions' durations, the proof
  matrix (28 gallery circuits by 11 checks), and the five models by name. "Proves" is underlined by a pen stroke drawn
  once on load; nothing else moves.

## D86. The lecture checker: a filmed explanation in, every spoken claim checked (2026-11-04)
Three Meta capabilities the app had not used yet, each on what it is built for, and exact physics as the judge:

- **Muse Voice Transcribe in `DIARIZATION` mode** returns turns with start, end and a speaker label (the buffered
  `turns` array). A WAV written to a pipe has no length in its header, so the audio is cut to a file first.
- **SAM 3.1 on video** (`input_video`, a data URL of a 2-frames-a-second H.264 clip): one line per frame, each object
  keeping its id, so an object's first frame is when it was drawn. On pen sketches "square" and "circle" track
  reliably; "gate box" found nothing on video, and "dot" found the control dots late. Measured on the sample: the H at
  7.0 s, the CNOTs at 13.5 s and 30.0 s (drawn at 6.6, 13.6 and 30.1 s).
- **Muse Spark** reads the last frame with SAM's tracks as its segments, and writes each claim out formally: kind
  (probability, outcomes, entangled, not entangled, named state, other), qubits, bits, and the board version it is
  about. It never judges. The version it names is only accepted if that version was on the board during the turn (or
  appeared within a second after it); otherwise the board at the turn's start is used.
- **Exact simulation** judges every claim against the circuit as drawn at that moment: marginal probabilities to
  0.02, outcome sets exactly, entanglement as a mixed single-qubit reduced state (purity below 0.999), named states as
  fidelity 0.99 or more with GHZ, W, Bell, all-zero or uniform.
- **Muse Wonder** writes corrected notes from the verdicts only; **Muse Image** draws the final board (D87).

The sample (`scripts/make_lecture.py`) is a pen sketch drawn in five stages while Windows' David and Zira voices talk;
two statements are wrong on purpose, one per speaker. Live, the whole run takes about a minute and finds the same
three wrong claims the script planted (the student's "the third qubit is entangled too" before it was wired in, and the
teacher's "this is the W state" and "exactly one reads one"); `examples/lecture/lecture_run.json` records it. Offline,
only the sample can be checked: its script's own record stands in for the models, labelled. Uploads (MP4 or MOV with
sound, at most 60 s and 40 MB) need the live models. `imageio-ffmpeg` moved into the runtime requirements.

## D87. Proven illustrations: a generated figure is read back before it is shown (2026-11-04)
Muse Image's first figure of the lecture circuit drew the CNOTs on the wrong wires, and its "corrected" figure was
still wrong, yet a reader passed it: the figure's captions said "CNOT (q0→q1)". So a figure to be proven is drawn with
no captions (`diagram_prompt(..., {"plain": True})`), and read back with an instruction to read only the symbols
(a CNOT is a dot and a circled plus joined by a line; titles and captions are ignored), through the same pipeline as a
photographed sketch (Muse Spark picks concepts, SAM 3.1 segments, Muse Spark reads). The circuit read back must have
the same qubit count and the same unitary up to a global phase (overlap at least 0.999, since a figure prints angles to
two decimals). A wrong figure goes to Muse Image's edit endpoint (`/images/edits`, the figure as a data URL) with the
exact difference, at most twice; if it never matches, the exact Qiskit drawing is shown and the page says why.
`scripts/figure_bench.py` measures it over the small gallery circuits (`examples/figure_benchmark.json`): of 20,
Muse Image was right first time on 5 (Bell pair, Deutsch-Jozsa (balanced), GHZ-3, Superdense coding (sends 11), Superposition with a tilt) and after one correction on 1
(the Toffoli); the other 14 never matched within two corrections. In the six checked by eye, the read-back was right: gates on the wrong
wires, a Toffoli drawn for two CNOTs, controls joined to nothing, boxes spanning several wires. So the benchmark
measures Muse Image, and the rule (never show an unproven figure on its own) is what makes it safe to use.

## D88. The quantum internet on a 3D Earth (2026-11-04)
A key network between real cities, designed by the models and decided by physics, on a globe you can grab.

- **The globe** (`frontend/src/components/EarthScene.ts`, three.js): Natural Earth land drawn into a texture, lit by the
  Sun's real position for the moment shown (the Astronomical Almanac's low-precision solar coordinates), so day and
  night are right; routes coloured by the key they deliver; entangled photon pairs in gold (the colour kept for
  entanglement) leaving each source in opposite directions, fading out on the way where no key survives; SpeQtre and
  QUBE-II on their real orbits (SGP4 from today's CelesTrak elements, three hours ahead), with a gold beam to a city
  whenever the satellite is more than 15 degrees above its horizon; time at 1x, 60x or 600x. A frame is only ever
  scheduled once (OrbitControls' change event inside the frame would otherwise double the frames each frame).
- **Routes** (`backend/inkubit/qnet.py`) are one of three things that exist: fiber over the great-circle distance (the
  best case), fiber cut by quantum-memory repeaters (the network model's heralded segments), or a real satellite as a
  trusted node, scored by its clear-sky key from the real night passes of the next 24 hours, with tonight's cloud
  forecast shown beside it. A design is scored by its weakest pair.
- **The collaboration**: Muse Spark designs from words (city ids only, route types, no numbers); exact physics scores
  every route; Muse Wonder challenges with the physics in hand, and gets a second round with its first attempt as
  physics scored it; an exhaustive search over the same options shows the best possible. In the first live runs Spark
  chose QUBE-II for Delhi–Mumbai (586 bits a day), Wonder's first try did worse, and its second round switched to
  SpeQtre (8,070 bits a day), which the search confirmed as the best of the options. The numbers move with the orbits.
- **Honest physics, not a sales pitch**: with today's memories (10 ms) the model's repeaters never beat direct fiber;
  a slider lets anyone see where they start to win (three repeaters with 10 s memories give London–Paris about six
  times fiber's key). Offline, a rule of thumb stands in for the designer and nobody challenges it.

