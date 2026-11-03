"""Real satellites: element parsing and fallbacks, SGP4 frames checked against Skyfield, clouds, the outlook, the API.
Nothing here touches the network: CelesTrak and Open-Meteo are replaced by the shipped snapshot and stubs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from inkubit import satellites as S
from inkubit.api.app import app
from inkubit.orbits import CITIES, azimuth, elevation, station, up_vector

NOW = datetime(2026, 11, 2, 9, 37, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def no_network(url, params):
        raise httpx.ConnectError("offline in tests")

    monkeypatch.setattr(S, "_http", no_network)
    S._tles.clear()
    S._cloud_cache.clear()
    S._real_plan.cache_clear()
    yield
    S._tles.clear()
    S._cloud_cache.clear()
    S._real_plan.cache_clear()


def test_elements_are_checked_before_use():
    el = S.snapshot(66769)
    good = f"SPEQTRE\n{el.line1}\n{el.line2}\n"
    assert S.parse_tle(good, 66769) == ("SPEQTRE", el.line1, el.line2)
    broken = el.line1[:60] + ("1" if el.line1[60] != "1" else "2") + el.line1[61:]
    with pytest.raises(ValueError, match="bad element line"):
        S.parse_tle(f"X\n{broken}\n{el.line2}", 66769)
    with pytest.raises(ValueError, match="another satellite"):
        S.parse_tle(good, 69023)


def test_without_celestrak_the_snapshot_is_used_and_labelled():
    el = S.elements(66769)
    assert el.source == "snapshot shipped with the app" and el.name == "SPEQTRE"
    assert datetime(2026, 10, 1, tzinfo=timezone.utc) < el.epoch < datetime(2026, 11, 2, tzinfo=timezone.utc)


def test_a_failed_refresh_keeps_the_last_good_copy(monkeypatch):
    el = S.snapshot(69023)
    monkeypatch.setattr(S, "_http", lambda url, params: httpx.Response(200, text=f"QUBE-II\n{el.line1}\n{el.line2}\n",
                                                                       request=httpx.Request("GET", url)))
    assert S.elements(69023).source == "CelesTrak"
    S._tles[69023] = (0.0, S._tles[69023][1])  # expired
    monkeypatch.setattr(S, "_http", lambda url, params: (_ for _ in ()).throw(httpx.ConnectError("down")))
    assert S.elements(69023).source == "CelesTrak, last good copy"


def test_sgp4_frames_agree_with_skyfield():
    """An independent implementation (Skyfield: its own TEME to ITRS and WGS84 topocentric code) agrees on every
    visible moment of a day to within a few thousandths of a degree and tens of metres."""
    skyfield = pytest.importorskip("skyfield.api")
    el = S.snapshot(66769)
    ts = skyfield.load.timescale(builtin=True)
    sat = skyfield.EarthSatellite(el.line1, el.line2, el.name, ts)
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    secs = np.arange(0, 86400, 30.0)
    pos, speed = S.propagate(el, start, secs)
    assert 7.5 < speed.mean() < 7.7
    for cid in ("chilbolton", "singapore"):
        _, lat, lon = CITIES[cid]
        sta, up = station(lat, lon), up_vector(lat, lon)
        el_deg, rng = elevation(pos, sta, up)
        az = azimuth(pos, sta, lat, lon)
        vis = np.flatnonzero(el_deg > 5)
        assert vis.size > 20
        alt, saz, dist = (sat - skyfield.wgs84.latlon(lat, lon)).at(
            ts.from_datetimes([start + timedelta(seconds=float(s)) for s in secs[vis]])).altaz()
        assert np.abs(el_deg[vis] - alt.degrees).max() < 0.01
        assert np.abs((az[vis] - saz.degrees + 180) % 360 - 180).max() < 0.01
        assert np.abs(rng[vis] - dist.km).max() < 0.1


def test_real_plan_without_network_flies_the_snapshot():
    p = S.real_plan("speqtre", "chilbolton", "singapore", now=NOW)
    sat = p.satellite
    assert sat["real"] and sat["norad"] == 66769 and sat["elements"]["source"] == "snapshot shipped with the app"
    assert 480 < sat["height_km"][0] < sat["height_km"][1] < 560 and sat["period_min"] == pytest.approx(94.6, abs=0.3)
    assert p.start_utc == "2026-11-02T09:30:00+00:00" and p.now_index == pytest.approx(14.0)
    assert len(p.track) == 86400 // p.step_s and len(p.outlook) == S.OUTLOOK_DAYS
    assert p.passes and all(x.kind in ("a", "b") for x in p.passes)  # one downlink: never both at once
    assert p.clouds is None and p.expected_trusted_key_bits is None and "in orbit now" in p.finding


def test_clouds_scale_the_key_each_pass_can_expect(monkeypatch):
    def half_cloudy(points, days=8):
        ts = np.arange(NOW.timestamp() - 7200, NOW.timestamp() + 9 * 86400, 3600.0)
        return [(ts, np.full(ts.size, 50.0)) for _ in points]

    monkeypatch.setattr(S, "cloud_forecast", half_cloudy)
    p = S.real_plan("qube2", "oberpfaffenhofen", "chilbolton", now=NOW)
    assert p.clouds and p.passes
    for x in p.passes:
        assert (x.cloud_a if x.kind == "a" else x.cloud_b) == 50.0
        assert x.expected_key_bits == pytest.approx(0.5 * x.key_bits)
    assert p.expected_trusted_key_bits == pytest.approx(0.5 * p.trusted_key_bits_per_day)
    assert all(o["expected_trusted"] == pytest.approx(0.5 * o["trusted"]) for o in p.outlook)


def test_cloud_series_outside_the_forecast_gives_no_number():
    series = (np.array([0.0, 3600.0]), np.array([20.0, 80.0]))
    assert S.cloud_at(series, 1800.0) == 50.0
    assert S.cloud_at(series, 7200.0) is None


def test_endpoint_lists_satellites_and_flies_a_real_one():
    client = TestClient(app)
    meta = client.get("/api/orbits/cities").json()
    by_id = {s["id"]: s for s in meta["satellites"]}
    assert by_id["speqtre"]["real"] and not by_id["micius"]["real"]
    assert any(pr["sat"] == "speqtre" for pr in meta["pairs"])
    r = client.get("/api/orbits", params={"a": "chilbolton", "b": "singapore", "sat": "speqtre"}).json()
    assert r["satellite"]["name"] == "SpeQtre" and r["now_index"] is not None
    assert client.get("/api/orbits", params={"a": "delhi", "b": "mumbai", "sat": "nope"}).status_code == 422
