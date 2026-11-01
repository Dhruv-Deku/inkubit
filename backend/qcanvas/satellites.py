"""Quantum satellites in orbit today, on their real orbits: elements from CelesTrak, SGP4, and the cloud forecast.

Micius, which did the 2017 experiments, re-entered on 25 January 2026, and Jinan-1, the 2022 quantum
microsatellite, on 15 April 2025 (CelesTrak's satellite catalogue), so the planner's Micius flies a modelled orbit.
Two quantum-key satellites are up now and fly here on their real orbits:
* SpeQtre (NORAD 66769): RAL Space and SpeQtral, a 12U CubeSat with an entangled-photon source and an 80 mm
  telescope, deployed 28 November 2025; ground stations at Chilbolton and in Singapore.
* QUBE-II (NORAD 69023): a German 8U CubeSat with an 85 mm telescope for prepare-and-measure keys, launched
  3 May 2026.

Elements: CelesTrak's general perturbations data as two-line elements, fetched at most every two hours and checked
against their checksums and catalogue number; if CelesTrak cannot be reached, the last good copy, then a snapshot
shipped with the app, labelled with its age. Propagation: SGP4, the model the elements are fitted for (Vallado's
implementation in the sgp4 package), to the TEME frame, then Earth-fixed through Greenwich mean sidereal time
(IAU-82, as TEME is defined; polar motion and UT1-UTC are left out, under 30 m on the ground). The frame chain is
checked against Skyfield in the tests. Clouds: Open-Meteo's hourly forecast of total cloud cover at each station; an
optical link needs a clear line of sight, so a pass's expected key is its clear-sky key times the clear fraction,
a first approximation (a low pass looks through more sky than the zenith the forecast describes).

Key per pass uses the planner's decoy-state downlink with each satellite's own telescope aperture; the real payloads'
source rates and protocols differ, so the key bits are estimates while the pass times, elevations and clouds are
real data.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from qcanvas.orbits import (
    CITIES, STEP_S, Plan, _rot_z, assemble, find_passes, geometry, gmst, julian, subpoint, totals,
)

log = logging.getLogger("qcanvas.satellites")

CELESTRAK = "https://celestrak.org/NORAD/elements/gp.php"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
SNAPSHOT = Path(__file__).parent / "data" / "tle_snapshot.json"
TLE_TTL_S = 2 * 3600  # CelesTrak updates about every two hours and asks not to be polled faster
RETRY_S = 600  # after a failed fetch
CLOUD_TTL_S = 3600
OUTLOOK_DAYS = 7

SATELLITES: dict[str, dict[str, Any]] = {
    "speqtre": {
        "name": "SpeQtre", "norad": 66769, "aperture_mm": 80, "launched": "2025-11-28",
        "note": "RAL Space (UK) and SpeQtral (Singapore): a 12U CubeSat with an entangled-photon source and an 80 mm "
                "telescope, deployed on 28 November 2025. One photon of each pair is measured on board and the other "
                "sent down, so each ground station gets its own key and the satellite is a trusted node. Its ground "
                "stations are at Chilbolton and in Singapore.",
    },
    "qube2": {
        "name": "QUBE-II", "norad": 69023, "aperture_mm": 85, "launched": "2026-05-03",
        "note": "A German mission (Zentrum für Telematik, DLR and partners): an 8U CubeSat with an 85 mm telescope "
                "for prepare-and-measure quantum keys to an optical ground station, launched on 3 May 2026.",
    },
}


@dataclass(frozen=True)
class Elements:
    norad: int
    name: str
    line1: str
    line2: str
    source: str  # "CelesTrak" | "CelesTrak, last good copy" | "snapshot shipped with the app"
    fetched_utc: str

    def satrec(self):
        from sgp4.api import Satrec

        return Satrec.twoline2rv(self.line1, self.line2)

    @property
    def epoch(self) -> datetime:
        s = self.satrec()
        return datetime.fromtimestamp((s.jdsatepoch + s.jdsatepochF - 2440587.5) * 86400.0, tz=timezone.utc)


def _checksum(line: str) -> int:
    return sum(int(c) if c.isdigit() else 1 if c == "-" else 0 for c in line[:68]) % 10


def parse_tle(text: str, norad: int) -> tuple[str, str, str]:
    """(name, line 1, line 2) from CelesTrak's three-line format, refusing anything malformed."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    l1 = next((ln for ln in lines if ln.startswith("1 ")), "")
    l2 = next((ln for ln in lines if ln.startswith("2 ")), "")
    for ln in (l1, l2):
        if len(ln) < 69 or not ln[68].isdigit() or _checksum(ln) != int(ln[68]):
            raise ValueError(f"bad element line for {norad}: {ln[:30]!r}")
    if int(l1[2:7]) != norad or int(l2[2:7]) != norad:
        raise ValueError(f"elements are for another satellite than {norad}")
    name = lines[lines.index(l1) - 1].strip() if lines.index(l1) > 0 else str(norad)
    return name, l1, l2


def _http(url: str, params: dict[str, Any]) -> httpx.Response:
    r = httpx.get(url, params=params, timeout=8.0, headers={"User-Agent": "Q-Canvas satellite planner"})
    r.raise_for_status()
    return r


