"""ML verifier: features, predictions inside [0, 1], the exact check, the stored evaluation, the endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from qcanvas.api.app import app
from qcanvas.mlverify import FEATURES, check, exact_fidelity, features, load_model, predict
from qcanvas.spec import parse_spec


def _ghz(n: int) -> dict:
    ops = [{"gate": "H", "targets": [0]}] + [{"gate": "CX", "controls": [q], "targets": [q + 1]} for q in range(n - 1)]
    return {"kind": "circuit", "num_qubits": n, "num_clbits": n, "operations": ops,
            "measurements": [{"qubit": q, "clbit": q} for q in range(n)]}


def test_features_count_the_structure():
    spec = parse_spec(_ghz(3))
    f = dict(zip(FEATURES, features(spec, 1.0)))
    assert len(f) == len(FEATURES)
    assert (f["qubits"], f["gates_1q"], f["gates_2q"], f["depth"]) == (3, 1, 2, 3)
    assert f["entropy_bits"] == pytest.approx(1.0)
    assert 0 < f["baseline"] < 1


def test_prediction_is_a_fidelity_with_an_interval_around_it():
    p = predict(parse_spec(_ghz(4)), 1.0)
    assert 0 <= p.low <= p.fidelity <= p.high <= 1
    assert p.in_training_range and p.microseconds > 0


def test_check_computes_the_exact_answer_up_to_ten_qubits():
    spec = parse_spec(_ghz(3))
    res = check(spec, 2.0)
    assert res.exact == pytest.approx(exact_fidelity(spec, 2.0), abs=1e-4)
    assert res.error == pytest.approx(abs(res.prediction.fidelity - res.exact), abs=1e-4)
    assert res.inside == (res.prediction.low - 1e-9 <= res.exact <= res.prediction.high + 1e-9)
    big = check(parse_spec(_ghz(11)), 1.0)
    assert big.exact is None and "extrapolation" in big.verdict and not big.prediction.in_training_range


def test_stored_evaluation_beats_the_rule_of_thumb_and_keeps_its_coverage():
    m = load_model().metrics
    assert m["test_mae_ml"] < m["test_mae_baseline"] / 3
    assert m["test_coverage"] >= 0.85  # 90% target on a finite test set
    assert m["gallery_mae_ml"] < m["gallery_mae_baseline"]


def test_endpoints():
    client = TestClient(app)
    body = client.post("/api/mlverify", json={"spec": _ghz(2), "scale": 1.0}).json()
    assert body["exact"] is not None and "prediction" in body
    report = client.get("/api/mlverify/report").json()
    assert report["metrics"]["samples"] >= 1000 and len(report["scatter"]) > 100
