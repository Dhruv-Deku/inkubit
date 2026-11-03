"""Satellite planner: a quantum satellite over two real cities, every pass and its key.

Two kinds of satellite fly here. The quantum-key satellites in orbit today (SpeQtre, QUBE-II) fly their real orbits
from today's CelesTrak elements with SGP4, under the real cloud forecast (inkubit.satellites). Micius, which did the
2017 experiments and re-entered on 25 January 2026, flies a modelled orbit over a fixed day:

Modelled orbit: circular, 500 km, inclination 97.4 degrees (sun-synchronous, like Micius), propagated with the J2
drift of the orbital plane, (3/2) n J2 (R/a)^2 cos i, and the Earth's rotation through Greenwich mean sidereal time.
The plane is placed so the satellite crosses the equator going south near local midnight, because free-space quantum
links run in the dark (Micius did all its experiments at night). The Sun comes from the NOAA low-precision solar
position.

Stations sit on the WGS84 ellipsoid. A station sees the satellite above 15 degrees elevation (from the local
vertical) and only at night (Sun below -12 degrees, nautical twilight over). Each moment's link uses the slant range
to each station; the atmosphere costs 4 dB times the air mass 1/sin(elevation) relative to 45 degrees, on top of
diffraction from the satellite's own telescope and optics from the network planner's model (D12).

Two ways to share a key between the cities:
* Entanglement (a satellite with two downlinks, as Micius had): both stations must see the satellite at the same
  time; the pair rate and key rate come from the network model with the two real slant ranges (BBM92). Nothing has
  to be trusted, but such windows are rare.
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
from typing import Any, Callable

import numpy as np
from pydantic import BaseModel

from inkubit.network import physics as ph

MU = 398600.4418  # km^3/s^2
R_E = 6378.137  # km, WGS84 equatorial radius
F_E = 1 / 298.257223563  # WGS84 flattening
E2 = F_E * (2 - F_E)
J2 = 1.08263e-3
OMEGA_E = 7.2921159e-5  # rad/s
ALT_KM = 500.0
INC_DEG = 97.4
MIN_EL = 15.0
NIGHT_SUN_EL = -12.0
NIGHT_BACKGROUND = 2e-6  # dark counts plus stray light per detector gate at night
MICIUS_APERTURE_M = 0.30
STEP_S = 30
HOURS = 24
START = datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc)

CITIES = {
    "delingha": ("Delingha", 37.37, 97.73), "lijiang": ("Lijiang", 26.69, 100.03),
    "xinglong": ("Xinglong", 40.40, 117.58), "nanshan": ("Nanshan (Ürümqi)", 43.47, 87.18),
    "graz": ("Graz", 47.07, 15.44), "vienna": ("Vienna", 48.21, 16.37), "beijing": ("Beijing", 39.90, 116.40),
    "chilbolton": ("Chilbolton (RAL)", 51.1445, -1.4370), "oberpfaffenhofen": ("Oberpfaffenhofen (DLR)", 48.0833, 11.2775),
    "singapore": ("Singapore (CQT)", 1.2966, 103.7764),
    "delhi": ("Delhi", 28.61, 77.21), "mumbai": ("Mumbai", 19.08, 72.88), "bengaluru": ("Bengaluru", 12.97, 77.59),
    "london": ("London", 51.51, -0.13), "new_york": ("New York", 40.71, -74.01), "sydney": ("Sydney", -33.87, 151.21),
}
# (city a, city b, label, satellite the pair belongs to or None for any)
PAIRS = [("chilbolton", "singapore", "SpeQtre's two ground stations", "speqtre"),
         ("oberpfaffenhofen", "chilbolton", "QUBE-II: Oberpfaffenhofen and Chilbolton", "qube2"),
         ("delingha", "lijiang", "Micius 2017: entanglement over 1,203 km", "micius"),
         ("xinglong", "graz", "Micius 2017: the first intercontinental quantum key", "micius"),
         ("delhi", "mumbai", "Two Indian cities", None), ("london", "new_york", "Across the Atlantic", None)]


def julian(t: datetime) -> float:
    return t.timestamp() / 86400.0 + 2440587.5


def gmst(jd: np.ndarray) -> np.ndarray:
    """Greenwich mean sidereal time, IAU-82 (the angle SGP4's TEME frame is defined with), in radians."""
    tut1 = (np.asarray(jd, dtype=float) - 2451545.0) / 36525.0
    sec = -6.2e-6 * tut1 ** 3 + 0.093104 * tut1 ** 2 + (876600.0 * 3600 + 8640184.812866) * tut1 + 67310.54841
    return np.radians(sec / 240.0) % (2 * np.pi)


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


def up_vector(lat: float, lon: float) -> np.ndarray:
    """The local vertical: the WGS84 ellipsoid's normal at geodetic (lat, lon)."""
    la, lo = math.radians(lat), math.radians(lon)
    return np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)])


