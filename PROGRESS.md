# Progress

Deadline: **Nov 4, 2026, 9:00 PM ET** (Cerebral Valley portal). Read this,
`DECISIONS.md` and `git log` first after a restart.

## Done (430 tests pass offline; frontend builds; live smoke tests pass; last checked 2026-11-01)
- **P1 Spec**: versioned pydantic models, readable validation (all issues, with paths), `schema.json`, 6 examples, round trips.
- **P2 Codegen + sim**: deterministic readable Qiskit template, noise presets (ideal / low / realistic), AST safety check, sandboxed subprocess runner (timeout, scrubbed env).
- **P3 Verification**: independent exact noise-aware expectation (density matrix + exact readout), TVD + Hellinger, shot-noise-based thresholds (D8), structured verdicts.
- **P4 Agent loop**: generate → run → verify → diagnose → repair, max 4 attempts, no-progress stop, 6 injected faults (5 repairable offline, 1 honest failure), diffs per attempt, event bus, CLI (`scripts/demo.sh`).
- **P5 Sketch understanding**: Muse Spark picks concepts → SAM 3.1 boxes → Muse Spark spec draft with segment links, re-prompt on invalid; 3 generated sample sketches with ground-truth fixtures; mocks by file hash.
- **P6 API**: FastAPI, image analysis, spec validation, jobs + SSE log, examples, health with provider mode; serves the built frontend.
- **P7 Frontend**: start (drop zone, samples, specs, paste JSON), photo overlay + form/JSON editor with live preview and validation, live agent log with diffs, live attempt histogram, results dashboard (verdict, metrics, histogram, explanation, code tabs, diagrams, models used), network results. Provider badge, demo-mode toggle.
- **P8 Explanation + diagram**: Muse Spark explanation and Muse Image illustration adapters; offline templates with real numbers; Qiskit/matplotlib diagrams.
- **P9 Network**: analytic model (fiber, satellite downlink, Werner fidelity, memory decoherence, swapping, BBM92), bottleneck search with 5 fix types over 3 rounds, sanity checks, before/after.
- **P10 Package**: README (Mermaid architecture, model usage, setup, spec, loop, limitations), DEMO_SCRIPT.md, `scripts/setup.sh`, `scripts/dev.sh`, screenshots + GIF.
- **Demo video**: `scripts/record_demo.py` records a captioned 1080p walkthrough of the real app (D16); offline take renders in about 2.5 minutes.
- **Added 2026-10-29** (each tested and committed):
  - Gates S†, T†, √X, CP, Toffoli; gallery: Grover, Bernstein-Vazirani, Deutsch-Jozsa, phase estimation, superdense coding, Toffoli AND (D17).
  - Insights (D18, D22): gate-by-gate state with Bloch spheres, entanglement ideal vs noisy, error budget, hardware sweep to 99%, readout correction, chip layouts (all-to-all, line, heavy-hex), OpenQASM 2/3 + spec export; "Step through" before running.
  - Network purification (BBPSSW) as a spec field and agent fix; 600 km chain preset (D19).
  - Describe it in words (Muse Spark live, offline parser), camera capture, share links, grouped examples (D20).
  - Ask about a result (D21); explanations in 12 languages (D23); downloadable HTML report.
  - Planted-fault benchmark `scripts/benchmark.py` → `docs/BENCHMARK.md`: 55/55 runs end correctly.
  - Challenge mode (D24): 11 exact puzzles in 3 levels with par, stars (localStorage), lessons, author hints offline and Muse Spark hints live; solvable by palette, photo or words.
  - Click-to-compose palette with ghost placement, erase, undo; live state strip with draggable 3D Bloch spheres and each qubit's path (D25).
  - What-if hardware slider with exact odds; animated network map with before/after (D26). Teleportation and W-state examples.
  - Optimizer (D27): rules with reasons, Qiskit level 3, rules + Qiskit, live Muse Spark with one retry; every proposal proven (unitary / state / odds) or rejected; fuzz-tested.
  - Zero-noise extrapolation by gate folding, exact and with shots (D28); entanglement web in the live strip and inspector (D29).
  - Bell tests: CHSH per entangled pair, Mermin for three qubits, ideal / noisy / shots with error bars (D30). State tomography with a 3D cityscape (D31). Error-correction lab with break-even vs gate quality, and a bit-flip code example (D32). "Say it" voice input (D33).
  - First live run against the Meta Model API, 2026-10-30 (D34): every model path works with fallback off; two problems found and fixed (meters in the sketch draft, Hindi in Latin letters). About $0.40 of credit used.
  - Shor's algorithm lab: factor 15 for every base a, from the measured phase to the period to the primes, with the failing bases explained.
  - Muse Voice Transcribe is the fifth Meta model (D35): "Say it" records a 16 kHz WAV in the browser, `/api/transcribe` sends it with quantum keywords, and the spec banner credits both models. Checked live through a fake microphone in headless Edge.
  - Split the party (D36): QAOA Max-Cut lab with a clickable graph, brute-force answer, depth-1 landscape you can click to try your own angles, optimized depths 1-3, realistic-noise odds, circuit to the editor.
  - Bug hunt (D37): find the one wrong gate from the histogram, graded by an exact search of every one-gate edit; Muse Spark plays the same round live; three levels, score and streak in the browser.
  - AI alone vs Q-Canvas (D38, docs/ARENA.md): Muse Spark predicting outcome odds with no simulator, scored against exact simulation. Exact on 23 of 24 small circuits; on bigger ones (6-8 qubits) exact on 3 of 6, one confidently 43% wrong, one no answer. "Ask the AI alone" in the editor; "How it was checked" column in the models table.
  - Molecule lab (D39): H₂ from first principles, Hartree-Fock vs exact vs VQE raw and mitigated across bond lengths. Catch the spy (D40): BB84 with an eavesdropper. Who it is for (D41): nine use-case cards.
  - Ask Q-Canvas (D42): Muse Spark with tool calling over eight exact tools, every number traced; voice input; result cards with "Open in the editor". Use-case photos from Muse Image (D43). Demo video beats rewritten around the assistant and the new labs.

