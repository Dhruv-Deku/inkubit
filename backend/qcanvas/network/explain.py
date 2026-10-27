"""Offline explanation of a network result, filled with the real numbers."""

from __future__ import annotations

from typing import Any

from qcanvas.spec.models import NetworkSpec


def _rate(x: float, unit: str) -> str:
    if x <= 0:
        return f"0 {unit}"
    return f"{x:.2g} {unit}" if x < 1 else f"{x:,.3g} {unit}"


def explain_network(spec: NetworkSpec, result: dict[str, Any]) -> str:
    """Three short paragraphs: how pairs travel, why the numbers, what the agent changed."""
    before = result.get("before") or {}
    after = result.get("after")
    e = before.get("end_to_end", {})
    path = " → ".join(before.get("path", []))
    sats = [n for n in spec.nodes if n.type == "satellite" and n.id in before.get("path", [])]
    swaps = e.get("swaps", 0)
    how = []
    if sats:
        how.append(f"the satellite creates each entangled photon pair and sends one photon down to each ground station")
    if swaps:
        how.append(f"{swaps} repeater{'s' if swaps > 1 else ''} store photons in quantum memory and join neighbouring "
                   "pairs by entanglement swapping")
    p1 = (f"Entangled pairs are shared between {spec.source} and {spec.destination} along {path}. "
          + ("; ".join(how).capitalize() + "." if how else "Photons travel the whole way through one channel."))

    weak = before.get("weakest_link") or {}
    key = e.get("key_rate_bps", 0)
    p2 = (f"Every kilometre loses photons. The worst link is {weak.get('from')} → {weak.get('to')}: "
          f"{weak.get('reason', 'it loses the most light')}. As drawn the network delivers "
          f"{_rate(e.get('pair_rate_hz', 0), 'pairs per second')} with fidelity {e.get('fidelity', 0):.3f}, "
          f"an error rate of {e.get('qber', 0) * 100:.1f}%. ")
    if key > 0:
        p2 += f"That is enough for a secret key at {_rate(key, 'bits per second')} using BBM92."
    else:
        p2 += ("No secret key survives: above about 11% errors, error correction and privacy amplification "
               "use up every bit.")

    fixes = result.get("fixes") or []
    if after and fixes:
        a = after["end_to_end"]
        steps = "; then ".join(f["description"] for f in fixes)
        p3 = (f"The agent re-simulated {len(result.get('candidates', []))} candidate fixes and kept the best each round: "
              f"{steps}. Result: {_rate(a['pair_rate_hz'], 'pairs per second')}, fidelity {a['fidelity']:.3f}, "
              f"error rate {a['qber'] * 100:.1f}%, secret key {_rate(a['key_rate_bps'], 'bits per second')}.")
    else:
        p3 = "None of the fixes the agent tried made the design better, so it is kept as drawn."
    checks = result.get("checks") or []
    if checks:
        ok = sum(1 for c in checks if c.get("passed"))
        p3 += f" {ok} of {len(checks)} physics sanity checks passed."
    return "\n\n".join([p1, p2, p3])
