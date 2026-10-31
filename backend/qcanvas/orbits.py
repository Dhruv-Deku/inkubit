"""Satellite planner: a Micius-like satellite over a real day, two real cities, every pass and its key.

Orbit: circular, 500 km, inclination 97.4 degrees (sun-synchronous, like Micius), propagated with the J2 drift of the
orbital plane, (3/2) n J2 (R/a)^2 cos i, and the Earth's rotation through Greenwich mean sidereal time. The plane is
placed so the satellite crosses the equator going south near local midnight, because free-space quantum links run in
the dark (Micius did all its experiments at night). The Sun comes from the NOAA low-precision solar position.

A station sees the satellite above 15 degrees elevation and only at night (Sun below -12 degrees, nautical twilight
over). Each moment's link uses the slant range to each station; the atmosphere costs 4 dB times the air mass
1/sin(elevation) relative to 45 degrees, on top of diffraction and optics from the network planner's model (D12).

Two ways to share a key between the cities:
* Entanglement: both stations must see the satellite at the same time; the pair rate and key rate come from the
  network model with the two real slant ranges (BBM92). Nothing has to be trusted, but such windows are rare.
* Trusted satellite: each station gets its own key from a decoy-state BB84 downlink during its own passes (100 MHz,
  mean photon number 0.5, key per pulse 0.5 * mu e^-mu * eta * (1 - 2 h(e))), and the satellite combines them, as
  Micius did between China and Austria in 2017; the shared key per day is the smaller of the two. Night background
  is 2e-6 per gate per detector; with it the model gives about 2 kbit/s at 1,200 km, the order Micius measured (about
  1 kbit/s at 1,200 km, Liao et al., Nature 549, 43, 2017).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import numpy as np
from pydantic import BaseModel

from qcanvas.network import physics as ph

MU = 398600.4418  # km^3/s^2
R_E = 6378.137  # km
J2 = 1.08263e-3
OMEGA_E = 7.2921159e-5  # rad/s
ALT_KM = 500.0
INC_DEG = 97.4
MIN_EL = 15.0
NIGHT_SUN_EL = -12.0
NIGHT_BACKGROUND = 2e-6  # dark counts plus stray light per detector gate at night
STEP_S = 30
HOURS = 24
START = datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc)

CITIES = {
    "delingha": ("Delingha", 37.37, 97.73), "lijiang": ("Lijiang", 26.69, 100.03),
    "xinglong": ("Xinglong", 40.40, 117.58), "nanshan": ("Nanshan (Ürümqi)", 43.47, 87.18),
    "graz": ("Graz", 47.07, 15.44), "vienna": ("Vienna", 48.21, 16.37), "beijing": ("Beijing", 39.90, 116.40),
    "delhi": ("Delhi", 28.61, 77.21), "mumbai": ("Mumbai", 19.08, 72.88), "bengaluru": ("Bengaluru", 12.97, 77.59),
    "london": ("London", 51.51, -0.13), "new_york": ("New York", 40.71, -74.01), "singapore": ("Singapore", 1.35, 103.82),
    "sydney": ("Sydney", -33.87, 151.21),
}
PAIRS = [("delingha", "lijiang", "Micius 2017: entanglement over 1,203 km"),
         ("xinglong", "graz", "Micius 2017: the first intercontinental quantum key"),
         ("delhi", "mumbai", "Two Indian cities"), ("london", "new_york", "Across the Atlantic")]


def julian(t: datetime) -> float:
    return t.timestamp() / 86400.0 + 2440587.5


def gmst(jd: np.ndarray) -> np.ndarray:
    d = jd - 2451545.0
    return np.radians((280.46061837 + 360.98564736629 * d) % 360.0)


def sun_eci(jd: np.ndarray) -> np.ndarray:
    """Unit vector to the Sun in the equatorial frame (NOAA / Astronomical Almanac low-precision formula)."""
    n = jd - 2451545.0
    L = np.radians((280.460 + 0.9856474 * n) % 360)
    g = np.radians((357.528 + 0.9856003 * n) % 360)
    lam = L + np.radians(1.915) * np.sin(g) + np.radians(0.020) * np.sin(2 * g)
    eps = np.radians(23.439 - 0.0000004 * n)
    return np.stack([np.cos(lam), np.cos(eps) * np.sin(lam), np.sin(eps) * np.sin(lam)], axis=-1)


def _rot_z(v: np.ndarray, angle: np.ndarray) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    return np.stack([c * v[..., 0] + s * v[..., 1], -s * v[..., 0] + c * v[..., 1], v[..., 2]], axis=-1)


def station(lat: float, lon: float) -> np.ndarray:
    la, lo = math.radians(lat), math.radians(lon)
    return R_E * np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)])


def orbit_ecef(times_s: np.ndarray, jd: np.ndarray) -> np.ndarray:
    a = R_E + ALT_KM
    n = math.sqrt(MU / a ** 3)
    inc = math.radians(INC_DEG)
    raan_rate = -1.5 * n * J2 * (R_E / a) ** 2 * math.cos(inc)
    # plane at local midnight: the descending node points away from the Sun at the start
    sun0 = sun_eci(jd[:1])[0]
    raan0 = math.atan2(-sun0[1], -sun0[0]) + math.pi  # ascending node opposite the descending node
    raan = raan0 + raan_rate * times_s
    u = math.pi / 2 + n * times_s  # start over the northern turning point
    x = np.cos(raan) * np.cos(u) - np.sin(raan) * np.sin(u) * math.cos(inc)
    y = np.sin(raan) * np.cos(u) + np.cos(raan) * np.sin(u) * math.cos(inc)
    z = np.sin(u) * math.sin(inc)
    eci = a * np.stack([x, y, z], axis=-1)
    return _rot_z(eci, gmst(jd))


def elevation(sat: np.ndarray, sta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    d = sat - sta
    rng = np.linalg.norm(d, axis=-1)
    up = sta / np.linalg.norm(sta)
    return np.degrees(np.arcsin(np.clip((d @ up) / rng, -1, 1))), rng


def sun_elevation(sun_ecef: np.ndarray, sta: np.ndarray) -> np.ndarray:
    up = sta / np.linalg.norm(sta)
    return np.degrees(np.arcsin(np.clip(sun_ecef @ up, -1, 1)))


def downlink_loss_db(slant_km: float, el_deg: float) -> float:
    base = ph.free_space_loss(slant_km, satellite=True)
    airmass = 1 / math.sin(math.radians(max(el_deg, 1.0)))
    return base.total_db - ph.DOWNLINK_ATMOSPHERE_DB + ph.DOWNLINK_ATMOSPHERE_DB * airmass / math.sqrt(2)


def entanglement_rate(la: float, ea: float, lb: float, eb: float) -> tuple[float, float]:
    from qcanvas.network.model import simulate
    from qcanvas.spec.models import NetworkSpec

    spec = NetworkSpec.model_validate({
        "nodes": [{"id": "a", "type": "ground_station"}, {"id": "s", "type": "satellite"}, {"id": "b", "type": "ground_station"}],
        "links": [{"from": "a", "to": "s", "medium": "free_space", "length_km": la, "loss_db": downlink_loss_db(la, ea)},
                  {"from": "s", "to": "b", "medium": "free_space", "length_km": lb, "loss_db": downlink_loss_db(lb, eb)}],
        "source": "a", "destination": "b"})
    e = simulate(spec).end_to_end
    return e.pair_rate_hz, e.key_rate_bps


def bb84_key_rate(slant_km: float, el_deg: float) -> float:
    eta = 10 ** (-downlink_loss_db(slant_km, el_deg) / 10) * ph.FREE_SPACE_DETECTOR_EFF
    mu = 0.5
    signal = mu * math.exp(-mu) * eta
    noise = 2 * NIGHT_BACKGROUND
    e = (0.5 * noise + 0.01 * signal) / (signal + noise) if signal + noise > 0 else 0.5
    return max(0.0, 1e8 * 0.5 * signal * (1 - 2 * ph.binary_entropy(e)))


class Pass(BaseModel):
    start_utc: str
    minutes: float
    max_el_a: float
    max_el_b: float | None
    pairs: float | None
    key_bits: float
    kind: str  # both | a | b


class Plan(BaseModel):
    city_a: dict[str, Any]
    city_b: dict[str, Any]
    distance_km: float
    start_utc: str
    step_s: int
    track: list[tuple[float, float]]  # satellite sub-point lat, lon per step
    sun: list[tuple[float, float]]  # sub-solar point per step (every 10 steps)
    el_a: list[float]
    el_b: list[float]
    night_a: list[bool]
    night_b: list[bool]
    passes: list[Pass]
    shared_key_bits_per_day: float
    entangled_pairs_per_day: float
    trusted_key_bits_per_day: float
    finding: str


def _great_circle(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    c = math.sin(la1) * math.sin(la2) + math.cos(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return 6371.0 * math.acos(max(-1.0, min(1.0, c)))


def _windows(mask: np.ndarray) -> list[tuple[int, int]]:
    out, i = [], 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j + 1 < len(mask) and mask[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


@lru_cache(maxsize=32)
def plan(a_id: str, b_id: str, night_only: bool = True) -> Plan:
    if a_id not in CITIES or b_id not in CITIES or a_id == b_id:
        raise ValueError("choose two different cities from the list")
    times = np.arange(0, HOURS * 3600, STEP_S, dtype=float)
    jd = julian(START) + times / 86400.0
    sat = orbit_ecef(times, jd)
    sun = _rot_z(sun_eci(jd), gmst(jd))
    (na, la_, loa), (nb, lb_, lob) = CITIES[a_id], CITIES[b_id]
    sa, sb = station(la_, loa), station(lb_, lob)
    ela, rga = elevation(sat, sa)
    elb, rgb = elevation(sat, sb)
    nighta = sun_elevation(sun, sa) < NIGHT_SUN_EL if night_only else np.ones_like(ela, bool)
    nightb = sun_elevation(sun, sb) < NIGHT_SUN_EL if night_only else np.ones_like(elb, bool)
    vis_a, vis_b = (ela >= MIN_EL) & nighta, (elb >= MIN_EL) & nightb
    passes: list[Pass] = []
    pairs_day = shared_key_ent = 0.0
    for i, j in _windows(vis_a & vis_b):
        pairs = key = 0.0
        for k in range(i, j + 1):
            p, kr = entanglement_rate(float(rga[k]), float(ela[k]), float(rgb[k]), float(elb[k]))
            pairs += p * STEP_S
            key += kr * STEP_S
        pairs_day += pairs
        shared_key_ent += key
        passes.append(Pass(start_utc=(START + timedelta(seconds=float(times[i]))).isoformat(), minutes=(j - i + 1) * STEP_S / 60,
                           max_el_a=round(float(ela[i:j + 1].max()), 1), max_el_b=round(float(elb[i:j + 1].max()), 1),
                           pairs=pairs, key_bits=key, kind="both"))
    keys = {"a": 0.0, "b": 0.0}
    for side, vis, el, rg in (("a", vis_a, ela, rga), ("b", vis_b, elb, rgb)):
        for i, j in _windows(vis):
            key = sum(bb84_key_rate(float(rg[k]), float(el[k])) * STEP_S for k in range(i, j + 1))
            keys[side] += key
            passes.append(Pass(start_utc=(START + timedelta(seconds=float(times[i]))).isoformat(),
                               minutes=(j - i + 1) * STEP_S / 60, max_el_a=round(float(el[i:j + 1].max()), 1),
                               max_el_b=None, pairs=None, key_bits=key, kind=side))
    passes.sort(key=lambda p: p.start_utc)
    trusted = min(keys["a"], keys["b"])
    dist = _great_circle((la_, loa), (lb_, lob))
    n_both = sum(1 for p in passes if p.kind == "both")
    sub_lat = np.degrees(np.arcsin(sat[:, 2] / np.linalg.norm(sat, axis=1)))
    sub_lon = np.degrees(np.arctan2(sat[:, 1], sat[:, 0]))
    sun_lat = np.degrees(np.arcsin(sun[:, 2]))
    sun_lon = np.degrees(np.arctan2(sun[:, 1], sun[:, 0]))
    if n_both:
        ent = (f"On {n_both} pass{'es' if n_both != 1 else ''} both cities see the satellite at night at once, sharing "
               f"{pairs_day:,.0f} entangled pairs and {shared_key_ent:,.0f} key bits that nobody, not even the "
               "satellite, knows.")
    else:
        ent = (f"The cities are {dist:,.0f} km apart: no pass lets both see the satellite at night at the same time, "
               "so entanglement-based keys are impossible from one satellite.")
    finding = (f"{ent} As a trusted node the satellite gives {na} {keys['a']:,.0f} and {nb} {keys['b']:,.0f} key bits "
               f"a day, so the cities can share {trusted:,.0f} bits a day if they trust the satellite.")
    return Plan(city_a={"id": a_id, "name": na, "lat": la_, "lon": loa}, city_b={"id": b_id, "name": nb, "lat": lb_, "lon": lob},
                distance_km=round(dist, 1), start_utc=START.isoformat(), step_s=STEP_S,
                track=[(round(float(x), 3), round(float(y), 3)) for x, y in zip(sub_lat, sub_lon)],
                sun=[(round(float(x), 2), round(float(y), 2)) for x, y in zip(sun_lat[::10], sun_lon[::10])],
                el_a=[round(float(v), 1) for v in ela], el_b=[round(float(v), 1) for v in elb],
                night_a=[bool(v) for v in nighta], night_b=[bool(v) for v in nightb], passes=passes,
                shared_key_bits_per_day=shared_key_ent, entangled_pairs_per_day=pairs_day,
                trusted_key_bits_per_day=trusted, finding=finding)
