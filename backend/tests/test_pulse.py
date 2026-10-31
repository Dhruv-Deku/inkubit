"""Pulse lab: pulse area, leakage physics, DRAG, decoherence limits."""

from __future__ import annotations

import math

import numpy as np
import pytest

from qcanvas.pulse import envelope, propagate, qubit_metrics, run


def test_pulse_area_is_pi():
    t, ox, _ = envelope(20.0)
    assert ox.sum() * (t[1] - t[0]) == pytest.approx(math.pi, rel=1e-9)


def test_a_slow_pulse_is_a_near_perfect_x_without_decoherence():
    fid, leak = qubit_metrics(propagate(60.0, 0.0, deco=False)[0])
    assert fid > 0.999 and leak < 1e-5


def test_short_gaussian_pulses_leak_and_drag_cuts_it():
    g = run(6.0, drag=False)
    d = run(6.0, drag=True)
    assert g.leakage > 5e-3
    assert d.leakage < g.leakage / 3 and d.fidelity > g.fidelity
    assert 0.2 < d.beta < 1.0  # first-order DRAG theory puts the optimum near 0.5


def test_populations_sum_to_one_and_end_in_one():
    r = run(20.0, drag=True)
    assert all(abs(sum(p) - 1) < 1e-5 for p in r.populations)
    assert r.populations[-1][1] > 0.999
