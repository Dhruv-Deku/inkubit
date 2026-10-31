"""Surface-code decoders: the code itself, sampling, matching on known shots, the stored neural evaluation."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from qcanvas.api.app import app
from qcanvas.decoder import LOGICAL_X, LOGICAL_Z, X_CHECKS, Z_CHECKS, model, mwpm, sample, unprotected


def test_checks_commute_and_logicals_are_valid():
    for xc in X_CHECKS:
        for zc in Z_CHECKS:
            assert len(set(xc) & set(zc)) % 2 == 0
    assert all(len(set(LOGICAL_Z) & set(xc)) % 2 == 0 for xc in X_CHECKS)
    assert all(len(set(LOGICAL_X) & set(zc)) % 2 == 0 for zc in Z_CHECKS)
    assert len(set(LOGICAL_Z) & set(LOGICAL_X)) % 2 == 1


def test_no_noise_no_events():
    s = sample(50, 0.0)
    assert not s["dz"].any() and not s["dx"].any() and not s["flip"].any()


def test_matching_fixes_a_single_error_on_the_logical_row():
    dz = np.zeros((4, 4), np.uint8)
    dz[1, 0] = 1  # X on qubit 1 (top row) in round 2: check Z0 fires once and stays on, a boundary error
    assert mwpm(dz, 0.01) == 1
    dz2 = np.zeros((4, 4), np.uint8)
    dz2[1, 1] = 1  # X on qubit 6 or 7: boundary of check Z1, not on the logical row
    assert mwpm(dz2, 0.01) == 0


def test_code_beats_a_bare_qubit_at_low_noise_and_the_network_beats_matching():
    curve = {r["p"]: r for r in model()["curve"]}
    low = curve[0.005]
    assert low["mwpm"] < unprotected(0.005) and low["mwpm"] == low["mwpm"]
    wins = [r for r in curve.values() if r["neural"] + r["neural_ci"] < r["mwpm"] - r["mwpm_ci"]]
    assert len(wins) >= len(curve) // 2  # a clear win, beyond both error bars, on most noise levels


def test_endpoint():
    body = TestClient(app).get("/api/decoder", params={"p": 0.02, "seed": 3}).json()
    assert len(body["curve"]) >= 5 and body["example"]["mwpm"] in (0, 1)
