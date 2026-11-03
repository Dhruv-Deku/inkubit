"""Network agent: model -> find bottleneck -> try fixes -> re-simulate -> keep the best."""

from __future__ import annotations

import time

from pydantic import BaseModel, Field

from inkubit.agent.events import EventBus
from inkubit.network.model import NetworkMetrics, simulate
from inkubit.network.optimize import candidates, improves
from inkubit.spec.models import NetworkSpec

MAX_ROUNDS = 3


class FixOut(BaseModel):
    """A fix as shown in the UI."""

    kind: str
    description: str
    round: int
    applied: bool
    pair_rate_hz: float
    fidelity: float
    key_rate_bps: float
    score: float = 0.0


class Check(BaseModel):
    name: str
    passed: bool
    detail: str


class NetworkResult(BaseModel):
    """Before/after of the bottleneck search."""

    status: str
    summary: str
    path: list[str]
    before: NetworkMetrics
    after: NetworkMetrics | None
    fix: FixOut | None
    fixes: list[FixOut] = Field(default_factory=list)
    candidates: list[FixOut] = Field(default_factory=list)
    spec_after: dict | None = None
    checks: list[Check] = Field(default_factory=list)


def _rate(hz: float, unit: str = "pairs/s") -> str:
    if hz <= 0:
        return f"0 {unit}"
    if hz < 1e-3:
        return f"{hz:.1e} {unit}"
    if hz < 1:
        return f"{hz:.2g} {unit}"
    for f, p in ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1, "")):
        if hz >= f:
            return f"{hz / f:.3g} {p}{unit}"
    return f"{hz:.3g} {unit}"


def describe(m: NetworkMetrics) -> str:
    e = m.end_to_end
    return (f"{_rate(e.pair_rate_hz)}, fidelity {e.fidelity:.3f}, error rate {e.qber * 100:.1f}%, "
            f"secret key {_rate(e.key_rate_bps, 'bit/s')}")


def bottleneck(m: NetworkMetrics) -> str:
    """Plain-language reason the network is limited."""
    for s in m.segments:
        if s.memory_t2_ms and s.wait_s > 0.3 * s.memory_t2_ms / 1e3:
            return (f"pairs wait {s.wait_s * 1e3:,.0f} ms in memory but the memories stay coherent for only "
                    f"{s.memory_t2_ms:g} ms, so they decay before the swap (slowest span: {m.weakest_link['from']} "
                    f"→ {m.weakest_link['to']})")
    w = m.weakest_link
    return f"{w['from']} → {w['to']} is the weakest link: {w['reason']}" if w else "no path"


def sanity_checks(spec: NetworkSpec, m: NetworkMetrics) -> list[Check]:
    """Physics checks the model must satisfy (the network analogue of verification)."""
    e = m.end_to_end
    checks = [
        Check(name="Fidelity is physical", passed=0.25 - 1e-9 <= e.fidelity <= 1 + 1e-9,
              detail=f"{e.fidelity:.3f} lies in [0.25, 1]"),
        Check(name="Key never exceeds sifted pairs", passed=0 <= e.key_rate_bps <= e.pair_rate_hz / 2 + 1e-12,
              detail=f"{_rate(e.key_rate_bps, 'bit/s')} ≤ half of {_rate(e.pair_rate_hz)}"),
        Check(name="No key above the BBM92 error threshold", passed=not (e.qber > 0.11 and e.key_rate_bps > 0),
              detail=f"error rate {e.qber * 100:.1f}% ({'below' if e.qber <= 0.11 else 'above'} 11%)"),
    ]
    if m.weakest_link:
        data = spec.model_dump(by_alias=True, exclude_none=True)
        for link in data["links"]:
            if {link["from"], link["to"]} == {m.weakest_link["from"], m.weakest_link["to"]}:
                link["length_km"] *= 1.1
                link.pop("loss_db", None)
        longer = simulate(NetworkSpec.model_validate(data))
        checks.append(Check(name="A longer weakest link lowers the rate",
                            passed=longer.end_to_end.pair_rate_hz <= e.pair_rate_hz + 1e-15,
                            detail=f"+10% length: {_rate(e.pair_rate_hz)} → {_rate(longer.end_to_end.pair_rate_hz)}"))
    return checks


