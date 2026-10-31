"""Satellite planner: orbit geometry, the Sun, sun-synchronous drift, passes, the two key modes, the endpoint."""

from __future__ import annotations

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from qcanvas.api.app import app
from qcanvas.orbits import (
    ALT_KM, INC_DEG, J2, MU, R_E, START, bb84_key_rate, elevation, julian, orbit_ecef, plan, station, sun_eci,
)


def test_orbit_keeps_its_altitude_and_reaches_its_inclination():
    t = np.arange(0, 6000, 10.0)
    sat = orbit_ecef(t, julian(START) + t / 86400)
    r = np.linalg.norm(sat, axis=1)
    assert np.allclose(r, R_E + ALT_KM)
    assert np.degrees(np.arcsin(sat[:, 2] / r)).max() == pytest.approx(180 - INC_DEG, abs=0.1)


def test_plane_drifts_one_degree_a_day_like_the_sun():
    a = R_E + ALT_KM
    n = math.sqrt(MU / a ** 3)
    drift = -1.5 * n * J2 * (R_E / a) ** 2 * math.cos(math.radians(INC_DEG))
    assert math.degrees(drift * 86400) == pytest.approx(360 / 365.2422, abs=0.02)  # sun-synchronous


def test_sun_is_near_the_tropic_of_capricorn_in_late_december():
    from datetime import datetime, timezone

    v = sun_eci(np.array([julian(datetime(2026, 12, 21, 12, tzinfo=timezone.utc))]))[0]
    assert math.degrees(math.asin(v[2])) == pytest.approx(-23.44, abs=0.1)


def test_elevation_is_ninety_degrees_straight_overhead():
    sta = station(10.0, 20.0)
    el, rng = elevation(sta * (1 + ALT_KM / R_E), sta)
    assert el == pytest.approx(90.0) and rng == pytest.approx(ALT_KM)


def test_downlink_key_falls_with_slant_range():
    assert bb84_key_rate(600, 70) > bb84_key_rate(1200, 30) > 0


def test_micius_pair_shares_a_pass_and_far_cities_need_a_trusted_satellite():
    near = plan("delingha", "lijiang")
    assert any(p.kind == "both" for p in near.passes) and near.entangled_pairs_per_day > 0
    far = plan("xinglong", "graz")
    assert not any(p.kind == "both" for p in far.passes) and far.trusted_key_bits_per_day > 0
    assert len(near.track) == len(near.el_a) == 24 * 3600 // near.step_s


def test_endpoint():
    client = TestClient(app)
    assert len(client.get("/api/orbits/cities").json()["pairs"]) >= 3
    assert client.get("/api/orbits", params={"a": "delhi", "b": "mumbai"}).json()["city_b"]["name"] == "Mumbai"
    assert client.get("/api/orbits", params={"a": "delhi", "b": "delhi"}).status_code == 422
