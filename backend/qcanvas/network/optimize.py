"""Candidate fixes for a network bottleneck, each producing a new, valid spec."""

from __future__ import annotations

from dataclasses import dataclass

from qcanvas.network import physics as ph
from qcanvas.network.model import NetworkMetrics, simulate
from qcanvas.spec.models import Link, NetworkSpec, Node, Position
from qcanvas.spec.validation import parse_spec

MIN_SLANT_KM = 500.0  # a LEO satellite at ~500 km is never closer than overhead
MAX_T2_MS = 10_000.0
MAX_APERTURE_M = 1.8  # the Lijiang ground telescope used with Micius


@dataclass
class Candidate:
    """One proposed change and its simulated outcome."""

    kind: str
    description: str
    spec: NetworkSpec
    metrics: NetworkMetrics

    @property
    def score(self) -> tuple[float, float]:
        return score(self.metrics)


def score(m: NetworkMetrics) -> tuple[float, float]:
    """(secret key rate, pairs/s weighted by how far fidelity is above a fully mixed state).

    The second part gives credit for progress before any key exists, e.g. a relay that
    makes pairs faster even though memories still spoil them.
    """
    e = m.end_to_end
    return (e.key_rate_bps, e.pair_rate_hz * max(0.0, e.fidelity - 0.25))


def improves(new: NetworkMetrics, old: NetworkMetrics, margin: float = 0.01) -> bool:
    """True if ``new`` is meaningfully better: more key, or (with no key either way) more useful pairs."""
    (nk, nu), (ok, ou) = score(new), score(old)
    if nk > 0 or ok > 0:
        return nk > ok * (1 + margin)
    return nu > ou * (1 + margin) + 1e-15


def _find_link(spec: NetworkSpec, a: str, b: str) -> int:
    return next(i for i, l in enumerate(spec.links) if {l.from_node, l.to_node} == {a, b})


def _rebuild(spec: NetworkSpec, **changes) -> NetworkSpec:
    data = spec.model_dump(by_alias=True, exclude_none=True)
    data.update(changes)
    return parse_spec(data)  # type: ignore[return-value]


def _midpoint_relay(spec: NetworkSpec, a: str, b: str) -> tuple[str, NetworkSpec] | None:
    i = _find_link(spec, a, b)
    link = spec.links[i]
    if "satellite" in (spec.node(a).type, spec.node(b).type):
        return None
    na, nb = spec.node(a), spec.node(b)
    t2 = max([n.memory_t2_ms or ph.DEFAULT_T2_MS for n in spec.nodes if n.type == "repeater"] or [ph.DEFAULT_T2_MS])
    k = 1
    while any(n.id == f"relay{k}" for n in spec.nodes):
        k += 1
    pos = None
    if na.position and nb.position:
        pos = Position(x=(na.position.x + nb.position.x) / 2, y=(na.position.y + nb.position.y) / 2 + 40)
    relay = Node(id=f"relay{k}", type="repeater", label=f"Relay {k}", memory_t2_ms=t2, position=pos)
    half = link.length_km / 2
    links = [l.model_dump(by_alias=True, exclude_none=True) for j, l in enumerate(spec.links) if j != i]
    links.insert(i, Link(**{"from": a, "to": relay.id, "medium": link.medium, "length_km": half}).model_dump(by_alias=True, exclude_none=True))
    links.insert(i + 1, Link(**{"from": relay.id, "to": b, "medium": link.medium, "length_km": half}).model_dump(by_alias=True, exclude_none=True))
    nodes = [n.model_dump(by_alias=True, exclude_none=True) for n in spec.nodes] + [relay.model_dump(exclude_none=True)]
    desc = f"add a relay at the middle of {a} → {b} ({link.length_km:,.0f} km becomes 2 × {half:,.0f} km)"
    return desc, _rebuild(spec, nodes=nodes, links=links)


def _rebalance(spec: NetworkSpec, m: NetworkMetrics, a: str, b: str) -> tuple[str, NetworkSpec] | None:
    """Move a repeater at one end of the weak fiber span toward the other end."""
    path = m.path
    i, j = path.index(a), path.index(b)
    options = []
    for mover, neighbor in ((path[i], path[i - 1] if i > 0 else None), (path[j], path[j + 1] if j + 1 < len(path) else None)):
        if neighbor is None or spec.node(mover).type != "repeater":
            continue
        weak = spec.links[_find_link(spec, a, b)]
        other = spec.links[_find_link(spec, mover, neighbor)]
        if other.medium != "fiber" or weak.medium != "fiber" or other.length_km >= weak.length_km:
            continue
        shift = (weak.length_km - other.length_km) / 2
        options.append((other.length_km, mover, neighbor, shift, weak, other))
    if not options:
        return None
    _, mover, neighbor, shift, weak, other = min(options, key=lambda o: o[0])
    links = [l.model_dump(by_alias=True, exclude_none=True) for l in spec.links]
    links[_find_link(spec, a, b)]["length_km"] = weak.length_km - shift
    links[_find_link(spec, mover, neighbor)]["length_km"] = other.length_km + shift
    desc = (f"move {mover} {shift:,.0f} km toward {'the far end' if neighbor is None else (b if mover == a else a)}: "
            f"spans {other.length_km:,.0f}/{weak.length_km:,.0f} km become {other.length_km + shift:,.0f}/"
            f"{weak.length_km - shift:,.0f} km")
    return desc, _rebuild(spec, links=links)


