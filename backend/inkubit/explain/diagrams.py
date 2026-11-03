"""Offline diagrams: Qiskit's circuit drawer and a matplotlib network drawing."""

from __future__ import annotations

import io
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from qiskit import ClassicalRegister  # noqa: E402

from inkubit.spec.models import CircuitSpec, NetworkSpec  # noqa: E402
from inkubit.verify.expected import build_reference_circuit  # noqa: E402

BG = "#16171b"
INK = "#e8e6e1"
MUTED = "#8b8d94"
ACCENT = "#d9a441"  # gold: reserved for entanglement / the end-to-end pair
WARN = "#e0715a"


def circuit_png(spec: CircuitSpec) -> bytes:
    """Clean circuit drawing (Qiskit matplotlib drawer, dark style) as PNG bytes."""
    qc = build_reference_circuit(spec)
    qc.add_register(ClassicalRegister(spec.num_clbits, "c"))
    for op in spec.operations:
        if op.gate == "BARRIER":
            qc.barrier(*op.targets)
    qc.barrier()
    for q, c in spec.measured_pairs():
        qc.measure(q, c)
    fig = qc.draw(output="mpl", style="iqp-dark", fold=-1)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


def network_png(spec: NetworkSpec, metrics: dict[str, Any] | None = None) -> bytes:
    """Network drawing: nodes, links labelled with km and loss, weakest link highlighted."""
    metrics = metrics or {}
    link_stats = {(m["from"], m["to"]): m for m in metrics.get("links", [])}
    weakest = metrics.get("weakest_link")
    pos = {}
    for i, n in enumerate(spec.nodes):
        pos[n.id] = (n.position.x, -n.position.y) if n.position else (i * 200.0, 0.0)
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=150)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    for link in spec.links:
        (x1, y1), (x2, y2) = pos[link.from_node], pos[link.to_node]
        key = (link.from_node, link.to_node)
        is_weak = weakest is not None and (weakest.get("from"), weakest.get("to")) == key
        color = WARN if is_weak else MUTED
        ax.plot([x1, x2], [y1, y2], color=color, lw=3 if is_weak else 2,
                ls="--" if link.medium == "free_space" else "-", zorder=1)
        stats = link_stats.get(key, {})
        label = f"{link.length_km:g} km"
        if "loss_db" in stats:
            label += f"\n{stats['loss_db']:.1f} dB"
        ax.text((x1 + x2) / 2, (y1 + y2) / 2, label, color=color, fontsize=9, ha="center", va="center",
                bbox={"boxstyle": "round,pad=0.3", "fc": BG, "ec": "none"}, zorder=3)
    marker = {"ground_station": "s", "satellite": "D", "repeater": "o"}
    for n in spec.nodes:
        x, y = pos[n.id]
        end = n.id in (spec.source, spec.destination)
        ax.scatter([x], [y], s=380, marker=marker[n.type], color=ACCENT if end else INK, zorder=4,
                   edgecolors=BG, linewidths=2)
        above = n.type == "satellite"
        ax.text(x, y + 38 if above else y - 38, n.label or n.id, color=INK, fontsize=10, ha="center",
                va="bottom" if above else "top", zorder=5)
    ax.set_aspect("equal", adjustable="datalim")
    ax.margins(0.15)
    ax.axis("off")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return buf.getvalue()
