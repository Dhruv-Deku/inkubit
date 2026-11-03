"""The stored results (inkubit.precomputed) equal a fresh computation, so a small server can serve them safely."""

from __future__ import annotations

import math

from inkubit import observatory, precomputed, pulse


def _close(a, b, path="") -> None:
    if isinstance(a, dict):
        assert a.keys() == b.keys(), path
        for k in a:
            _close(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            _close(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9), f"{path}: stored {a}, fresh {b}"
    else:
        assert a == b, f"{path}: stored {a!r}, fresh {b!r}"


def test_the_stored_observatory_is_what_the_code_computes():
    stored = precomputed.load("observatory", observatory.Observatory)
    assert stored is not None, "run scripts/precompute.py"
    _close(stored.model_dump(mode="json"), observatory.compute().model_dump(mode="json"))


def test_the_stored_pulse_lab_is_what_the_code_computes():
    betas = precomputed.load_raw("pulse_betas")
    assert betas is not None and set(betas) == {f"{d:g}" for d in pulse.DURATIONS}, "run scripts/precompute.py"
    for d in (6, 20):  # two calibrations recomputed in full; the sweep below uses all of them
        assert math.isclose(betas[f"{d:g}"], pulse.calibrate_beta(float(d)), rel_tol=1e-6)
    stored = precomputed.load("pulse_sweep", pulse.Sweep)
    _close(stored.model_dump(mode="json"), pulse.compute_sweep().model_dump(mode="json"))


def test_the_app_serves_the_stored_results():
    observatory.observatory.cache_clear()
    pulse.sweep.cache_clear()
    pulse.best_beta.cache_clear()
    assert observatory.observatory() == precomputed.load("observatory", observatory.Observatory)
    assert pulse.sweep() == precomputed.load("pulse_sweep", pulse.Sweep)
    assert pulse.best_beta(20.0) == precomputed.load_raw("pulse_betas")["20"]
