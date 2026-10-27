"""P9: analytic network model, bottleneck search and its physics sanity."""

from __future__ import annotations

import pytest

from qcanvas.agent.events import EventBus
from qcanvas.network import physics as ph
from qcanvas.network.agent import run_network_agent, sanity_checks
from qcanvas.network.model import simulate
from qcanvas.spec import parse_spec


def chain(lengths: list[float], t2_ms: float = 1000.0, medium: str = "fiber") -> dict:
    """A straight chain A - r1 - ... - B with the given span lengths."""
    ids = ["a"] + [f"r{i}" for i in range(1, len(lengths))] + ["b"]
    nodes = [{"id": i, "type": "ground_station" if i in ("a", "b") else "repeater",
              **({"memory_t2_ms": t2_ms} if i not in ("a", "b") else {})} for i in ids]
    links = [{"from": ids[k], "to": ids[k + 1], "medium": medium, "length_km": L} for k, L in enumerate(lengths)]
    return {"kind": "network", "nodes": nodes, "links": links, "source": "a", "destination": "b"}


def test_fiber_loss_is_02_db_per_km():
    assert ph.fiber_loss(100).total_db == pytest.approx(20.0)


def test_binary_entropy_and_key_fraction():
    assert ph.binary_entropy(0.5) == pytest.approx(1.0)
    assert ph.bbm92_key_fraction(0.0) == pytest.approx(1.0)
    assert ph.bbm92_key_fraction(0.12) == 0.0  # past the ~11% threshold the key is clamped to zero


def test_satellite_preset_is_micius_like(example):
    m = simulate(parse_spec(example("network_satellite")))
    total_db = sum(link["loss_db"] for link in m.links)
    assert 60 < total_db < 82  # Micius dual downlink: ~64-82 dB
    assert 0.3 < m.end_to_end.pair_rate_hz < 3  # Micius: ~1 pair/s over 1,200 km
    assert m.end_to_end.swaps == 0 and m.end_to_end.segments == 1


@pytest.mark.parametrize("medium", ["fiber", "free_space"])
def test_longer_link_means_lower_rate(medium):
    rates = [simulate(parse_spec(chain([L], medium=medium))).end_to_end.pair_rate_hz for L in (20, 60, 120)]
    assert rates[0] > rates[1] > rates[2]


def test_longer_link_means_lower_fidelity():
    f = [simulate(parse_spec(chain([L]))).end_to_end.fidelity for L in (50, 250, 400)]
    assert f[0] >= f[1] > f[2]


def test_repeaters_help_a_long_fiber_chain():
    direct = simulate(parse_spec(chain([600]))).end_to_end
    repeated = simulate(parse_spec(chain([100] * 6, t2_ms=1000))).end_to_end
    assert repeated.pair_rate_hz > 1000 * direct.pair_rate_hz
    assert repeated.fidelity > direct.fidelity and direct.key_rate_bps == 0
    # five swaps of 98%-fidelity pairs pile up ~12% errors: past the BBM92 limit without purification
    assert repeated.qber > 0.11 and repeated.key_rate_bps == 0


def test_short_memories_spoil_the_pairs():
    good = simulate(parse_spec(chain([100, 100], t2_ms=1000))).end_to_end
    bad = simulate(parse_spec(chain([100, 100], t2_ms=1))).end_to_end
    assert bad.fidelity < good.fidelity


def test_weakest_link_is_the_longest_span(example):
    m = simulate(parse_spec(example("network_fiber_chain")))
    assert (m.weakest_link["from"], m.weakest_link["to"]) == ("r1", "r2")


def test_agent_fixes_the_fiber_chain(example):
    bus = EventBus()
    result = run_network_agent(parse_spec(example("network_fiber_chain")), bus)
    assert result.before.end_to_end.key_rate_bps == 0
    assert result.after is not None and result.after.end_to_end.key_rate_bps > 0
    kinds = [f.kind for f in result.fixes]
    assert kinds[0] == "midpoint_relay" and "better_memory" in kinds
    spec_after = parse_spec(result.spec_after)  # the improved design is itself a valid spec
    assert len(spec_after.nodes) == 5
    assert all(c.passed for c in result.checks)
    steps = [e.step for e in bus.events()]
    assert "bottleneck" in steps and "fix" in steps and steps[-1] == "done"


def test_agent_improves_the_satellite_link(example):
    result = run_network_agent(parse_spec(example("network_satellite")))
    assert result.after.end_to_end.key_rate_bps > result.before.end_to_end.key_rate_bps
    apertures = [n.aperture_m for n in parse_spec(result.spec_after).nodes if n.aperture_m]
    assert apertures and max(apertures) <= 1.8


def test_sanity_checks_pass_on_presets(example):
    for name in ("network_satellite", "network_fiber_chain"):
        spec = parse_spec(example(name))
        assert all(c.passed for c in sanity_checks(spec, simulate(spec)))


def test_loss_override_is_respected():
    data = chain([100])
    data["links"][0]["loss_db"] = 3.0
    m = simulate(parse_spec(data))
    assert m.links[0]["loss_db"] == pytest.approx(3.0)
