# Progress

Deadline: **Nov 4, 2026, 9:00 PM ET** (Cerebral Valley portal). Read this,
`DECISIONS.md` and `git log` first after a restart.

## Done (170 tests pass offline; frontend builds; last checked 2026-10-29)
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

## In progress
- Nothing. Fresh-clone check passed on 2026-10-28; features since then are covered by the 170 offline tests and a browser check of every new screen.

## Known issues / limitations
- Live Meta adapters are implemented from the docs and tested against recorded request shapes with a fake client, but **never called live** (no key on this machine). First live run may surface response-shape surprises; the fallback keeps the UI working and labels it.
- Muse Code CLI backend untested (CLI not installed).
- Network purification is the simple BBPSSW recurrence (D19); no nested or pumping schemes.
- Generated sample PNGs embed random paper grain: re-running `make_sketches.py` changes hashes (fixtures are rewritten together, so they stay consistent).

## Needs human
1. Put the Meta key in `.env`: `META_API_KEY=LLM_...` and `QCANVAS_MODEL_PROVIDER=meta`. Then run `cd backend && ../.venv/Scripts/python -m pytest -m live -q` (three tiny calls, < $0.02).
2. Try one real phone photo of a hand-drawn circuit in live mode; check SAM finds the parts (concept phrases are chosen by Muse Spark).
3. Run `scripts/record_demo.py` in live mode (twice: the first warms the cache), then upload `docs/video/q-canvas-demo.mp4`; optionally add a voice-over.
4. Create the GitHub repo (private until submission?) and push; fill the Cerebral Valley submission form (check its required fields: video length, repo link, description).
5. Git identity is `DHRUV <alwaysworking.7077@gmail.com>`; change with `git config user.email` if needed.

## Top 5 next steps
1. Live smoke test with the key; fix any response-shape differences in `adapters/meta_*.py` (now also `spec_from_text`, `answer`, and explanations in other languages).
2. Tune the concept-phrase prompt on 3-4 real photos (different pens/lighting).
3. Record the demo video live (`scripts/record_demo.py`).
4. Optional: let users click a box on the photo to add an operation that the reading missed.
5. Optional: a "Muse Spark writes the code" toggle in the UI (backend already routes generation through the code model in live mode).
