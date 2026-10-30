"""QAOA Max-Cut: the NumPy simulator against Qiskit, known depth-1 values, brute force and the endpoint."""

from __future__ import annotations

import math
import random

import numpy as np
import pytest
from fastapi.testclient import TestClient

from qcanvas.api.app import app
from qcanvas.qaoa import _canonical_p1, _expected, check_graph, cut_values, qaoa_lab, qaoa_spec, qaoa_state
from qcanvas.spec import parse_spec
from qcanvas.verify.expected import ideal_distribution

RING6 = [(i, (i + 1) % 6) for i in range(6)]
RING5 = [(i, (i + 1) % 5) for i in range(5)]
K4 = [(i, j) for i in range(4) for j in range(i + 1, 4)]


def test_numpy_state_matches_qiskit_on_the_generated_circuit():
    rng = random.Random(7)
    n = 5
    edges = check_graph(n, [(0, 1), (1, 2), (2, 0), (2, 3), (3, 4), (1, 4)])
    gam, bet = [rng.uniform(0, 3) for _ in range(2)], [rng.uniform(0, 1.5) for _ in range(2)]
    probs = np.abs(qaoa_state(n, cut_values(n, edges), gam, bet)) ** 2
    ref = ideal_distribution(parse_spec(qaoa_spec(n, edges, gam, bet)))
    for key, p in ref.items():  # clbit k is node k; Qiskit keys are big-endian
        assert probs[int(key, 2)] == pytest.approx(p, abs=1e-6)
    assert sum(ref.values()) == pytest.approx(1)


def test_brute_force_best_cuts():
    assert cut_values(5, RING5).max() == 4
    lab = qaoa_lab(4, K4, noise="ideal")
    assert lab.max_cut == 4 and lab.optimal_count == 3 and lab.splits == 8  # the three 2-2 splits
    assert qaoa_lab(6, RING6, noise="ideal").optimal_count == 1  # alternate, folded with its complement


def test_ring_depth_one_is_three_quarters_and_depth_three_solves_the_six_ring():
    lab = qaoa_lab(6, RING6, noise="ideal")
    assert lab.depths[0].ratio == pytest.approx(0.75, abs=1e-6)  # the known p = 1 value on a 2-regular ring
    assert lab.depths[2].p_best == pytest.approx(1.0, abs=1e-4)  # p >= n/2 reaches the optimum on even rings
    assert lab.random_ratio == pytest.approx(0.5)


def test_more_layers_never_do_worse_and_noise_costs_something():
    lab = qaoa_lab(6, [(0, 1), (1, 2), (2, 0), (2, 3), (3, 4), (4, 5), (5, 3), (1, 4)])
    ratios = [d.ratio for d in lab.depths]
    assert ratios == sorted(ratios) and ratios[0] > lab.random_ratio
    for d in lab.depths:
        assert d.p_best_noisy is not None and d.p_best_noisy < d.p_best
        assert d.cx == 2 * 8 * d.p
        assert sum(s.prob for s in d.top) <= 1 + 1e-9 and all(s.teams[0] == 0 for s in d.top)
    assert "not a speedup" in lab.summary


def test_landscape_peak_matches_the_optimised_depth_one_angles():
    lab = qaoa_lab(5, RING5, noise="ideal")
    peak = max(max(row) for row in lab.landscape)
    assert lab.depths[0].ratio >= peak - 1e-9 and lab.depths[0].ratio - peak < 0.02
    g, b = lab.path[-1]
    assert 0 <= g <= math.pi and 0 <= b <= math.pi / 2


def test_canonical_angles_keep_the_expectation():
    rng = random.Random(3)
    edges = check_graph(5, [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0), (0, 2)])
    cuts = cut_values(5, edges)
    for _ in range(20):
        g, b = rng.uniform(-7, 7), rng.uniform(-4, 4)
        cg, cb = _canonical_p1(g, b)
        assert 0 <= cg <= math.pi and 0 <= cb <= math.pi / 2
        assert _expected(5, cuts, np.array([cg, cb])) == pytest.approx(_expected(5, cuts, np.array([g, b])), abs=1e-9)


@pytest.mark.parametrize("n, edges, needle", [
    (2, [(0, 1)], "3 to 8"), (9, [(0, 1)], "3 to 8"), (4, [], "at least one"),
    (4, [(0, 0)], "itself"), (4, [(0, 4)], "does not exist"),
], ids=["few", "many", "none", "loop", "range"])
def test_bad_graphs_are_refused(n, edges, needle):
    with pytest.raises(ValueError, match=needle):
        check_graph(n, edges)


def test_endpoint_names_the_guests_in_the_circuit():
    c = TestClient(app)
    r = c.post("/api/lab/qaoa", json={"n": 4, "edges": [[0, 1], [1, 2], [2, 3], [3, 0]], "labels": ["Ana", "Ben", "Cai", "Dev"]})
    assert r.status_code == 200
    d = r.json()
    assert d["max_cut"] == 4 and len(d["depths"]) == 3 and "q0 = Ana" in d["depths"][0]["spec"]["metadata"]["notes"]
    assert len(d["landscape"]) == 24 and len(d["landscape"][0]) == 48
    assert c.post("/api/lab/qaoa", json={"n": 4, "edges": [[0, 0]]}).status_code == 422
