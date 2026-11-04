"""The quantum internet planner on a 3D Earth: Muse Spark designs a key network between real cities, Muse Wonder
challenges the design, and exact physics decides.

Every route is one of three things that exist or are being built:

* **fiber**: one span of telecom fiber, 0.2 dB/km over the great-circle distance (real cables run longer, so this is
  the best case); the network model's entangled-pair source in the middle, BBM92 key.
* **repeaters**: the same fiber cut into equal spans by quantum-memory repeaters that store and swap entanglement
  (the network model's heralded segments, memories with a 10 ms coherence time, multiplexed).
* **satellite**: a quantum-key satellite in orbit today (SpeQtre or QUBE-II) on its real orbit from CelesTrak, as a
  trusted node: it gives each city a key on its own night passes and the two keys are combined, so the pair shares
  as many bits a day as the poorer city gets (the satellite planner's model, with the cloud forecast when it can be
  fetched). Its rate is an average over the day.

A design is scored by its weakest required pair, because a network is only as good as its worst link. The models
never compute a number: they choose cities and route types, and the physics fills in every rate. An exhaustive
search over the same options per pair shows what the best design within them would be.
"""

from __future__ import annotations

import json
import math
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from inkubit.adapters.base import ModelCall

EARTH_R = 6371.0
TODAY_MEMORY_MS = 10.0  # the network model's default quantum-memory coherence time
MAX_ROUTES = 8
MAX_REPEATERS = 12

# Major cities and the two operating satellites' ground stations (degrees).
CITIES: dict[str, tuple[str, float, float]] = {
    "delhi": ("Delhi", 28.61, 77.21), "mumbai": ("Mumbai", 19.08, 72.88), "bengaluru": ("Bengaluru", 12.97, 77.59),
    "chennai": ("Chennai", 13.08, 80.27), "kolkata": ("Kolkata", 22.57, 88.36), "hyderabad": ("Hyderabad", 17.39, 78.49),
    "karachi": ("Karachi", 24.86, 67.01), "dhaka": ("Dhaka", 23.81, 90.41), "dubai": ("Dubai", 25.20, 55.27),
    "riyadh": ("Riyadh", 24.71, 46.68), "tel_aviv": ("Tel Aviv", 32.09, 34.78), "istanbul": ("Istanbul", 41.01, 28.98),
    "cairo": ("Cairo", 30.04, 31.24), "lagos": ("Lagos", 6.52, 3.38), "nairobi": ("Nairobi", -1.29, 36.82),
    "johannesburg": ("Johannesburg", -26.20, 28.05), "cape_town": ("Cape Town", -33.92, 18.42),
    "london": ("London", 51.51, -0.13), "paris": ("Paris", 48.86, 2.35), "berlin": ("Berlin", 52.52, 13.40),
    "madrid": ("Madrid", 40.42, -3.70), "rome": ("Rome", 41.90, 12.50), "vienna": ("Vienna", 48.21, 16.37),
    "geneva": ("Geneva", 46.20, 6.14), "zurich": ("Zurich", 47.38, 8.54), "munich": ("Munich", 48.14, 11.58),
    "amsterdam": ("Amsterdam", 52.37, 4.90), "stockholm": ("Stockholm", 59.33, 18.07), "moscow": ("Moscow", 55.76, 37.62),
    "reykjavik": ("Reykjavik", 64.15, -21.94), "graz": ("Graz", 47.07, 15.44),
    "chilbolton": ("Chilbolton (RAL)", 51.1445, -1.4370), "oberpfaffenhofen": ("Oberpfaffenhofen (DLR)", 48.0833, 11.2775),
    "new_york": ("New York", 40.71, -74.01), "washington": ("Washington", 38.91, -77.04), "boston": ("Boston", 42.36, -71.06),
    "chicago": ("Chicago", 41.88, -87.63), "toronto": ("Toronto", 43.65, -79.38), "san_francisco": ("San Francisco", 37.77, -122.42),
    "los_angeles": ("Los Angeles", 34.05, -118.24), "seattle": ("Seattle", 47.61, -122.33), "anchorage": ("Anchorage", 61.22, -149.90),
    "honolulu": ("Honolulu", 21.31, -157.86), "mexico_city": ("Mexico City", 19.43, -99.13), "bogota": ("Bogotá", 4.71, -74.07),
    "lima": ("Lima", -12.05, -77.04), "sao_paulo": ("São Paulo", -23.55, -46.63), "rio": ("Rio de Janeiro", -22.91, -43.17),
    "buenos_aires": ("Buenos Aires", -34.60, -58.38), "santiago": ("Santiago", -33.45, -70.67),
    "tokyo": ("Tokyo", 35.68, 139.69), "seoul": ("Seoul", 37.57, 126.98), "beijing": ("Beijing", 39.90, 116.40),
    "shanghai": ("Shanghai", 31.23, 121.47), "hefei": ("Hefei", 31.82, 117.23), "hong_kong": ("Hong Kong", 22.32, 114.17),
    "singapore": ("Singapore (CQT)", 1.2966, 103.7764), "bangkok": ("Bangkok", 13.76, 100.50), "jakarta": ("Jakarta", -6.21, 106.85),
    "manila": ("Manila", 14.60, 120.98), "sydney": ("Sydney", -33.87, 151.21), "melbourne": ("Melbourne", -37.81, 144.96),
    "perth": ("Perth", -31.95, 115.86), "auckland": ("Auckland", -36.85, 174.76),
    "delingha": ("Delingha", 37.37, 97.73), "lijiang": ("Lijiang", 26.69, 100.03),
}