def _higher_pass(spec: NetworkSpec, a: str, b: str) -> tuple[str, NetworkSpec] | None:
    i = _find_link(spec, a, b)
    link = spec.links[i]
    if link.medium != "free_space" or "satellite" not in (spec.node(a).type, spec.node(b).type):
        return None
    new = max(MIN_SLANT_KM, link.length_km * 0.75)
    if new >= link.length_km:
        return None
    links = [l.model_dump(by_alias=True, exclude_none=True) for l in spec.links]
    links[i]["length_km"] = new
    desc = f"schedule a higher-elevation pass: slant range {link.length_km:,.0f} → {new:,.0f} km on {a} → {b}"
    return desc, _rebuild(spec, links=links)


def _bigger_telescope(spec: NetworkSpec, a: str, b: str) -> tuple[str, NetworkSpec] | None:
    link = spec.links[_find_link(spec, a, b)]
    if link.medium != "free_space":
        return None
    ground = next((spec.node(x) for x in (a, b) if spec.node(x).type == "ground_station"), None)
    if ground is None:
        return None
    old = ground.aperture_m or ph.RX_APERTURE_M
    new = round(min(MAX_APERTURE_M, old * 1.5), 2)
    if new <= old:
        return None
    nodes = [n.model_dump(by_alias=True, exclude_none=True) for n in spec.nodes]
    for n in nodes:
        if n["id"] == ground.id:
            n["aperture_m"] = new
    desc = f"upgrade the {ground.label or ground.id} telescope from {old:g} m to {new:g} m"
    return desc, _rebuild(spec, nodes=nodes)


def _better_memory(spec: NetworkSpec, m: NetworkMetrics) -> tuple[str, NetworkSpec] | None:
    reps = [n for n in spec.nodes if n.type == "repeater" and n.id in m.path]
    if not reps:
        return None
    old = max(n.memory_t2_ms or ph.DEFAULT_T2_MS for n in reps)
    if old >= MAX_T2_MS:
        return None
    new = min(MAX_T2_MS, old * 10)
    nodes = [n.model_dump(by_alias=True, exclude_none=True) for n in spec.nodes]
    for n in nodes:
        if n["type"] == "repeater":
            n["memory_t2_ms"] = max(n.get("memory_t2_ms", ph.DEFAULT_T2_MS), new)
    return f"upgrade repeater memories: coherence time T2 {old:g} → {new:g} ms", _rebuild(spec, nodes=nodes)


MAX_PURIFICATION_ROUNDS = 2


def _purify(spec: NetworkSpec, m: NetworkMetrics) -> tuple[str, NetworkSpec] | None:
    """One more round of entanglement purification, when errors (not rate) are what kill the key."""
    e = m.end_to_end
    if spec.purification_rounds >= MAX_PURIFICATION_ROUNDS or e.pair_rate_hz <= 0 or e.qber < 0.02:
        return None
    if all(s.fidelity_fresh <= 0.5 for s in m.segments):
        return None
    new = spec.purification_rounds + 1
    desc = (f"add {'a second round' if new == 2 else 'one round'} of entanglement purification (BBPSSW) "
            f"on every segment: two noisy pairs in, one better pair out")
    return desc, _rebuild(spec, purification_rounds=new)


def candidates(spec: NetworkSpec, m: NetworkMetrics) -> list[Candidate]:
    """Every applicable fix for the current bottleneck, each re-simulated."""
    if not m.weakest_link:
        return []
    a, b = m.weakest_link["from"], m.weakest_link["to"]
    proposals = [
        ("midpoint_relay", _midpoint_relay(spec, a, b)),
        ("rebalance", _rebalance(spec, m, a, b)),
        ("higher_pass", _higher_pass(spec, a, b)),
        ("bigger_telescope", _bigger_telescope(spec, a, b)),
        ("better_memory", _better_memory(spec, m)),
        ("purify", _purify(spec, m)),
    ]
    out = []
    for kind, proposal in proposals:
        if proposal is None:
            continue
        desc, new_spec = proposal
        out.append(Candidate(kind=kind, description=desc, spec=new_spec, metrics=simulate(new_spec)))
    return out
