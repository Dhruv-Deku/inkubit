"""Resource estimator: the surface-code model, its check against Gidney and Ekera, the families, the endpoint."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from inkubit.api.app import app
from inkubit.estimator import (
    HARDWARE,
    Algorithm,
    estimate,
    factoring_algorithm,
    gnfs_core_years,
    offline_map,
    p_logical,
    surface_code,
)


def test_logical_error_falls_with_distance_below_threshold():
    assert p_logical(5, 1e-3) < p_logical(3, 1e-3)
    assert p_logical(3, 1e-2) == pytest.approx(0.03)  # at threshold distance does not help
    assert surface_code(Algorithm(logical_qubits=10, toffolis=10, depth=10), HARDWARE["superconducting"].model_copy(
        update={"p": 0.02})).feasible is False


def test_rsa_2048_lands_near_the_published_figure():
    q = surface_code(factoring_algorithm(2048), HARDWARE["superconducting"])
    assert 10e6 < q.physical_qubits < 40e6  # Gidney & Ekera 2021: 20 million
    assert 4 * 3600 < q.runtime_s < 36 * 3600  # and 8 hours
    assert q.code_distance in range(25, 35, 2)


def test_classical_factoring_is_anchored_at_rsa_250():
    assert gnfs_core_years(829) == pytest.approx(2700)
    assert gnfs_core_years(2048) > 1e12


def test_better_qubits_need_fewer_physical_qubits():
    a = estimate({"family": "factoring", "bits": 2048}, "superconducting").quantum
    b = estimate({"family": "factoring", "bits": 2048}, "better").quantum
    assert b.physical_qubits < a.physical_qubits / 2 and b.code_distance < a.code_distance


def test_grover_loses_at_64_bits_and_crosses_later():
    e = estimate({"family": "search", "log2_candidates": 64, "oracle_toffolis": 1000, "checks_per_second": 1e8,
                  "cores": 1e4})
    assert e.verdict == "classical wins" and e.details["crossover_log2"] > 64


def test_simulation_and_none_families():
    small = estimate({"family": "simulation", "side": 6, "time": 1, "accuracy": 1e-2})
    assert small.verdict.startswith("classical can")  # 36 spins still fit exactly
    big = estimate({"family": "simulation", "side": 10, "time": 1, "accuracy": 1e-2})
    assert "contested" in big.verdict and math.isfinite(big.quantum.physical_qubits)
    assert estimate({"family": "none", "title": "Sorting"}).verdict == "no known quantum speedup"


def test_offline_reader_and_endpoint():
    assert offline_map("break RSA-4096 encryption")["bits"] == 4096
    assert offline_map("sort my spreadsheet")["family"] == "none"
    client = TestClient(app)
    body = client.post("/api/estimate", json={"preset": "rsa2048"}).json()
    assert body["family"] == "factoring" and "Gidney" in body["check"]
    assert client.post("/api/estimate", json={"text": "crack a 56-bit key"}).json()["family"] == "search"
    assert client.post("/api/estimate", json={}).status_code == 422