Kind = Literal["fiber", "repeaters", "satellite"]
SATS = ("speqtre", "qube2")


class Route(BaseModel):
    a: str
    b: str
    kind: Kind
    repeaters: int = Field(default=0, ge=0, le=MAX_REPEATERS)
    satellite: str | None = None
    memory_ms: float = Field(default=TODAY_MEMORY_MS, ge=0.1, le=100_000)  # repeaters' memory coherence time


class Design(BaseModel):
    routes: list[Route] = Field(min_length=1, max_length=MAX_ROUTES)
    by: str = "you"
    rationale: str = ""


def great_circle(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    c = math.sin(la1) * math.sin(la2) + math.cos(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return EARTH_R * math.acos(max(-1.0, min(1.0, c)))


def arc_points(a: tuple[float, float], b: tuple[float, float], n: int) -> list[tuple[float, float]]:
    """n+1 points along the great circle from a to b (lat, lon)."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    p = np.array([math.cos(la1) * math.cos(lo1), math.cos(la1) * math.sin(lo1), math.sin(la1)])
    q = np.array([math.cos(la2) * math.cos(lo2), math.cos(la2) * math.sin(lo2), math.sin(la2)])
    w = math.acos(max(-1.0, min(1.0, float(p @ q))))
    out = []
    for k in range(n + 1):
        t = k / n
        v = p if w < 1e-9 else (math.sin((1 - t) * w) * p + math.sin(t * w) * q) / math.sin(w)
        out.append((round(math.degrees(math.asin(max(-1.0, min(1.0, v[2])))), 4), round(math.degrees(math.atan2(v[1], v[0])), 4)))
    return out


def _ms(ms: float) -> str:
    return f"{ms / 1000:g} s" if ms >= 1000 else f"{ms:g} ms"


def _city(cid: str) -> tuple[str, float, float]:
    if cid not in CITIES:
        raise ValueError(f"unknown city {cid!r}")
    return CITIES[cid]


def _chain(a: str, b: str, km: float, repeaters: int, memory_ms: float = TODAY_MEMORY_MS):
    """The network model's spec for a fiber route with ``repeaters`` evenly spaced memory nodes."""
    from inkubit.spec.models import NetworkSpec

    names = [a] + [f"r{k + 1}" for k in range(repeaters)] + [b]
    nodes = [{"id": n, "type": "repeater", "memory_t2_ms": memory_ms} if k and k < len(names) - 1 else
             {"id": n, "type": "ground_station"} for k, n in enumerate(names)]
    span = km / (repeaters + 1)
    links = [{"from": names[k], "to": names[k + 1], "medium": "fiber", "length_km": max(span, 0.1)}
             for k in range(len(names) - 1)]
    return NetworkSpec.model_validate({"kind": "network", "nodes": nodes, "links": links, "source": a, "destination": b})


def _register(cid: str) -> None:
    """The satellite planner keys its stations by id; make sure ours are there."""
    from inkubit import orbits

    orbits.CITIES.setdefault(cid, CITIES[cid])


def evaluate_route(r: Route) -> dict[str, Any]:
    """Exact numbers for one route; the models never supply any of these."""
    na, la, loa = _city(r.a)
    nb, lb, lob = _city(r.b)
    km = great_circle((la, loa), (lb, lob))
    out: dict[str, Any] = {"a": r.a, "b": r.b, "kind": r.kind, "repeaters": r.repeaters if r.kind == "repeaters" else 0,
                           "satellite": r.satellite if r.kind == "satellite" else None,
                           "distance_km": round(km, 1), "path": arc_points((la, loa), (lb, lob), max(8, int(km / 150)))}
    if r.kind in ("fiber", "repeaters"):
        from inkubit.network.model import simulate

        n = r.repeaters if r.kind == "repeaters" else 0
        m = simulate(_chain(r.a, r.b, km, n, r.memory_ms))
        e = m.end_to_end
        span = km / (n + 1)
        out.update(memory_ms=r.memory_ms if n else None,
                   key_rate_bps=float(e.key_rate_bps), pair_rate_hz=float(e.pair_rate_hz), fidelity=round(float(e.fidelity), 4),
                   qber=round(float(e.qber), 4), loss_db=round(sum(l["loss_db"] for l in m.links), 1),
                   span_km=round(span, 1), bits_per_day=float(e.key_rate_bps) * 86400,
                   repeater_points=[arc_points((la, loa), (lb, lob), n + 1)[k] for k in range(1, n + 1)])
        if e.key_rate_bps <= 0 and n and e.pair_rate_hz > 1e-6:
            out["limit"] = (f"pairs arrive ({e.pair_rate_hz:.3g}/s) but {_ms(r.memory_ms)} memories lose them while the "
                            f"other spans herald: fidelity {e.fidelity:.3f}, error rate {e.qber:.0%}, too noisy for a key")
        elif e.key_rate_bps <= 0:
            out["limit"] = (f"{span:,.0f} km spans lose {0.2 * span:,.0f} dB each: too few photons survive to beat the "
                            "detector noise, so no secret key is left" if n else
                            f"{km:,.0f} km of fiber loses {0.2 * km:,.0f} dB: no secret key survives")
        elif n:
            out["limit"] = (f"{n} repeater{'s' if n > 1 else ''} with {_ms(r.memory_ms)} memories, {span:,.0f} km spans: the "
                            f"slowest span sets the rate (fidelity {e.fidelity:.3f}, error rate {e.qber:.1%})")
        else:
            out["limit"] = f"{0.2 * km:,.0f} dB of fiber loss sets the rate (error rate {e.qber:.1%})"
        return out
    from inkubit import satellites

    sat = r.satellite if r.satellite in SATS else "speqtre"
    _register(r.a)
    _register(r.b)
    plan = satellites.real_plan(sat, r.a, r.b)
    bits = float(plan.trusted_key_bits_per_day)  # clear sky: a network is planned for the passes, not tonight's weather
    tonight = plan.expected_trusted_key_bits
    passes = [p for p in plan.passes]
    out.update(satellite=sat, satellite_name=satellites.SATELLITES[sat]["name"], key_rate_bps=bits / 86400,
               bits_per_day=bits, bits_tonight=None if tonight is None else float(tonight),
               passes_a=sum(p.kind == "a" for p in passes), passes_b=sum(p.kind == "b" for p in passes),
               clouds=plan.clouds, height_km=plan.satellite.get("height_km"),
               pass_windows=[{"station": p.kind, "start_utc": p.start_utc, "minutes": round(p.minutes, 1),
                              "max_el": round(float(p.max_el_a if p.kind == "a" else (p.max_el_b or p.max_el_a)), 1)}
                             for p in passes][:12])
    out["limit"] = (f"{satellites.SATELLITES[sat]['name']} reaches {na} on {out['passes_a']} and {nb} on {out['passes_b']} "
                    f"night passes in the next day; as a trusted node the pair shares what the poorer city gets under a "
                    f"clear sky" + (f" (tonight's cloud forecast leaves {tonight:,.0f} bits)" if tonight is not None else "")
                    if out["passes_a"] and out["passes_b"] else
                    f"{satellites.SATELLITES[sat]['name']} has no night pass over "
                    f"{na if not out['passes_a'] else nb} in the next day, so no key")
    return out


def evaluate(design: Design) -> dict[str, Any]:
    routes = []
    for r in design.routes:
        try:
            routes.append(evaluate_route(r))
        except Exception as err:  # noqa: BLE001 - a satellite feed can fail; the route says so
            routes.append({"a": r.a, "b": r.b, "kind": r.kind, "repeaters": r.repeaters, "satellite": r.satellite,
                           "key_rate_bps": 0.0, "bits_per_day": 0.0, "error": str(err)[:200], "limit": str(err)[:200],
                           "distance_km": round(great_circle(_city(r.a)[1:], _city(r.b)[1:]), 1),
                           "path": arc_points(_city(r.a)[1:], _city(r.b)[1:], 24)})
    weakest = min(routes, key=lambda x: x["key_rate_bps"])
    return {"by": design.by, "rationale": design.rationale, "routes": routes,
            "score_bps": weakest["key_rate_bps"], "weakest": {"a": weakest["a"], "b": weakest["b"]},
            "cities": sorted({c for r in routes for c in (r["a"], r["b"])})}


def best_route(a: str, b: str) -> tuple[Route, dict[str, Any]]:
    """Exhaustive search over the same options a model can choose from: the physics' own best for one pair."""
    options = [Route(a=a, b=b, kind="fiber")] + [Route(a=a, b=b, kind="repeaters", repeaters=n) for n in range(1, MAX_REPEATERS + 1)]
    options += [Route(a=a, b=b, kind="satellite", satellite=s) for s in SATS]
    best: tuple[Route, dict[str, Any]] | None = None
    for opt in options:
        try:
            ev = evaluate_route(opt)
        except Exception:  # noqa: BLE001
            continue
        if best is None or ev["key_rate_bps"] > best[1]["key_rate_bps"] * 1.0001:
            best = (opt, ev)
    assert best is not None
    return best


# ---------- the models ----------

ROUTE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["a", "b", "kind", "repeaters", "satellite"],
                "properties": {"a": {"type": "string"}, "b": {"type": "string"},
                               "kind": {"type": "string", "enum": ["fiber", "repeaters", "satellite"]},
                               "repeaters": {"type": "integer", "description": "repeaters: 1 to 12; else 0"},
                               "satellite": {"type": "string", "enum": ["speqtre", "qube2", "none"]}}}
DESIGN_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["routes", "rationale"],
                 "properties": {"routes": {"type": "array", "minItems": 1, "maxItems": MAX_ROUTES, "items": ROUTE_SCHEMA},
                                "rationale": {"type": "string", "description": "Two sentences at most."}}}
CHALLENGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["routes", "critique"],
                    "properties": {"routes": {"type": "array", "minItems": 1, "maxItems": MAX_ROUTES, "items": ROUTE_SCHEMA},
                                   "critique": {"type": "string", "description": "Two sentences: what you changed and why."}}}

OPTIONS = ("Route options for each pair of cities that must share keys: 'fiber' (one fiber span over the great-circle "
           "distance, 0.2 dB/km loss), 'repeaters' (the same fiber cut into equal spans by 1 to 12 quantum-memory "
           "repeaters), or 'satellite' (a quantum-key satellite in orbit today on its real orbit, acting as a trusted "
           "node on night passes: 'speqtre', with an entangled-photon source and an 80 mm telescope, or 'qube2', an "
           "85 mm prepare-and-measure payload). A network is judged by its weakest pair. Use only the city ids listed.")
DESIGN_SYSTEM = ("You design quantum-key networks between real cities. " + OPTIONS + " Connect every city the request "
                 "names (a chain or a star, at most 8 routes), choose a route type for each, and say in two sentences "
                 "why. Do not compute rates: exact physics will.")
CHALLENGE_SYSTEM = ("You review another model's quantum-key network design. " + OPTIONS + " You get the design and the "
                    "exact physics for each route: its key rate and what limits it. Try to raise the weakest pair's rate: "
                    "change route types, repeater counts or satellites, or the topology between the same cities. Return "
                    "your design and, in two plain sentences a reader can follow, what you changed and why, quoting only "
                    "numbers you were given. The repeaters use today's quantum memories (10 ms coherence). If you cannot "
                    "improve it, return it unchanged and say so. If you are shown your own first attempt as scored by physics, learn "
                    "from it.")


