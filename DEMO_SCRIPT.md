# Q-Canvas demo video: shot list (2:30 target, 3:00 max)

**Fastest route: let the script record it.** With the backend running
(`scripts/dev.sh`, or uvicorn on :8000):

```sh
.venv/Scripts/python scripts/record_demo.py          # writes docs/video/q-canvas-demo.mp4 (+ .png thumbnail)
```

It drives the real app and lays captions over it (about 1:40, 1080p). Run it once
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
| 6 | 1:50-1:58 | Diagrams panel: exact Qiskit drawing next to the Muse Image illustration. Then the "Models used" table with **Meta live** badges. | "Muse Image draws a clean version, always next to the exact drawing. Every result says which model made it." |
| 7 | 1:58-2:25 | Back to start, pick **Preset A: satellite link** (or the satellite sketch). Run. Show the log: link losses in dB, bottleneck, fixes tried, applied. Then Before/After tiles and the fix table. | "Q-Canvas also plans quantum networks. Two ground stations 1,200 km apart share entanglement from a satellite. It models every link from physics, finds the bottleneck, tries real fixes, re-simulates each one and keeps the best. The secret-key rate goes up more than a hundredfold, and every step passed its physics sanity checks." |
| 8 | 2:25-2:35 | Title card: "Q-Canvas: sketch → verified quantum simulation. SAM 3.1 · Muse Spark · Muse Image · Muse Code." | "From a pencil sketch to verified quantum code, with every answer checked. That's Q-Canvas." |

## Backup plan

- If the network is slow or the key is missing, set `QCANVAS_MODEL_PROVIDER=mock`
  and use the sample sketches: everything works offline and the badge honestly
  says **Mock**. Say "offline mode" on camera rather than implying live calls.
- `scripts/demo.sh` prints the same fail-repair-pass log in a terminal, for a
  close-up insert shot.
- The fiber chain preset is a second network story: no secret key at all until
  the agent adds a relay and upgrades the memories (0 → 0.39 bit/s).
