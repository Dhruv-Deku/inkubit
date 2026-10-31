"""Observatory: satellite geometry, the fiber crossover, walk spreads, Grover against theory, Page's limit, the endpoint."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient
from qiskit.quantum_info import DensityMatrix

from qcanvas.api.app import app
from qcanvas.observatory import (
    _evolve,
    _grover_parts,
    _read_marked,
    entanglement_chart,
    grover_case,
    observatory,
    page_entropy_bits,
    satellite_chart,
    satellite_geometry,
    walk_chart,
    walk_frames,
    wall_chart,
)


def test_satellite_overhead_is_its_altitude_and_low_elevation_far_away():
    slant, elevation = satellite_geometry(0.0)
    assert slant == pytest.approx(500.0)
    assert elevation == pytest.approx(90.0)
    slant, elevation = satellite_geometry(3000.0)
    assert slant > 1500 and elevation < 15


def test_fiber_wins_short_distances_and_the_satellite_wins_long_ones():
    chart = satellite_chart()
    sat, fiber = (dict(s.points) for s in chart.series)
    assert fiber[25] > sat[25] * 1000
    assert sat[1000] is not None and fiber[1000] is None  # fiber gives no key at all
    assert sat[3000] is None  # below 15 degrees for both stations: not plotted
    assert "260 km" in chart.finding


def test_walk_is_normalised_and_spreads_ballistically():
    frames = walk_frames(40)
    for q, c in zip(frames.quantum, frames.classical):
        assert sum(q) == pytest.approx(1.0, abs=1e-4)
        assert sum(c) == pytest.approx(1.0, abs=1e-4)
    spread = dict(walk_chart(frames).series[0].points)
    classical = dict(walk_chart(frames).series[1].points)
    assert spread[40] / 40 == pytest.approx(math.sqrt(1 - 1 / math.sqrt(2)), abs=0.02)  # Hadamard walk speed
    assert classical[40] == pytest.approx(math.sqrt(40), abs=1e-3)


@pytest.mark.parametrize("n", [2, 3, 4])
def test_noiseless_grover_circuit_matches_the_textbook_formula(n):
    marked = "1" * (n - 1) + "0"
    prep, step = _grover_parts(n, marked)
    rho = _evolve(DensityMatrix.from_label("0" * n), prep, {})
    theta = math.asin(1 / math.sqrt(2 ** n))
    for k in range(4):
        if k:
            rho = _evolve(rho, step, {})
        assert _read_marked(rho, marked, 0, 0) == pytest.approx(math.sin((2 * k + 1) * theta) ** 2, abs=1e-9)


def test_noise_erases_the_speedup_at_five_qubits_but_not_at_two():
    two, five = grover_case(2), grover_case(5)
    noisy2 = dict(two.chart.series[1].points)
    assert noisy2[1] > 0.85 and "still ahead" in two.chart.finding
    assert "erased the speedup" in five.chart.finding
    assert five.cx_per_query > two.cx_per_query


def test_page_limit_for_two_qubits_is_a_third_of_a_nat():
    assert page_entropy_bits(1, 1) == pytest.approx(1 / 3 / math.log(2))


def test_random_circuits_approach_page_but_never_exceed_the_maximum():
    chart = entanglement_chart(n=8, depth=16, seeds=3)
    mean = [v for _, v in chart.series[0].points]
    assert mean[0] == 0
    assert all(b >= a - 0.05 for a, b in zip(mean, mean[1:]))
    assert max(v for s in chart.series for _, v in s.points) <= 4 + 1e-9
    assert mean[-1] == pytest.approx(chart.references[0].value, rel=0.05)


def test_wall_doubles_per_qubit():
    pts = dict(wall_chart(40).series[0].points)
    assert pts[30] == 16 * 2 ** 30
    assert pts[31] == 2 * pts[30]


def test_endpoint_returns_every_chart():
    observatory.cache_clear()
    body = TestClient(app).get("/api/observatory").json()
    assert {"satellite", "walk", "walk_frames", "grover", "entanglement", "wall"} <= set(body)
    assert [g["qubits"] for g in body["grover"]] == [2, 3, 4, 5]