def city_list() -> str:
    return "; ".join(f"{k} ({v[0]})" for k, v in CITIES.items())


def _routes_from(data: dict[str, Any], who: str, why: str) -> Design:
    routes = []
    for r in data.get("routes", [])[:MAX_ROUTES]:
        a, b = str(r.get("a", "")), str(r.get("b", ""))
        if a not in CITIES or b not in CITIES or a == b:
            continue
        kind = r.get("kind") if r.get("kind") in ("fiber", "repeaters", "satellite") else "fiber"
        n = max(1, min(MAX_REPEATERS, int(r.get("repeaters") or 1))) if kind == "repeaters" else 0
        sat = r.get("satellite") if kind == "satellite" and r.get("satellite") in SATS else ("speqtre" if kind == "satellite" else None)
        routes.append(Route(a=a, b=b, kind=kind, repeaters=n, satellite=sat))
    if not routes:
        raise ValueError(f"{who} named no route between known cities")
    return Design(routes=routes, by=who, rationale=str(data.get(why, ""))[:500])


def _mentioned(text: str) -> list[str]:
    low = text.lower()
    found = []
    for cid, (name, _, _) in CITIES.items():
        key = name.split(" (")[0].lower()
        i = low.find(key)
        if i >= 0:
            found.append((i, cid))
    return [c for _, c in sorted(found)]


