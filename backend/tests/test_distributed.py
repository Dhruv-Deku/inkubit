"""Distributed computer: the remote-gate channel, the split search, fidelity ordering, the endpoint."""

from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from qiskit.quantum_info import DensityMatrix, random_density_matrix

from qcanvas import EXAMPLES_DIR
from qcanvas.api.app import app
from qcanvas.distributed import _remote_channel, best_split, compile_ops, distribute
from qcanvas.spec import parse_spec


def _example(name: str):
    return parse_spec(json.loads((EXAMPLES_DIR / "specs" / f"{name}.json").read_text(encoding="utf-8")))


def test_a_perfect_link_adds_no_error_and_a_noisy_one_flips_the_right_qubits():
    rho = random_density_matrix(4, seed=3)
    assert np.allclose(rho.evolve(_remote_channel(1.0, 0.0, 0.0)).data, rho.data, atol=1e-12)
    zero = DensityMatrix.from_label("00")  # qargs [control, target]: an X on the target shows up as |1> on qubit 1
    out = zero.evolve(_remote_channel(0.7, 0.0, 0.0)).probabilities_dict()
    assert out["10"] == pytest.approx(2 * 0.1)  # X_t alone and X_t Z_c, each (1 - F)/3
    assert out["00"] == pytest.approx(1 - 0.2)


def test_split_search_finds_the_cheapest_cut():
    two_pairs = parse_spec({"kind": "circuit", "num_qubits": 4, "num_clbits": 4, "operations": [
        {"gate": "H", "targets": [0]}, {"gate": "CX", "controls": [0], "targets": [2]},
        {"gate": "H", "targets": [1]}, {"gate": "CX", "controls": [1], "targets": [3]}],
        "measurements": [{"qubit": q, "clbit": q} for q in range(4)]})
    _, ops = compile_ops(two_pairs)
    best, naive = best_split(ops, 4, 2)
    assert best.remote == 0 and sorted(best.chip_a) == [0, 2]
    assert naive.remote == 2  # first half on A cuts both pairs


def test_distance_and_memory_order_the_fidelities():
    res = distribute(_example("ghz3"), None, "fiber", 1.0)
    near, far = res.sweep[0], res.sweep[-1]
    assert res.best.remote == 1
    assert near[1] < res.monolithic_fidelity
    assert far[1] < near[1]
    assert far[2] > far[1]  # long-lived memory qubits survive the wait
    assert res.floor == pytest.approx(1 / 64)


def test_endpoint_and_limits():
    client = TestClient(app)
    spec = json.loads((EXAMPLES_DIR / "specs" / "teleportation.json").read_text(encoding="utf-8"))
    body = client.post("/api/distributed", json={"spec": spec, "medium": "fiber", "km": 0.1}).json()
    assert body["best"]["remote"] <= body["naive"]["remote"]
    assert body["options"][0]["fidelity"] < body["monolithic_fidelity"]
    big = {"kind": "circuit", "num_qubits": 6, "num_clbits": 6, "operations": [{"gate": "H", "targets": [0]}],
           "measurements": [{"qubit": 0, "clbit": 0}]}
    assert client.post("/api/distributed", json={"spec": big}).status_code == 422
