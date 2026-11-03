"""Offline explanations: informative templates filled with the real results."""

from __future__ import annotations

import math
from typing import Any

from inkubit.sim.noise import get_preset
from inkubit.spec.models import CircuitSpec, Operation
from inkubit.verify.verdict import describe


def _angle(theta: float) -> str:
    deg = math.degrees(theta)
    return f"{deg:.0f}°"


def _op_phrase(op: Operation) -> str:
    phrase = _gate_phrase(op)
    if op.conditional is not None:
        when = " and ".join(f"c{c} reads {v}" for c, v in op.conditional.pairs())
        phrase = f"only if {when}, {phrase}"
    return phrase


def _gate_phrase(op: Operation) -> str:
    qs = ", ".join(f"q{q}" for q in op.targets)
    g = op.gate
    if g == "RESET":
        return f"a reset puts {qs} back to 0 so it can be used again"
    if g == "H":
        return f"a Hadamard gate puts {qs} into an equal mix of 0 and 1"
    if g == "X":
        return f"an X gate flips {qs} from 0 to 1"
    if g == "Y":
        return f"a Y gate flips {qs} and adds a phase"
    if g == "Z":
        return f"a Z gate flips the phase of {qs}, which a measurement alone cannot see"
    if g in ("S", "T"):
        return f"an {g} gate adds a {'quarter' if g == 'S' else 'eighth'}-turn phase to {qs}"
    if g in ("SDG", "TDG"):
        return f"an {g[0]}-dagger gate takes a {'quarter' if g == 'SDG' else 'eighth'}-turn phase back off {qs}"
    if g == "SX":
        return f"a square-root-of-X gate does half a bit flip on {qs}"
    if g in ("RX", "RY", "RZ"):
        return f"an {g} rotation turns {qs} by {_angle(op.params[0])}"
    if g == "CX":
        return (f"a CNOT flips q{op.targets[0]} whenever q{op.controls[0]} is 1, "
                f"which ties their results together (entanglement)")
    if g == "CZ":
        return f"a CZ adds a phase when both q{op.controls[0]} and q{op.targets[0]} are 1"
    if g == "CP":
        return (f"a controlled-phase adds a {_angle(op.params[0])} phase when both q{op.controls[0]} "
                f"and q{op.targets[0]} are 1")
    if g == "CCX":
        return (f"a Toffoli flips q{op.targets[0]} only when both q{op.controls[0]} and q{op.controls[1]} are 1, "
                f"the quantum version of an AND gate")
    if g == "SWAP":
        return f"a SWAP exchanges q{op.targets[0]} and q{op.targets[1]}"
    return ""


def _join(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if not parts:
        return "nothing happens before the measurement"
    if len(parts) == 1:
        return parts[0]
    return ", then ".join(parts[:-1]) + ", and finally " + parts[-1]


def _always_agree(dist: dict[str, float], nc: int, pairs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out = []
    cl = sorted(c for _, c in pairs)
    for i, a in enumerate(cl):
        for b in cl[i + 1:]:
            ia, ib = nc - 1 - a, nc - 1 - b
            corr = sum(p * (1 if k[ia] == k[ib] else -1) for k, p in dist.items())
            marg = sum(p for k, p in dist.items() if k[ia] == "1")
            if corr > 0.99 and 0.05 < marg < 0.95:
                out.append((a, b))
    return out


def explain_circuit(spec: CircuitSpec, result: dict[str, Any]) -> str:
    """Three short paragraphs about the design, the histogram and the noise."""
    verdict = result.get("verdict") or {}
    noise = verdict.get("noise") or result.get("noise", "ideal")
    preset = get_preset(noise)
    ideal: dict[str, float] = verdict.get("ideal", {})
    measured: dict[str, float] = verdict.get("measured", {})
    metrics = verdict.get("metrics", {})
    title = spec.metadata.title or "This circuit"

    steps = [_op_phrase(op) for op in spec.operations if op.gate not in ("MEASURE", "BARRIER")]
    p1 = f"{title} uses {spec.num_qubits} qubit{'s' if spec.num_qubits != 1 else ''}. All start at 0; " \
         f"{_join(steps)}. Then every qubit is measured."

    agree = _always_agree(ideal, spec.num_clbits, spec.measured_pairs())
    p2 = f"A perfect machine would give {describe(ideal) if ideal else 'no data'}."
    if agree:
        pairs = ", ".join(f"c{a} and c{b}" for a, b in agree[:3])
        p2 += (f" Each result on its own is a coin flip, yet {pairs} always agree. Neither qubit had a value "
               "before the measurement; the agreement comes from entanglement, not from a hidden answer.")
    elif len(ideal) > 1:
        p2 += " The spread is the superposition showing up: each shot picks one outcome at random with these odds."

    if preset.is_ideal or not measured:
        p3 = "This run used an ideal simulator, so the counts differ from the perfect odds only by random sampling."
    else:
        stray = sum(v for k, v in measured.items() if ideal.get(k, 0) < 1e-9)
        fid = metrics.get("fidelity_vs_ideal")
        p3 = (f"With {preset.label.lower()} noise the run measured {describe(measured)}. "
              f"About {stray * 100:.1f}% of shots landed on outcomes the perfect circuit never produces: two-qubit "
              f"gates fail {preset.p2 * 100:.1f}% of the time and each readout misreads "
              f"{preset.readout_p01 * 100:.0f}-{preset.readout_p10 * 100:.0f}% of bits.")
        if fid is not None:
            p3 += f" Similarity to the perfect result (Hellinger fidelity) is {fid:.3f}."
    if verdict:
        if result.get("verified"):
            p3 += (f" The verifier predicted the exact noisy odds from the spec and the run matched within "
                   f"{metrics.get('tvd', 0):.3f} (limit {metrics.get('tvd_threshold', 0):.3f}).")
        else:
            p3 += " The run did not match the spec, so treat these numbers as unverified."
    fault = result.get("fault")
    if fault and result.get("verified"):
        p3 += (f" The first attempt had a planted bug ({fault['label']}); the agent caught it only "
               "because the counts disagreed with the spec, then fixed the code.")
    return "\n\n".join([p1, p2, p3])