def describe(r: Route) -> str:
    if r.kind == "satellite":
        return "SpeQtre" if r.satellite == "speqtre" else "QUBE-II"
    return f"{r.repeaters} repeater{'s' if r.repeaters != 1 else ''}" if r.kind == "repeaters" else "fiber"


def changes(old: Design, new: Design) -> str:
    """What one design changes in another, pair by pair, in words."""
    key = lambda r: frozenset((r.a, r.b))  # noqa: E731
    before, after = {key(r): r for r in old.routes}, {key(r): r for r in new.routes}
    nm = lambda r: f"{CITIES[r.a][0].split(' (')[0]}–{CITIES[r.b][0].split(' (')[0]}"  # noqa: E731
    out = [f"{nm(r)}: {describe(before[k])} → {describe(r)}" for k, r in after.items()
           if k in before and describe(before[k]) != describe(r)]
    out += [f"adds {nm(r)} by {describe(r)}" for k, r in after.items() if k not in before]
    out += [f"drops {nm(r)}" for k, r in before.items() if k not in after]
    return "; ".join(out) or "no change"


def rule_of_thumb(cities: list[str]) -> Design:
    """Offline stand-in for the designer: a chain, fiber under 150 km, repeaters every ~150 km up to 1,800 km, else
    the satellite."""
    routes = []
    for a, b in zip(cities, cities[1:]):
        km = great_circle(_city(a)[1:], _city(b)[1:])
        if km < 150:
            routes.append(Route(a=a, b=b, kind="fiber"))
        elif km <= 1800:
            routes.append(Route(a=a, b=b, kind="repeaters", repeaters=min(MAX_REPEATERS, math.ceil(km / 150) - 1)))
        else:
            routes.append(Route(a=a, b=b, kind="satellite", satellite="speqtre"))
    return Design(routes=routes, by="rule of thumb", rationale="Fiber for short hops, repeaters about every 150 km, "
                  "a satellite beyond 1,800 km.")


STEPS = [("design", "Design the network", "Muse Spark"), ("physics", "Score every route", "exact physics"),
         ("challenge", "Challenge the design", "Muse Wonder"), ("rescore", "Score the challenge", "exact physics"),
         ("search", "Best possible from these options", "exhaustive search"), ("verdict", "Verdict", "exact physics")]


class Session:
    def __init__(self, request: str):
        self.id = uuid.uuid4().hex[:12]
        self.request = request
        self.status = "running"
        self.error: str | None = None
        self.result: dict[str, Any] = {"request": request}
        self.steps = [{"id": i, "label": l, "by": b, "status": "waiting", "detail": ""} for i, l, b in STEPS]
        self.lock = threading.Lock()

    def step(self, sid: str, status: str, detail: str = "", **data: Any) -> None:
        with self.lock:
            for s in self.steps:
                if s["id"] == sid:
                    s["status"], s["detail"] = status, detail[:300]
            self.result.update(data)

    def view(self) -> dict[str, Any]:
        with self.lock:
            return {"id": self.id, "status": self.status, "error": self.error, "steps": [dict(s) for s in self.steps],
                    "result": json.loads(json.dumps(self.result, default=str))}


