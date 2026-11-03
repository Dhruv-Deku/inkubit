"""What the start page's opening scene shows, every number read from a stored result or computed here.

The scene replays the pipeline on the bundled GHZ sketch: the parts SAM 3.1 segmented (stored with the sketch), the
circuit Muse Spark reads from them, a noisy run and the independent prediction it is verified against. The four
headline figures come from the benchmark and hardware files the README quotes; tests/test_headline.py rebuilds them.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

from inkubit import EXAMPLES_DIR
from inkubit.sim.noise import build_noise_model, get_preset
from inkubit.spec.validation import parse_spec
from inkubit.verify.expected import build_reference_circuit, noisy_distribution
from inkubit.verify.verdict import verify_counts

SHOTS = 4096
SEED = 11
PRESET = "realistic"
MODELS = ["SAM 3.1", "Muse Spark", "Muse Wonder", "Muse Image", "Muse Voice"]


def _load(name: str) -> Any:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def stats() -> list[dict[str, str]]:
    """The four figures above the scene, each with where it comes from."""
    out: list[dict[str, str]] = []
    ibm = EXAMPLES_DIR / "ibm_experiments.json"
    if ibm.exists():
        data = json.loads(ibm.read_text(encoding="utf-8"))
        if not data.get("rehearsal"):
            t = data["teleport"]
            out.append({"value": f"{t['feed_forward']['average']:.3f}", "label": f"teleportation fidelity on IBM {data['device']}",
                        "note": f"classical limit {t['classical_limit']:.3f}; real mid-circuit feed-forward",
                        "source": "examples/ibm_experiments.json"})
    missions = _load("mission_benchmark.json")
    done = sum(1 for m in missions if m["status"] == "done")
    steps = sum(m["steps"] for m in missions)
    verified = sum(m["verified"] for m in missions)
    out.append({"value": f"{done}/{len(missions)}", "label": "missions finished live",
                "note": f"{verified} of {steps} steps verified", "source": "examples/mission_benchmark.json"})
    proof = _load("proofsheet_benchmark.json")
    tot = proof["totals"]
    checked = tot["passed"] + tot["failed"]
    out.append({"value": f"{tot['passed']}/{checked}", "label": "proof checks passed",
                "note": f"{proof['circuits']} gallery circuits, {proof['checks_per_circuit']} checks each",
                "source": "examples/proofsheet_benchmark.json"})
    out.append({"value": str(len(MODELS)), "label": "Meta models in the loop", "note": ", ".join(MODELS), "source": "health"})
    return out


@lru_cache(maxsize=1)
def scene() -> dict[str, Any]:
    """The GHZ sketch, its segments and gates, and a seeded noisy run checked by the real verifier."""
    sketch = _load("images/ghz_sketch.json")
    spec = parse_spec(_load("specs/ghz3.json"))
    qc = build_reference_circuit(spec)
    meas = QuantumCircuit(spec.num_qubits, spec.num_clbits)
    meas.compose(qc, inplace=True)
    for q, c in spec.measured_pairs():
        meas.measure(q, c)
    preset = get_preset(PRESET)
    sim = AerSimulator(noise_model=build_noise_model(preset), seed_simulator=SEED)
    counts = sim.run(meas, shots=SHOTS).result().get_counts()
    predicted = noisy_distribution(spec, preset)
    verdict = verify_counts(spec, counts, noise=PRESET)
    keys = [format(i, f"0{spec.num_clbits}b") for i in range(2 ** spec.num_clbits)]
    return {
        "image": "/api/examples/images/ghz_sketch.png",
        "width": sketch["width"], "height": sketch["height"],
        "segments": [{"concept": s["concept"], "bbox": s["bbox"], "confidence": s["confidence"]} for s in sketch["segments"]],
        "operations": [op.model_dump(exclude_none=True) for op in spec.operations],
        "num_qubits": spec.num_qubits,
        "outcomes": [{"key": k, "measured": counts.get(k, 0) / SHOTS, "predicted": predicted.get(k, 0.0)} for k in keys],
        "shots": SHOTS, "preset": preset.label,
        "verified": verdict.passed, "fidelity": verdict.metrics.fidelity, "tvd": verdict.metrics.tvd,
    }


def headline() -> dict[str, Any]:
    return {"stats": stats(), "scene": scene()}