def station(lat: float, lon: float, h_km: float = 0.0) -> np.ndarray:
    """Earth-fixed position of a point at geodetic (lat, lon) and height h on the WGS84 ellipsoid."""
    la, lo = math.radians(lat), math.radians(lon)
    n = R_E / math.sqrt(1 - E2 * math.sin(la) ** 2)
    return np.array([(n + h_km) * math.cos(la) * math.cos(lo), (n + h_km) * math.cos(la) * math.sin(lo),
                     (n * (1 - E2) + h_km) * math.sin(la)])


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


def elevation(sat: np.ndarray, sta: np.ndarray, up: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Elevation in degrees above the station's horizon (the plane normal to ``up``) and slant range in km."""
    d = sat - sta
    rng = np.linalg.norm(d, axis=-1)
    up = sta / np.linalg.norm(sta) if up is None else up
    return np.degrees(np.arcsin(np.clip((d @ up) / rng, -1, 1))), rng


def azimuth(sat: np.ndarray, sta: np.ndarray, lat: float, lon: float) -> np.ndarray:
    """Azimuth in degrees east of north."""
    la, lo = math.radians(lat), math.radians(lon)
    east = np.array([-math.sin(lo), math.cos(lo), 0.0])
    north = np.array([-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la)])
    d = sat - sta
    return np.degrees(np.arctan2(d @ east, d @ north)) % 360


def sun_elevation(sun_ecef: np.ndarray, up: np.ndarray) -> np.ndarray:
    up = up / np.linalg.norm(up)
    return np.degrees(np.arcsin(np.clip(sun_ecef @ up, -1, 1)))


