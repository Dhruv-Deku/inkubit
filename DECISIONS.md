# Decisions

Each entry: what was decided, and why. Newest last.

## D1. Project location and identity (2026-10-28)
No `q-canvas` folder, `.env` or `docs/meta-api/` existed. Created the project at
`C:\Users\DHRUV\Projects\q-canvas` with its own git repo (branch `main`). Commits
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
| Write and repair Qiskit code | `muse-spark-1.3` by default (`QCANVAS_CODE_MODEL`, e.g. `muse-wonder-1.0`) | `POST /v1/chat/completions` |
| Optional: repair through the Muse Code agent itself | `muse exec` headless CLI | local binary, opt in with `QCANVAS_CODE_BACKEND=muse-cli` |
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
`backend/.qcanvas_runs/`, a 60 s timeout, and an environment with every
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
`QCANVAS_CODE_BACKEND=muse-cli` drives `muse exec` headlessly (flags from the
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
After a circuit runs, Q-Canvas also reports, exactly and from the spec alone:
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
`qcanvas/textspec.py` is a deterministic parser for named algorithms, gate lists
("h 0; cx 0 1; rz pi/4 1") and simple networks; anything else is a 422 that
lists what it understands, never a guess. The kind is chosen by keywords
(satellite, fiber, km, repeater...). The camera button captures a frame in the
browser (getUserMedia) and sends it through the normal photo path. A share link
carries the whole spec in the URL hash (deflate-raw + base64url, photo boxes
dropped), so nothing is stored on a server.
