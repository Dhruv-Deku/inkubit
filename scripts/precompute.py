"""Rebuild the results stored with the app (backend/qcanvas/data/precomputed): the simulation observatory, the pulse
lab's duration sweep and its DRAG calibrations. Run after changing observatory.py or pulse.py; a test fails until
you do.

    .venv/Scripts/python scripts/precompute.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from qcanvas import observatory, precomputed, pulse  # noqa: E402


def main() -> None:
    t0 = time.time()
    print("observatory", precomputed.save("observatory", observatory.compute()), flush=True)
    betas = {f"{d:g}": pulse.calibrate_beta(float(d)) for d in pulse.DURATIONS}
    print("pulse betas", precomputed.save("pulse_betas", betas), flush=True)
    pulse.best_beta.cache_clear()
    print("pulse sweep", precomputed.save("pulse_sweep", pulse.compute_sweep()), flush=True)
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