def _fmt(bps: float) -> str:
    if bps <= 0:
        return "no key"
    if bps >= 1000:
        return f"{bps / 1000:,.1f} kbit/s"
    if bps >= 1:
        return f"{bps:,.1f} bit/s"
    return f"{bps * 86400:,.0f} bits/day"


def _summary(ev: dict[str, Any]) -> str:
    w = next(r for r in ev["routes"] if (r["a"], r["b"]) == (ev["weakest"]["a"], ev["weakest"]["b"]))
    return f"weakest pair {CITIES[w['a']][0]}–{CITIES[w['b']][0]}: {_fmt(ev['score_bps'])}"


def run(s: Session, models: Any) -> None:
    st = models.settings
    live = st.provider == "meta" and st.has_key
    calls: list[dict[str, Any]] = []
    s.step("design", "running")
    cities = _mentioned(s.request)
    design: Design
    if live:
        try:
            data, call = models.reasoning.structured(DESIGN_SYSTEM, f"Cities: {city_list()}\n\nRequest: {s.request}",
                                                     DESIGN_SCHEMA, "network_design", effort="low", max_tokens=3000)
            calls.append(call.model_dump(mode="json"))
            design = _routes_from(data, "Muse Spark", "rationale")
        except Exception as err:  # noqa: BLE001
            if len(cities) < 2:
                raise ValueError(f"the design could not be made: {str(err)[:200]}") from None
            design = rule_of_thumb(cities)
            design.rationale += f" (Muse Spark failed: {str(err)[:120]})"
    else:
        if len(cities) < 2:
            raise ValueError("name at least two cities from the list, e.g. 'connect Delhi and London'")
        design = rule_of_thumb(cities)
    s.step("design", "done" if design.by == "Muse Spark" else "offline",
           f"{len(design.routes)} routes: " + ", ".join(f"{CITIES[r.a][0]}–{CITIES[r.b][0]} {r.kind}" for r in design.routes),
           design=design.model_dump())

    s.step("physics", "running")
    first = evaluate(design)
    s.step("physics", "done", _summary(first), first=first)

    s.step("challenge", "running")
    challenge: Design | None = None
    second: dict[str, Any] | None = None
    if live:
        def rows(ev: dict[str, Any]) -> list[dict[str, Any]]:
            return [{"a": r["a"], "b": r["b"], "kind": r["kind"], "repeaters": r.get("repeaters", 0),
                     "satellite": r.get("satellite"), "distance_km": round(r["distance_km"]),
                     "key": _fmt(r["key_rate_bps"]), "what_limits_it": r["limit"]} for r in ev["routes"]]

        tries: list[tuple[Design, dict[str, Any]]] = []
        last_err = ""
        for rnd in (1, 2):  # a second round sees how physics scored the first, as a scientist would
            facts: dict[str, Any] = {"request": s.request, "design_to_improve": {"weakest_pair": _summary(first),
                                                                                  "routes": rows(first)}}
            if tries:
                facts["your_first_attempt_as_scored_by_physics"] = {"weakest_pair": _summary(tries[-1][1]),
                                                                     "routes": rows(tries[-1][1])}
            got: Design | None = None
            for budget in (12000, 24000):  # Muse Wonder reasons at length; a cut-off answer is not JSON
                try:
                    data, call = models.reasoning.structured(CHALLENGE_SYSTEM, f"Cities: {city_list()}\n\n{json.dumps(facts)}",
                                                             CHALLENGE_SCHEMA, "network_challenge", effort="medium",
                                                             max_tokens=budget, model=st.deep_model)
                    if call.provider != "meta":
                        raise RuntimeError(call.error or "the live model did not answer")
                    calls.append(call.model_dump(mode="json"))
                    got = _routes_from(data, "Muse Wonder", "critique")
                    break
                except Exception as err:  # noqa: BLE001
                    last_err = str(err)[:160]
            if got is None:
                break
            ev = evaluate(got)
            ev["round"] = rnd
            tries.append((got, ev))
            s.step("challenge", "running" if rnd == 1 else "done", f"round {rnd}: {changes(design, got)}")
            s.step("rescore", "running", f"round {rnd}: {_summary(ev)}")
            if ev["score_bps"] > first["score_bps"] * 1.05:
                break  # it found an improvement; no need for another round
        if tries:
            challenge, second = max(tries, key=lambda t: t[1]["score_bps"])
            note = f" (best of {len(tries)} rounds)" if len(tries) > 1 else ""
            said = challenge.rationale if len(challenge.rationale) > 30 else ""
            s.step("challenge", "done", changes(design, challenge) + note + (f". {said}" if said else ""),
                   challenge=challenge.model_dump())
            s.step("rescore", "done", _summary(second) + note, second=second)
        else:
            s.step("challenge", "failed", f"Muse Wonder did not answer: {last_err}")
            s.step("rescore", "offline", "nothing to score")
    else:
        s.step("challenge", "offline", "offline: no second model to challenge the design")
        s.step("rescore", "offline", "nothing to score")

    s.step("search", "running")
    pairs = [(r.a, r.b) for r in (challenge or design).routes] if second and second["score_bps"] > first["score_bps"] \
        else [(r.a, r.b) for r in design.routes]
    best_routes, best_evals = [], []
    for a, b in pairs:
        r, ev = best_route(a, b)
        best_routes.append(r)
        best_evals.append(ev)
    weakest = min(best_evals, key=lambda x: x["key_rate_bps"])
    best = {"by": "exhaustive search", "rationale": "The best of the same options for each pair, found by trying them all.",
            "routes": best_evals, "score_bps": weakest["key_rate_bps"], "weakest": {"a": weakest["a"], "b": weakest["b"]},
            "cities": sorted({c for r in best_evals for c in (r["a"], r["b"])})}
    s.step("search", "done", _summary(best), best=best)

    s.step("verdict", "running")
    a_score, b_score = first["score_bps"], (second["score_bps"] if second else None)
    if b_score is not None and b_score > a_score * 1.05:
        winner, text = "second", (f"Physics sides with Muse Wonder: its design lifts the weakest pair from {_fmt(a_score)} "
                                  f"to {_fmt(b_score)}.")
    elif b_score is not None and b_score < a_score * 0.95:
        winner, text = "first", (f"Physics keeps Muse Spark's design: Muse Wonder's change drops the weakest pair from "
                                 f"{_fmt(a_score)} to {_fmt(b_score)}.")
    else:
        winner, text = "first", f"Both designs give the weakest pair about {_fmt(a_score)}."
    chosen = max(a_score, b_score or 0)
    gap = best["score_bps"] / chosen if chosen > 0 else (math.inf if best["score_bps"] > 0 else 1)
    text += (" The exhaustive search finds nothing better within these options." if gap <= 1.05 else
             f" The exhaustive search does better still: {_fmt(best['score_bps'])} on the weakest pair.")
    s.step("verdict", "done", text, verdict={"winner": winner, "text": text}, calls=calls, offline=not live)