## In progress
- Nothing. Fresh-clone check passed on 2026-10-28; features since then are covered by the offline tests and a headless-browser check of every new screen (desktop and 390 px phone width).

## Known issues / limitations
- Live runs are non-deterministic: a sketch read or a code draft can differ between fresh calls (responses are cached, so a recorded demo replays exactly). The verifier and the spec validator still decide what is shown as verified.
- Muse Code CLI backend untested (CLI not installed).
- Network purification is the simple BBPSSW recurrence (D19); no nested or pumping schemes.
- Generated sample PNGs embed random paper grain: re-running `make_sketches.py` changes hashes (fixtures are rewritten together, so they stay consistent).

## Needs human
1. Put the Meta key in `.env`: `META_API_KEY=LLM_...` and `QCANVAS_MODEL_PROVIDER=meta`. Then run `cd backend && ../.venv/Scripts/python -m pytest -m live -q` (three tiny calls, < $0.02).
2. Try one real phone photo of a hand-drawn circuit in live mode; check SAM finds the parts (concept phrases are chosen by Muse Spark).
3. Run `scripts/record_demo.py` in live mode (twice: the first warms the cache), then upload `docs/video/q-canvas-demo.mp4`; optionally add a voice-over.
4. Repo is pushed to https://github.com/Dhruv-Deku/q-canvas (**private**): make it public before submitting (`gh repo edit Dhruv-Deku/q-canvas --visibility public --accept-visibility-change-consequences`), then fill the Cerebral Valley submission form (check its required fields: video length, repo link, description).
5. Git identity is `DHRUV <alwaysworking.7077@gmail.com>`; change with `git config user.email` if needed.

- Oct 31: Muse Wonder deep mode for Ask Q-Canvas (D44). Hackathon rules applied (D45): MIT license, "Built during the hackathon" and third-party sections in the README, submission text updated; secret scan of the full history clean, repo ready to make public.

- Nov 1: the Quantum Rosetta (D46): Dirac notation both ways, exact OpenQASM/Quil/Qiskit readers, proven state preparation, eight output languages, the dictionary, photos of notation via Muse Spark; Dirac notation in the step inspector; translate_notation as the assistant's ninth tool.
- Nov 1: the simulation observatory (D47): satellites vs fiber, Grover vs noise, quantum walk, entanglement growth, the exponential wall, all exact (backend/qcanvas/observatory.py, /api/observatory, Observatory.tsx); use-case cards renamed by topic and redrawn by Muse Image in the pipeline's diagram style.
- Nov 1: mission control (D48: backend/qcanvas/mission.py, /api/missions + SSE, Mission.tsx), the ML verifier (D49: backend/qcanvas/mlverify.py, scripts/train_ml_verifier.py, data/ml_verifier.json, ML tab), seven more algorithms (D50). Live missions verified in the UI: two cities, photo to hardware, molecule, RSA, exams.
- Nov 1-2: discovery lab (D51), distributed computer (D52), when does quantum win (D53), live board (D54), satellite planner (D55), reproduce a paper (D56), ML decoder (D57), pulse lab (D58); each verified in the UI, live where a model is involved.

## Top 5 next steps
1. Live smoke test with the key; fix any response-shape differences in `adapters/meta_*.py` (now also `spec_from_text`, `answer`, `hint`, `optimize`, and explanations in other languages).
2. Tune the concept-phrase prompt on 3-4 real photos (different pens/lighting).
3. Record the demo video live (`scripts/record_demo.py`).
4. Optional: let users click a box on the photo to add an operation that the reading missed.
5. Optional: a "Muse Spark writes the code" toggle in the UI (backend already routes generation through the code model in live mode).
