# Q-Canvas demo video: shot list (2:45 target, 3:00 max)

**Fastest route: let the script record it.** With the backend running
(`scripts/dev.sh`, or uvicorn on :8000):

```sh
.venv/Scripts/python scripts/record_demo.py          # writes docs/video/q-canvas-demo.mp4 (+ .png thumbnail)
```

It drives the real app and lays captions over it (about 2:10, 1080p). Run it once
to warm the cache, then again for the final take. In live Meta mode the captions
name the models; offline, the title card says the answers are recorded mocks.
Add your own voice-over and the hand-drawing shot (1) in any editor if you like.
The shot list below is for recording by hand.

Record at 1920x1080, browser zoom 100%, dark OS theme. Before recording:

1. `.env` has `META_API_KEY` and `QCANVAS_MODEL_PROVIDER=meta`; the badge reads **Meta live**.
2. Do one full rehearsal run of each shot so every Meta response is cached
   (`backend/.qcanvas_cache/`): the takes are then instant and cost nothing.
3. Have a real phone photo of a hand-drawn Bell circuit ready (pen on white paper,
   H box, dot + circled plus, two meter boxes). If live reading misses something,
   that is fine: correcting it is part of the story (shot 3).
4. Turn on **Demo mode** (top right) before shot 4.

| # | Time | Shot | Say |
| --- | --- | --- | --- |
| 1 | 0:00-0:12 | Close-up: a hand drawing a Bell circuit on paper, then taking a phone photo. | "Every quantum program starts like this: a sketch. Turning it into code that is actually *right* is the hard part, because a wrong quantum program still runs. It just gives you the wrong answer." |
| 2 | 0:12-0:30 | Drag the photo onto Q-Canvas. Boxes appear on the photo with labels like `H q0 · 97%`, `CX q0→q1`. | "Q-Canvas sends the photo to Meta's models. Muse Spark decides what to look for, SAM 3.1 finds every gate, dot and meter, and Muse Spark reads the whole drawing into a structured spec, with every operation linked to the box it came from." |
| 3 | 0:30-0:45 | Hover a box: its row lights up in the editor. Change one thing (e.g. a target qubit) to show the live circuit preview and the readable validation error, then undo. | "Nothing runs until you agree with the reading. Hover a box to find its line, fix anything by hand, and the spec is checked as you type." |
| 4 | 0:45-1:25 | Click **Run** with Demo mode on. Keep the live log full screen-height. Let the failure land: red verify line, the attempt-1 histogram with bars at 00 and 01, the diagnosis line. Then the repair diff appears (`+ qc.cx(0, 1)`), attempt 2 passes. | "Demo mode plants a real bug in the first attempt: the CNOT is gone. The agent runs the code in a sandbox and compares it with an exact prediction it computes straight from the spec. Watch: expected 50% 00 and 50% 11, got 00 and 01. The two bits should agree and don't, so the entangling gate is missing. Muse Spark gets the spec, the code and that evidence, and fixes it. Attempt 2: verified." |
| 5 | 1:25-1:50 | Scroll the results: Verified badge, the four metric tiles, histogram with predicted (outline), measured (solid) and the dashed ideal. Pause on the explanation paragraph. Click the Code tab "Changes from attempt 1". | "The numbers are honest: distance from the prediction 0.004, well inside the shot-noise limit; noise cost about 7% against a perfect machine. Muse Spark explains it for a student, using these exact numbers. And the code is standalone Qiskit you can download and run." |
| 6 | 1:50-2:00 | Ask panel: click "Why did the first attempt fail?". | "Ask anything about the run. Muse Spark answers only from this run's numbers." |
| 7 | 2:00-2:15 | "Inside the circuit": press Play; the Bloch arrows shrink to the centre at the CNOT. Then the error budget and the "How good must the hardware be?" chart. | "Step through the exact state. When the CNOT entangles the qubits, their arrows shrink: neither has a state of its own. Readout errors cost the most here, and for a 99% match the hardware needs to get about seven times better." |
| 8 | 2:15-2:25 | Start page, type "Bernstein-Vazirani with secret 1011", Build it, Step through, Play to the end. | "No sketch? Describe it, and Muse Spark builds the spec. One query to the oracle reveals the secret." |
| 7b | (optional, +8 s) | Keep scrolling to **Zero-noise extrapolation**: the three blue points at 1x, 3x, 5x noise and the dashed line back to zero. | "Error mitigation: run the circuit noisier on purpose by folding every gate, then extrapolate back to zero noise. 0.93 becomes 0.998, and it also shows what's left with real shot counts." |
| 8a | (optional, +12 s) | Start page, **Phase estimation** from the spec list, **Find a shorter circuit**. Click the Rules + Qiskit row to show the numbered reasons. | "Rewrite rules, the Qiskit compiler and Muse Spark race to shorten it, and exact simulation proves each answer or rejects it. Phase estimation of a known phase shrinks to one X gate: its answer was fixed in advance, and Q-Canvas says so." |
| 8b | (optional, +15 s) | Start page, Challenges, **Bell pair**. Click H then q0; CX then q0, q1. Stars pop, the lesson appears. Drag a Bloch sphere to turn it. | "Or learn by playing: eleven puzzles, scored exactly against a hidden answer, with par like golf. Muse Spark gives hints without ever seeing the solution." |
| 9 | 2:25-2:40 | Pick **Preset A: satellite link** (or the satellite sketch). Run. Log, then the animated network map (toggle Before / After the fix) and the fix table. | "Q-Canvas also plans quantum networks: it models every link from physics, finds the bottleneck, tries real fixes, including entanglement purification, and keeps the best. The secret-key rate goes up more than a hundredfold." |
| 10 | 2:40-2:48 | Title card: "Q-Canvas: sketch → verified quantum simulation. SAM 3.1 · Muse Spark · Muse Image." | "From a pencil sketch to verified quantum code, with every answer checked. That's Q-Canvas." |

## Backup plan

- If the network is slow or the key is missing, set `QCANVAS_MODEL_PROVIDER=mock`
  and use the sample sketches: everything works offline and the badge honestly
  says **Mock**. Say "offline mode" on camera rather than implying live calls.
- `scripts/demo.sh` prints the same fail-repair-pass log in a terminal, for a
  close-up insert shot.
- The fiber chain preset is a second network story: no secret key at all until
  the agent adds a relay and upgrades the memories (0 → 0.39 bit/s).