def _out(c, rnd: int, applied: bool) -> FixOut:
    e = c.metrics.end_to_end
    return FixOut(kind=c.kind, description=c.description, round=rnd, applied=applied, pair_rate_hz=e.pair_rate_hz,
                  fidelity=e.fidelity, key_rate_bps=e.key_rate_bps, score=c.score[0] or c.score[1])


def run_network_agent(spec: NetworkSpec, bus: EventBus | None = None, pace_s: float = 0.0) -> NetworkResult:
    """Model the network, then greedily fix bottlenecks for up to three rounds."""
    bus = bus or EventBus()

    def pause() -> None:
        if pace_s:
            time.sleep(pace_s)

    title = spec.metadata.title or "the network"
    bus.emit("plan", "info", f"Plan: model every link of '{title}' from physics, find the bottleneck, try the "
                             f"fixes that apply, re-simulate each, and keep the best. Up to {MAX_ROUNDS} rounds.")
    before = simulate(spec)
    for row in before.links:
        parts = ", ".join(f"{k} {v:.1f} dB" for k, v in row["loss_parts"].items())
        bus.emit("network", "info", f"Link {row['from']} → {row['to']}: {row['medium'].replace('_', ' ')}, "
                                    f"{row['length_km']:,.0f} km, {row['loss_db']:.1f} dB loss ({parts}).",
                 link=row)
    pause()
    bus.emit("network", "ok", f"End to end ({' → '.join(before.path)}): {describe(before)}.",
             metrics=before.end_to_end.model_dump())

    current_spec, current = spec, before
    applied: list[FixOut] = []
    tried: list[FixOut] = []
    for rnd in range(1, MAX_ROUNDS + 1):
        pause()
        bus.emit("bottleneck", "warn", f"Round {rnd} bottleneck: {bottleneck(current)}.")
        options = candidates(current_spec, current)
        if not options:
            bus.emit("fix", "info", "No fix applies to this bottleneck.")
            break
        for c in options:
            better = improves(c.metrics, current)
            bus.emit("fix", "info", f"Tried: {c.description} → {describe(c.metrics)}"
                                    + ("" if better else " (no gain)"), round=rnd)
        best = max(options, key=lambda c: c.score)
        gain = improves(best.metrics, current)
        for c in options:
            tried.append(_out(c, rnd, c is best and gain))
        if not gain:
            bus.emit("fix", "info", "None of these improves the network any further; stopping.")
            break
        pause()
        applied.append(_out(best, rnd, True))
        bus.emit("fix", "ok", f"Applied: {best.description}. Key rate {_rate(current.end_to_end.key_rate_bps, 'bit/s')}"
                              f" → {_rate(best.metrics.end_to_end.key_rate_bps, 'bit/s')}, fidelity "
                              f"{current.end_to_end.fidelity:.3f} → {best.metrics.end_to_end.fidelity:.3f}.",
                 round=rnd)
        current_spec, current = best.spec, best.metrics

    after = current if applied else None
    checks = sanity_checks(current_spec, current)
    for c in checks:
        bus.emit("check", "ok" if c.passed else "fail", f"{c.name}: {c.detail}.")
    if applied:
        b, a = before.end_to_end, current.end_to_end
        summary = (f"{len(applied)} fix{'es' if len(applied) > 1 else ''} applied. Secret key "
                   f"{_rate(b.key_rate_bps, 'bit/s')} → {_rate(a.key_rate_bps, 'bit/s')}; entangled pairs "
                   f"{_rate(b.pair_rate_hz)} → {_rate(a.pair_rate_hz)}; fidelity {b.fidelity:.3f} → {a.fidelity:.3f}.")
    else:
        summary = f"No fix improved the design. As drawn: {describe(before)}."
    ok = all(c.passed for c in checks)
    bus.emit("done", "ok" if ok else "fail", summary if ok else summary + " A sanity check failed; see above.")
    combined = None
    if applied:
        last = applied[-1]
        combined = last.model_copy(update={"description": " + ".join(f.description for f in applied)})
    return NetworkResult(
        status="improved" if applied else "unchanged", summary=summary, path=before.path, before=before,
        after=after, fix=combined, fixes=applied, candidates=tried,
        spec_after=current_spec.model_dump(by_alias=True, exclude_none=True) if applied else None, checks=checks,
    )
