"""Analytic entanglement-distribution model for a NetworkSpec.

The source-destination path is split into *segments* at repeaters (nodes
with quantum memory that perform entanglement swapping). Each segment makes
heralded pairs; a satellite inside a segment is the pair source (dual
downlink). Segment pairs are Werner states; swapping multiplies Werner
parameters; waiting in memory decoheres them as exp(-t/T2).
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from inkubit.network import physics as ph
from inkubit.spec.models import Link, NetworkSpec
from inkubit.spec.validation import find_path


class LinkMetrics(BaseModel):
    """One link on the path."""

    model_config = {"populate_by_name": True}

    from_: str
    to: str
    medium: str
    length_km: float
    loss_db: float
    loss_parts: dict[str, float]
    transmissivity: float
    success_prob: float  # a photon sent into this link is detected at the far end
    pair_rate_hz: float  # heralded pairs/s of the segment this link belongs to
    fidelity: float  # fidelity of that segment's fresh pairs

    def model_dump_public(self) -> dict:
        d = self.model_dump()
        d["from"] = d.pop("from_")
        return d


class SegmentMetrics(BaseModel):
    """A run of links between swapping nodes."""

    nodes: list[str]
    length_km: float
    loss_db: float
    attempt_rate_hz: float
    success_prob: float
    pair_rate_hz: float
    fidelity_fresh: float
    fidelity_stored: float
    memory_t2_ms: float | None
    wait_s: float


class EndToEnd(BaseModel):
    """What the two end users get."""

    pair_rate_hz: float
    fidelity: float
    qber: float
    key_rate_bps: float
    swaps: int
    segments: int


class NetworkMetrics(BaseModel):
    """Full model output."""

    path: list[str]
    links: list[dict]
    segments: list[SegmentMetrics]
    end_to_end: EndToEnd
    weakest_link: dict | None


def _link_between(spec: NetworkSpec, a: str, b: str) -> Link:
    best = None
    for link in spec.links:
        if {link.from_node, link.to_node} == {a, b} and (best is None or link.length_km < best.length_km):
            best = link
    assert best is not None
    return best


def link_loss(spec: NetworkSpec, link: Link) -> ph.LinkLoss:
    """Loss of a link, honouring an explicit ``loss_db`` override."""
    if link.loss_db is not None:
        return ph.LinkLoss(link.loss_db, {"override": link.loss_db})
    if link.medium == "fiber":
        return ph.fiber_loss(link.length_km)
    a, b = spec.node(link.from_node), spec.node(link.to_node)
    satellite = "satellite" in (a.type, b.type)
    ground = b if a.type == "satellite" else a
    return ph.free_space_loss(link.length_km, satellite, getattr(ground, "aperture_m", None))


def simulate(spec: NetworkSpec) -> NetworkMetrics:
    """Rates, fidelities and key rate for the spec's source-destination path."""
    path = find_path(spec) or []
    hops = [(path[i], path[i + 1]) for i in range(len(path) - 1)]
    links = [_link_between(spec, a, b) for a, b in hops]
    losses = [link_loss(spec, link) for link in links]

    # split into segments at repeaters (memory nodes)
    cuts = [0] + [i for i, n in enumerate(path) if 0 < i < len(path) - 1 and spec.node(n).type == "repeater"] \
        + [len(path) - 1]
    segments: list[SegmentMetrics] = []
    seg_of_link: list[int] = []
    for s in range(len(cuts) - 1):
        a, b = cuts[s], cuts[s + 1]
        nodes = path[a:b + 1]
        idx = list(range(a, b))
        seg_of_link += [s] * len(idx)
        seg_links = [links[i] for i in idx]
        seg_loss = sum(losses[i].total_db for i in idx)
        free = all(link.medium == "free_space" for link in seg_links)
        det = ph.FREE_SPACE_DETECTOR_EFF if free else ph.FIBER_DETECTOR_EFF
        dark = ph.FREE_SPACE_DARK_PER_GATE if free else ph.FIBER_DARK_PER_GATE
        sat_pos = next((k for k, n in enumerate(nodes) if spec.node(n).type == "satellite"), None)
        if sat_pos is not None:  # satellite source: the two halves are real links
            eta_a = 10 ** (-sum(losses[a + k].total_db for k in range(sat_pos)) / 10)
            eta_b = 10 ** (-sum(losses[a + k].total_db for k in range(sat_pos, len(idx))) / 10)
        else:  # midpoint source
            eta_a = eta_b = 10 ** (-seg_loss / 20)
        p_true = ph.PAIR_PROB * eta_a * eta_b * det * det
        p_acc = 2 * dark * ph.PAIR_PROB * det * (eta_a + eta_b) + (2 * dark) ** 2
        visibility = p_true / (p_true + p_acc) if p_true + p_acc > 0 else 0.0
        w_fresh = ph.werner_from_fidelity(ph.SOURCE_FIDELITY) * visibility

        memory_ends = [spec.node(n) for n in (nodes[0], nodes[-1]) if spec.node(n).type == "repeater"]
        t2 = min((m.memory_t2_ms or ph.DEFAULT_T2_MS) for m in memory_ends) if memory_ends else None
        length = sum(link.length_km for link in seg_links)
        if t2 is None:
            attempt = ph.SOURCE_RATE_HZ
        else:  # must hear back before re-trying a memory: L / c per heralding round
            speed = ph.FREE_SPACE_SPEED_KM_S if free else ph.FIBER_SPEED_KM_S
            attempt = min(ph.SOURCE_RATE_HZ, ph.MULTIPLEX_MODES * speed / max(length, 1e-6))
        f_fresh, seg_rate = ph.fidelity_from_werner(w_fresh), attempt * p_true
        for _ in range(spec.purification_rounds):  # each round spends two pairs to make one better one
            if f_fresh <= 0.5:
                break
            f_fresh, p_ok = ph.bbpssw(f_fresh)
            seg_rate *= p_ok / 2
        segments.append(SegmentMetrics(
            nodes=nodes, length_km=length, loss_db=seg_loss, attempt_rate_hz=attempt, success_prob=p_true,
            pair_rate_hz=seg_rate, fidelity_fresh=f_fresh,
            fidelity_stored=f_fresh, memory_t2_ms=t2, wait_s=0.0,
        ))

    n = len(segments)
    swaps = n - 1
    slowest = min((s.pair_rate_hz for s in segments), default=0.0)
    if n == 1:
        rate = segments[0].pair_rate_hz if segments else 0.0
    elif slowest <= 0:
        rate = 0.0
    else:
        harmonic = sum(1 / k for k in range(1, n + 1))
        t_all = harmonic / slowest  # expected time until every segment holds a pair
        rate = ph.BSM_SUCCESS ** swaps / t_all
        for s in segments:
            s.wait_s = max(0.0, t_all - 1 / s.pair_rate_hz) if s.pair_rate_hz > 0 else t_all
            if s.memory_t2_ms:
                w = ph.werner_from_fidelity(s.fidelity_fresh) * math.exp(-s.wait_s / (s.memory_t2_ms / 1e3))
                s.fidelity_stored = ph.fidelity_from_werner(w)
    w_total = math.prod(ph.werner_from_fidelity(s.fidelity_stored) for s in segments) * ph.SWAP_FIDELITY ** swaps
    fidelity = ph.fidelity_from_werner(w_total)
    qber = (1 - w_total) / 2
    key = 0.5 * rate * ph.bbm92_key_fraction(qber)

    link_rows = []
    for i, (link, loss) in enumerate(zip(links, losses)):
        seg = segments[seg_of_link[i]]
        free = link.medium == "free_space"
        det = ph.FREE_SPACE_DETECTOR_EFF if free else ph.FIBER_DETECTOR_EFF
        link_rows.append(LinkMetrics(
            from_=hops[i][0], to=hops[i][1], medium=link.medium, length_km=link.length_km,
            loss_db=loss.total_db, loss_parts=loss.parts, transmissivity=loss.transmissivity,
            success_prob=loss.transmissivity * det, pair_rate_hz=seg.pair_rate_hz, fidelity=seg.fidelity_stored,
        ).model_dump_public())

    weakest = None
    if link_rows:
        w = max(link_rows, key=lambda r: r["loss_db"])
        weakest = {"from": w["from"], "to": w["to"],
                   "reason": f"{w['length_km']:,.0f} km of {w['medium'].replace('_', ' ')} loses "
                             f"{w['loss_db']:.1f} dB: only {w['transmissivity']:.1e} of photons get through"}
    return NetworkMetrics(path=path, links=link_rows, segments=segments,
                          end_to_end=EndToEnd(pair_rate_hz=rate, fidelity=fidelity, qber=qber, key_rate_bps=key,
                                              swaps=swaps, segments=n),
                          weakest_link=weakest)