def snapshot(norad: int) -> Elements:
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    name, l1, l2 = data["satellites"][str(norad)]
    return Elements(norad, name, l1, l2, "snapshot shipped with the app", data["fetched_utc"])


_lock = threading.Lock()
_tles: dict[int, tuple[float, Elements]] = {}


def elements(norad: int) -> Elements:
    """Today's elements: CelesTrak (cached two hours), else the last good copy, else the shipped snapshot."""
    now = time.time()
    with _lock:
        hit = _tles.get(norad)
    if hit and now - hit[0] < (TLE_TTL_S if hit[1].source == "CelesTrak" else RETRY_S):
        return hit[1]
    try:
        name, l1, l2 = parse_tle(_http(CELESTRAK, {"CATNR": norad, "FORMAT": "TLE"}).text, norad)
        el = Elements(norad, name, l1, l2, "CelesTrak", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    except (httpx.HTTPError, ValueError) as err:
        log.warning("CelesTrak elements for %s unavailable (%s)", norad, err)
        el = replace(hit[1], source="CelesTrak, last good copy") if hit and hit[1].source != "snapshot shipped with the app" \
            else snapshot(norad)
    with _lock:
        _tles[norad] = (now, el)
    return el


def propagate(el: Elements, start: datetime, seconds: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Earth-fixed positions (km) and inertial speeds (km/s) by SGP4 at ``start + seconds``."""
    from sgp4.api import SGP4_ERRORS

    jd0 = julian(start)
    whole = math.floor(jd0)
    jd = np.full(len(seconds), float(whole))
    fr = (jd0 - whole) + np.asarray(seconds, dtype=float) / 86400.0
    err, r, v = el.satrec().sgp4_array(jd, fr)
    bad = np.flatnonzero(err)
    if bad.size:
        raise ValueError(f"SGP4 cannot propagate {el.name}: {SGP4_ERRORS.get(int(err[bad[0]]), 'error')}")
    return _rot_z(r, gmst(jd + fr)), np.linalg.norm(v, axis=1)


_cloud_cache: dict[tuple, tuple[float, list[tuple[np.ndarray, np.ndarray]] | None]] = {}


def cloud_forecast(points: list[tuple[float, float]], days: int = OUTLOOK_DAYS + 1) -> list[tuple[np.ndarray, np.ndarray]] | None:
    """Hourly total cloud cover (unix times, percent) at each point from Open-Meteo, or None if unreachable."""
    key = tuple((round(a, 3), round(b, 3)) for a, b in points)
    now = time.time()
    with _lock:
        hit = _cloud_cache.get(key)
    if hit and now - hit[0] < (CLOUD_TTL_S if hit[1] is not None else RETRY_S):
        return hit[1]
    try:
        data = _http(OPEN_METEO, {"latitude": ",".join(f"{a:.4f}" for a, _ in points),
                                  "longitude": ",".join(f"{b:.4f}" for _, b in points),
                                  "hourly": "cloud_cover", "forecast_days": days, "timezone": "UTC"}).json()
        data = data if isinstance(data, list) else [data]
        out = []
        for d in data:
            ts = np.array([datetime.fromisoformat(t).replace(tzinfo=timezone.utc).timestamp() for t in d["hourly"]["time"]])
            cc = np.array([np.nan if v is None else float(v) for v in d["hourly"]["cloud_cover"]])
            out.append((ts, cc))
        if len(out) != len(points):
            raise ValueError("forecast for the wrong number of places")
    except (httpx.HTTPError, ValueError, KeyError) as err:
        log.warning("cloud forecast unavailable (%s)", err)
        out = None
    with _lock:
        _cloud_cache[key] = (now, out)
    return out


def cloud_at(series: tuple[np.ndarray, np.ndarray], t: float) -> float | None:
    ts, cc = series
    if not len(ts) or t < ts[0] or t > ts[-1]:
        return None
    v = float(np.interp(t, ts, cc))
    return None if math.isnan(v) else round(v, 1)


@lru_cache(maxsize=64)
def _real_plan(sat_id: str, a_id: str, b_id: str, night_only: bool, start_iso: str, el: Elements) -> Plan:
    info = SATELLITES[sat_id]
    start = datetime.fromisoformat(start_iso)
    times = np.arange(0, OUTLOOK_DAYS * 86400, STEP_S, dtype=float)
    pos, speed = propagate(el, start, times)
    jd = julian(start) + times / 86400.0
    g = geometry(a_id, b_id, pos, jd, night_only)
    fc = cloud_forecast([CITIES[a_id][1:], CITIES[b_id][1:]])
    cloud = (lambda side, t: cloud_at(fc[0 if side == "a" else 1], t)) if fc else None
    passes = find_passes(g, times, start, dual=False, tx_aperture_m=info["aperture_mm"] / 1000, cloud=cloud)
    day = 86400 // STEP_S
    outlook = []
    for d in range(OUTLOOK_DAYS):
        lo, hi = (start + timedelta(days=d)).isoformat(), (start + timedelta(days=d + 1)).isoformat()
        ps = [p for p in passes if lo <= p.start_utc < hi]
        t = totals(ps)
        clouds = {s: [c for p in ps if p.kind == s and (c := (p.cloud_a if s == "a" else p.cloud_b)) is not None] for s in "ab"}
        outlook.append({"from_utc": lo, "passes_a": sum(p.kind == "a" for p in ps), "passes_b": sum(p.kind == "b" for p in ps),
                        "key_a": t["key_a"], "key_b": t["key_b"], "trusted": t["trusted"], "expected_trusted": t["expected_trusted"],
                        "cloud_a": round(float(np.mean(clouds["a"])), 0) if clouds["a"] else None,
                        "cloud_b": round(float(np.mean(clouds["b"])), 0) if clouds["b"] else None})
    first = [p for p in passes if p.start_utc < (start + timedelta(days=1)).isoformat()]
    t = totals(first)
    _, _, h = subpoint(pos[:day])
    epoch = el.epoch
    sat_rec = el.satrec()
    satellite = {
        "id": sat_id, "name": info["name"], "norad": el.norad, "real": True, "aperture_mm": info["aperture_mm"],
        "dual": False, "status": "in orbit", "launched": info["launched"], "note": info["note"],
        "elements": {"source": el.source, "epoch_utc": epoch.isoformat(timespec="seconds"), "fetched_utc": el.fetched_utc,
                     "age_hours": round((start - epoch).total_seconds() / 3600, 1), "line1": el.line1, "line2": el.line2},
        "height_km": [round(float(h.min()), 1), round(float(h.max()), 1)], "speed_kms": round(float(speed.mean()), 2),
        "period_min": round(2 * math.pi / sat_rec.no_kozai, 1), "inclination_deg": round(math.degrees(sat_rec.inclo), 2),
    }
    na, nb = CITIES[a_id][0], CITIES[b_id][0]
    pa, pb = sum(p.kind == "a" for p in first), sum(p.kind == "b" for p in first)
    times_word = lambda n: "once" if n == 1 else "twice" if n == 2 else f"{n} times"  # noqa: E731
    finding = (f"{info['name']} is in orbit now, {satellite['height_km'][0]:.0f}–{satellite['height_km'][1]:.0f} km up. "
               f"In the next 24 hours it rises above 15° over {na} at night {times_word(pa) if pa else 'never'} and over "
               f"{nb} {times_word(pb) if pb else 'never'}. ")
    if pa and pb:
        finding += (f"With its {info['aperture_mm']} mm telescope a clear sky would give {na} {t['key_a']:,.0f} and {nb} "
                    f"{t['key_b']:,.0f} key bits, so the two could share {t['trusted']:,.0f} bits through the satellite")
        finding += (f"; the cloud forecast leaves about {t['expected_trusted']:,.0f}." if t["expected_trusted"] is not None else ".")
    else:
        finding += "Without a night pass over both, no key can be shared through it today."
    scored = [o for o in outlook if (o["expected_trusted"] if o["expected_trusted"] is not None else o["trusted"]) > 0]
    if scored:
        best = max(scored, key=lambda o: o["expected_trusted"] if o["expected_trusted"] is not None else o["trusted"])
        val = best["expected_trusted"] if best["expected_trusted"] is not None else best["trusted"]
        when = datetime.fromisoformat(best["from_utc"]).strftime("%a %d %b %H:%M UTC")
        finding += f" Best 24 hours of the next {OUTLOOK_DAYS} days: from {when}, about {val:,.0f} shared bits" + \
            (" expected under the forecast." if best["expected_trusted"] is not None else " under a clear sky.")
    return assemble(a_id, b_id, pos, g, start, first, finding, day, satellite=satellite, outlook=outlook,
                    clouds="Open-Meteo hourly cloud-cover forecast" if fc else None)


def real_plan(sat_id: str, a_id: str, b_id: str, night_only: bool = True, now: datetime | None = None) -> Plan:
    if sat_id not in SATELLITES:
        raise ValueError(f"unknown satellite {sat_id!r}; choose one of micius, {', '.join(SATELLITES)}")
    now = now or datetime.now(timezone.utc)
    start = now.replace(minute=now.minute - now.minute % 10, second=0, microsecond=0)
    el = elements(SATELLITES[sat_id]["norad"])
    p = _real_plan(sat_id, a_id, b_id, night_only, start.isoformat(), el)
    return p.model_copy(update={"now_index": round((now - start).total_seconds() / STEP_S, 3)})


def save_snapshot() -> None:
    """Refresh the shipped snapshot from CelesTrak (python -m qcanvas.satellites)."""
    sats = {}
    for info in SATELLITES.values():
        name, l1, l2 = parse_tle(_http(CELESTRAK, {"CATNR": info["norad"], "FORMAT": "TLE"}).text, info["norad"])
        sats[str(info["norad"])] = [name, l1, l2]
    SNAPSHOT.write_text(json.dumps({"fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                    "source": "CelesTrak GP, FORMAT=TLE", "satellites": sats}, indent=1) + "\n",
                        encoding="utf-8")
    print(f"wrote {SNAPSHOT}")


if __name__ == "__main__":
    save_snapshot()
