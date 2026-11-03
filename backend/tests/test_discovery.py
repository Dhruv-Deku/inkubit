"""Autonomous discovery: kernels against Qiskit, layouts on the chip, a full small run, model ideas, the endpoint."""

from __future__ import annotations

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

from inkubit.adapters.base import ModelCall
from inkubit.api.app import app
from inkubit.discovery import (
    GOALS,
    Discovery,
    _ghz,
    custom_goal,
    fit,
    lower_bound,
    prepare,
    run_discovery,
    spec_of,
    to_ops,
    tree_layouts,
)
from inkubit.insights.circuit import FALCON_7Q
from inkubit.spec import parse_spec
from inkubit.verify.expected import append_operation


def _qiskit_state(raw: dict) -> np.ndarray:
    spec = parse_spec(raw)
    qc = QuantumCircuit(spec.num_qubits)
    for op in spec.operations:
        append_operation(qc, op)
    return Statevector(qc).data


def test_kernel_matches_qiskit_for_random_angles():
    rng = np.random.default_rng(1)
    skel = [(0, 1), (2, 0), (1, 2)]
    for cplx in (False, True):
        x = rng.uniform(-3, 3, (3 + 6) * (2 if cplx else 1))
        ours = prepare(x, skel, 3, cplx)
        theirs = _qiskit_state(spec_of(to_ops(x, skel, 3, cplx), 3, "t"))
        assert abs(np.vdot(ours, theirs)) ** 2 == pytest.approx(1.0, abs=1e-10)


def test_fit_finds_ghz_on_a_fan_out_and_the_spec_proves_it():
    target = _ghz(3)
    err, x = fit(target, [(0, 1), (0, 2)], 3, False, np.random.default_rng(0))
    assert err < 1e-9
    psi = _qiskit_state(spec_of(to_ops(x, [(0, 1), (0, 2)], 3, False), 3, "ghz"))
    assert abs(np.vdot(target, psi)) ** 2 == pytest.approx(1.0, abs=1e-8)


def test_spanning_trees_use_only_the_chips_wiring():
    trees = tree_layouts(GOALS["ghz7_hex"])
    allowed = {p for a, b in FALCON_7Q for p in ((a, b), (b, a))}
    assert trees and all(len(t) == 6 and set(t) <= allowed for t in trees)


def test_lower_bound_counts_entangled_groups():
    assert lower_bound(_ghz(3), 3) == 2
    plus_zero = np.kron(np.array([1, 0]), np.array([1, 1]) / np.sqrt(2))  # |0>|+>
    assert lower_bound(plus_zero, 2) == 0


def test_custom_goal_reads_a_ket():
    goal, v = custom_goal("(|00⟩ + |11⟩)/√2")
    assert goal.num_qubits == 2 and np.allclose(np.abs(v), [2 ** -0.5, 0, 0, 2 ** -0.5])
    with pytest.raises(ValueError):
        custom_goal("|000000⟩")


def test_offline_run_beats_or_matches_the_baseline_with_a_proof():
    goal, v = custom_goal("(|000⟩ + |111⟩)/√2")
    d = Discovery(goal)
    run_discovery(d, v, budget_s=30)
    r = d.result
    assert d.status == "done" and r
    best = r["entries"][0]
    assert best["source"] not in ("textbook", "compiler") and best["cx"] == 2
    assert best["proof"] >= 1 - 1e-8
    assert r["fewest_cnots"] == 2 and r["ml_agrees"] is not None


class FakeModel:
    def structured(self, system, user, schema, name, effort="low", max_tokens=8000, model=None):
        return {"ideas": [{"cnots": [[0, 5]], "why": "not a qubit"},
                          {"cnots": [[1, 0], [1, 2]], "why": "fan out from the middle qubit"}]}, \
            ModelCall(provider="meta", model="fake", role=name, cached=False, latency_s=0.0)


def test_model_ideas_are_filtered_and_credited():
    goal, v = custom_goal("(|000⟩ + |111⟩)/√2")
    d = Discovery(goal)
    run_discovery(d, v, reasoning=FakeModel(), budget_s=30)
    sources = {e["source"] for e in d.result["entries"]}
    assert "muse" in sources
    muse = next(e for e in d.result["entries"] if e["source"] == "muse")
    assert muse["why"] == "fan out from the middle qubit" and muse["cx"] == 2


def test_endpoint():
    client = TestClient(app)
    assert {g["id"] for g in client.get("/api/discovery/goals").json()["goals"]} >= {"ghz7_hex", "w4"}
    assert client.post("/api/discovery", json={"goal": "nope"}).status_code == 422
    started = client.post("/api/discovery", json={"ket": "(|01⟩ - |10⟩)/√2"}).json()
    for _ in range(120):
        body = client.get(f"/api/discovery/{started['discovery_id']}").json()
        if body["status"] != "running":
            break
        time.sleep(0.25)
    assert body["status"] == "done", body
    assert body["result"]["entries"][0]["cx"] == 1