def subpoint(sat: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Geodetic latitude, longitude and height (km) under each Earth-fixed position (Bowring's method)."""
    x, y, z = sat[..., 0], sat[..., 1], sat[..., 2]
    p = np.hypot(x, y)
    b = R_E * (1 - F_E)
    ep2 = (R_E ** 2 - b ** 2) / b ** 2
    th = np.arctan2(z * R_E, p * b)
    lat = np.arctan2(z + ep2 * b * np.sin(th) ** 3, p - E2 * R_E * np.cos(th) ** 3)
    n = R_E / np.sqrt(1 - E2 * np.sin(lat) ** 2)
    h = p / np.cos(lat) - n
    return np.degrees(lat), np.degrees(np.arctan2(y, x)), h


def downlink_loss_db(slant_km: float, el_deg: float, tx_aperture_m: float | None = None) -> float:
    base = ph.free_space_loss(slant_km, satellite=True, tx_aperture_m=tx_aperture_m)
    airmass = 1 / math.sin(math.radians(max(el_deg, 1.0)))
    return base.total_db - ph.DOWNLINK_ATMOSPHERE_DB + ph.DOWNLINK_ATMOSPHERE_DB * airmass / math.sqrt(2)


def entanglement_rate(la: float, ea: float, lb: float, eb: float) -> tuple[float, float]:
    from inkubit.network.model import simulate
    from inkubit.spec.models import NetworkSpec

    spec = NetworkSpec.model_validate({
        "nodes": [{"id": "a", "type": "ground_station"}, {"id": "s", "type": "satellite"}, {"id": "b", "type": "ground_station"}],
        "links": [{"from": "a", "to": "s", "medium": "free_space", "length_km": la, "loss_db": downlink_loss_db(la, ea)},
                  {"from": "s", "to": "b", "medium": "free_space", "length_km": lb, "loss_db": downlink_loss_db(lb, eb)}],
        "source": "a", "destination": "b"})
    e = simulate(spec).end_to_end
    return e.pair_rate_hz, e.key_rate_bps


def bb84_key_rate(slant_km: float, el_deg: float, tx_aperture_m: float | None = None) -> float:
    eta = 10 ** (-downlink_loss_db(slant_km, el_deg, tx_aperture_m) / 10) * ph.FREE_SPACE_DETECTOR_EFF
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
    cloud_a: float | None = None  # forecast cloud cover at the station(s) during the pass, percent
    cloud_b: float | None = None
    expected_key_bits: float | None = None  # key_bits times the clear-sky fraction


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
    satellite: dict[str, Any] = {}
    alt_km: list[float] = []  # height above the ellipsoid (every 10 steps)
    now_index: float | None = None  # where "now" falls on the track, for a real satellite
    expected_trusted_key_bits: float | None = None  # with the cloud forecast
    clouds: str | None = None  # where the cloud forecast came from, if any
    outlook: list[dict[str, Any]] = []  # a real satellite's next days: passes and key per 24 hours


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


CloudFn = Callable[[str, float], "float | None"]  # (side "a"|"b", unix time) -> cloud cover percent


def check_pair(a_id: str, b_id: str) -> None:
    if a_id not in CITIES or b_id not in CITIES or a_id == b_id:
        raise ValueError("choose two different cities from the list")


def geometry(a_id: str, b_id: str, sat: np.ndarray, jd: np.ndarray, night_only: bool) -> dict[str, np.ndarray]:
    """Elevations, slant ranges and night flags at both stations for Earth-fixed satellite positions ``sat``."""
    sun = _rot_z(sun_eci(jd), gmst(jd))
    out: dict[str, np.ndarray] = {"sun": sun}
    for side, cid in (("a", a_id), ("b", b_id)):
        _, lat, lon = CITIES[cid]
        sta, up = station(lat, lon), up_vector(lat, lon)
        el, rg = elevation(sat, sta, up)
        night = sun_elevation(sun, up) < NIGHT_SUN_EL if night_only else np.ones_like(el, bool)
        out |= {f"el_{side}": el, f"rg_{side}": rg, f"night_{side}": night, f"vis_{side}": (el >= MIN_EL) & night}
    return out


def find_passes(g: dict[str, np.ndarray], times: np.ndarray, start: datetime, *, dual: bool,
                tx_aperture_m: float | None, cloud: CloudFn | None = None) -> list[Pass]:
    """Every usable pass: shared windows (entanglement, only for a satellite with two downlinks) and each station's
    own downlink passes, with the key each gives and, under a cloud forecast, the key to expect."""
    t0 = start.timestamp()

    def clouds(i: int, j: int, sides: str) -> list[float | None]:
        mid = t0 + float(times[(i + j) // 2])
        return [cloud(s, mid) if cloud else None for s in sides]

    def clear(cc: list[float | None]) -> float | None:
        if not cloud or any(c is None for c in cc):
            return None
        return float(np.prod([1 - c / 100 for c in cc]))  # type: ignore[operator]

    passes: list[Pass] = []
    if dual:
        for i, j in _windows(g["vis_a"] & g["vis_b"]):
            pairs = key = 0.0
            for k in range(i, j + 1):
                p, kr = entanglement_rate(float(g["rg_a"][k]), float(g["el_a"][k]), float(g["rg_b"][k]), float(g["el_b"][k]))
                pairs += p * STEP_S
                key += kr * STEP_S
            cc = clouds(i, j, "ab")
            f = clear(cc)
            passes.append(Pass(start_utc=(start + timedelta(seconds=float(times[i]))).isoformat(), minutes=(j - i + 1) * STEP_S / 60,
                               max_el_a=round(float(g["el_a"][i:j + 1].max()), 1), max_el_b=round(float(g["el_b"][i:j + 1].max()), 1),
                               pairs=pairs, key_bits=key, kind="both", cloud_a=cc[0], cloud_b=cc[1],
                               expected_key_bits=None if f is None else key * f))
    for side in ("a", "b"):
        el, rg = g[f"el_{side}"], g[f"rg_{side}"]
        for i, j in _windows(g[f"vis_{side}"]):
            key = sum(bb84_key_rate(float(rg[k]), float(el[k]), tx_aperture_m) * STEP_S for k in range(i, j + 1))
            cc = clouds(i, j, side)
            f = clear(cc)
            passes.append(Pass(start_utc=(start + timedelta(seconds=float(times[i]))).isoformat(),
                               minutes=(j - i + 1) * STEP_S / 60, max_el_a=round(float(el[i:j + 1].max()), 1),
                               max_el_b=None, pairs=None, key_bits=key, kind=side,
                               cloud_a=cc[0] if side == "a" else None, cloud_b=cc[0] if side == "b" else None,
                               expected_key_bits=None if f is None else key * f))
    passes.sort(key=lambda p: p.start_utc)
    return passes


def totals(passes: list[Pass]) -> dict[str, float | None]:
    """Per-station and shared key over a list of passes, clear sky and (if every pass has a forecast) expected."""
    key = {s: sum(p.key_bits for p in passes if p.kind == s) for s in "ab"}
    exp = None
    if passes and all(p.expected_key_bits is not None for p in passes):
        exp = min(sum(p.expected_key_bits for p in passes if p.kind == s) for s in "ab")  # type: ignore[misc]
    both = [p for p in passes if p.kind == "both"]
    return {"key_a": key["a"], "key_b": key["b"], "trusted": min(key["a"], key["b"]), "expected_trusted": exp,
            "pairs": sum(p.pairs or 0.0 for p in both), "shared": sum(p.key_bits for p in both), "n_both": len(both)}


def assemble(a_id: str, b_id: str, sat: np.ndarray, g: dict[str, np.ndarray], start: datetime, passes: list[Pass],
             finding: str, steps: int, **extra: Any) -> Plan:
    (na, la_, loa), (nb, lb_, lob) = CITIES[a_id], CITIES[b_id]
    t = totals(passes)
    sub_lat, sub_lon, h = subpoint(sat[:steps])
    sun = g["sun"][:steps]
    sun_lat = np.degrees(np.arcsin(sun[:, 2]))
    sun_lon = np.degrees(np.arctan2(sun[:, 1], sun[:, 0]))
    return Plan(city_a={"id": a_id, "name": na, "lat": la_, "lon": loa}, city_b={"id": b_id, "name": nb, "lat": lb_, "lon": lob},
                distance_km=round(_great_circle((la_, loa), (lb_, lob)), 1), start_utc=start.isoformat(), step_s=STEP_S,
                track=[(round(float(x), 3), round(float(y), 3)) for x, y in zip(sub_lat, sub_lon)],
                sun=[(round(float(x), 2), round(float(y), 2)) for x, y in zip(sun_lat[::10], sun_lon[::10])],
                alt_km=[round(float(v), 1) for v in h[::10]],
                el_a=[round(float(v), 1) for v in g["el_a"][:steps]], el_b=[round(float(v), 1) for v in g["el_b"][:steps]],
                night_a=[bool(v) for v in g["night_a"][:steps]], night_b=[bool(v) for v in g["night_b"][:steps]],
                passes=passes, shared_key_bits_per_day=float(t["shared"]), entangled_pairs_per_day=float(t["pairs"]),
                trusted_key_bits_per_day=float(t["trusted"]), expected_trusted_key_bits=t["expected_trusted"],
                finding=finding, **extra)


MICIUS = {"id": "micius", "name": "Micius", "norad": 41731, "real": False, "aperture_mm": 300, "dual": True,
          "status": "re-entered 25 January 2026", "launched": "2016-08-16",
          "note": "China's quantum science satellite (USTC and CAS), with two 300 mm downlink telescopes; it did the "
                  "2017 entanglement, key and teleportation experiments and re-entered on 25 January 2026, so its "
                  "orbit here is modelled (500 km, 97.4°, sun-synchronous) over a fixed day."}


@lru_cache(maxsize=32)
def _model_plan(a_id: str, b_id: str, night_only: bool) -> Plan:
    times = np.arange(0, HOURS * 3600, STEP_S, dtype=float)
    jd = julian(START) + times / 86400.0
    sat = orbit_ecef(times, jd)
    g = geometry(a_id, b_id, sat, jd, night_only)
    passes = find_passes(g, times, START, dual=True, tx_aperture_m=MICIUS_APERTURE_M)
    t = totals(passes)
    na, nb = CITIES[a_id][0], CITIES[b_id][0]
    dist = _great_circle(CITIES[a_id][1:], CITIES[b_id][1:])
    if t["n_both"]:
        n = int(t["n_both"])
        ent = (f"On {n} pass{'es' if n != 1 else ''} both cities see the satellite at night at once, sharing "
               f"{t['pairs']:,.0f} entangled pairs and {t['shared']:,.0f} key bits that nobody, not even the "
               "satellite, knows.")
    else:
        ent = (f"The cities are {dist:,.0f} km apart: no pass lets both see the satellite at night at the same time, "
               "so entanglement-based keys are impossible from one satellite.")
    finding = (f"{ent} As a trusted node the satellite gives {na} {t['key_a']:,.0f} and {nb} {t['key_b']:,.0f} key bits "
               f"a day, so the cities can share {t['trusted']:,.0f} bits a day if they trust the satellite.")
    return assemble(a_id, b_id, sat, g, START, passes, finding, len(times), satellite=MICIUS)


def plan(a_id: str, b_id: str, night_only: bool = True, sat: str = "micius") -> Plan:
    """Micius on its modelled orbit over a fixed day, or a satellite in orbit today on its real orbit from now."""
    check_pair(a_id, b_id)
    if sat == "micius":
        return _model_plan(a_id, b_id, night_only)
    from inkubit.satellites import real_plan

    return real_plan(sat, a_id, b_id, night_only)
