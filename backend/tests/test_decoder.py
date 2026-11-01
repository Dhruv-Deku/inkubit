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


def test_the_layout_generator_gives_the_distance_3_code_and_a_valid_distance_5_code():
    from qcanvas.decoder import code, layout

    assert layout(3) == (X_CHECKS, Z_CHECKS, LOGICAL_Z, LOGICAL_X)
    xs, zs, lz, lx = layout(5)
    assert len(xs) == len(zs) == 12
    assert all(len(set(a) & set(b)) % 2 == 0 for a in xs for b in zs)
    assert all(len(set(lz) & set(a)) % 2 == 0 for a in xs) and all(len(set(lx) & set(b)) % 2 == 0 for b in zs)
    hz, hx, _ = code(5)
    assert np.linalg.matrix_rank(hz.astype(float)) + np.linalg.matrix_rank(hx.astype(float)) == 24  # one logical qubit


def test_pymatching_agrees_with_the_exact_matcher():
    from qcanvas.decoder import matching

    s = sample(3000, 0.03, seed=11)
    cache: dict = {}
    exact = np.array([mwpm(s["dz"][i], 0.03, cache=cache) for i in range(3000)], np.uint8)
    assert (matching(s["dz"], 0.03, 3) == exact).all()


def test_distance_5_suppresses_errors_below_threshold():
    from qcanvas.decoder import model_d5

    curve = {r["p"]: r for r in model_d5()["curve"]}
    assert curve[0.005]["lam"] > 5 and curve[0.01]["lam"] > 2  # far below threshold the bigger code wins big
    lams = [curve[p]["lam"] for p in sorted(curve)]
    assert all(a > b for a, b in zip(lams, lams[1:]))  # and its advantage shrinks towards the threshold
    for r in curve.values():  # the network on top of matching is never worse beyond the error bars
        assert r["neural"] <= r["d5"] + r["d5_ci"] + r["neural_ci"]


def test_endpoint_serves_a_distance_5_shot():
    client = TestClient(app)
    body = client.get("/api/decoder", params={"p": 0.02, "seed": 2, "d": 5}).json()
    ex = body["example"]
    assert ex["d"] == 5 and len(ex["z_checks"]) == 12 and len(ex["errors"][0]) == 25 and body["d5"]["curve"]
    assert client.get("/api/decoder", params={"d": 7}).status_code == 422