_sessions: dict[str, Session] = {}
_lock = threading.Lock()


def launch(request: str, models: Any) -> Session:
    s = Session(request)
    with _lock:
        _sessions[s.id] = s
        while len(_sessions) > 12:
            _sessions.pop(next(iter(_sessions)))

    def go() -> None:
        try:
            run(s, models)
            s.status = "done"
        except Exception as err:  # noqa: BLE001 - shown on the page
            s.status, s.error = "failed", str(err)[:300]
            for st in s.steps:
                if st["status"] == "running":
                    st["status"] = "failed"

    threading.Thread(target=go, name=f"qnet-{s.id}", daemon=True).start()
    return s


def get(key: str) -> Session | None:
    with _lock:
        return _sessions.get(key)


def sky(hours: float = 3.0, step_s: int = 20) -> dict[str, Any]:
    """Where the operating quantum-key satellites are now and over the next hours: (lat, lon, height) every step."""
    from inkubit import satellites
    from inkubit.orbits import subpoint

    now = datetime.now(timezone.utc).replace(microsecond=0)
    times = np.arange(0, hours * 3600, step_s, dtype=float)
    out = []
    for sid in SATS:
        info = satellites.SATELLITES[sid]
        try:
            el = satellites.elements(info["norad"])
            pos, _ = satellites.propagate(el, now, times)
            lat, lon, h = subpoint(pos)
            out.append({"id": sid, "name": info["name"], "norad": info["norad"], "note": info["note"],
                        "source": el.source, "track": [[round(float(a), 3), round(float(b), 3), round(float(c), 1)]
                                                       for a, b, c in zip(lat, lon, h)]})
        except Exception as err:  # noqa: BLE001
            out.append({"id": sid, "name": info["name"], "error": str(err)[:160], "track": []})
    return {"start_utc": now.isoformat(), "step_s": step_s, "satellites": out}
