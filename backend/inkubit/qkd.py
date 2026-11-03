"""Catch the spy: BB84 quantum key distribution with an eavesdropper.

Alice sends single photons, each a random bit in a random basis (+ is Z, x is X). Bob measures each in a random
basis. Eve intercepts a chosen share of the photons, measures in her own random basis and resends what she saw.
The quantum rule that makes this work: measuring in the wrong basis gives a coin flip and destroys the original
state. Afterwards Alice and Bob compare bases in public and keep the bits where they matched (the sifted key),
reveal a random part of it to estimate the error rate (QBER), and abort above 11%, the bound for one-way BB84
(Shor-Preskill). An intercept-resend spy on a share f of photons causes QBER = f/4 on top of the channel's own
errors, so a curious Eve is caught; what survives is shrunk by privacy amplification to the secret length
n (1 - 2 h(QBER)).

Each photon's outcome follows the measurement rule exactly (same basis: the bit; other basis: 50/50), sampled with a
fixed seed; the tests check the per-photon rule against a Qiskit simulation of the circuit.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from pydantic import BaseModel

ABORT = 0.11
SHOWN = 20


def h2(p: float) -> float:
    return 0.0 if p <= 0 or p >= 1 else -p * math.log2(p) - (1 - p) * math.log2(1 - p)


class Photon(BaseModel):
    bit: int
    basis: str  # "+" or "x"
    eve: str | None  # Eve's basis, or None if she let it pass
    eve_bit: int | None
    bob_basis: str
    bob_bit: int
    kept: bool  # bases matched
    error: bool  # kept, and Bob's bit differs from Alice's


class QkdLab(BaseModel):
    photons: int
    eve: float
    noise: float
    seed: int
    shown: list[Photon]
    sifted: int
    checked: int  # sifted bits revealed to estimate the error rate
    errors_seen: int
    qber: float  # estimated from the revealed bits
    qber_err: float
    expected_qber: float  # noise + eve/4
    caught: bool
    key_bits: int  # after privacy amplification (0 if aborted)
    eve_knows: float  # share of the kept key bits Eve guessed right
    curve: list[tuple[float, float]]  # eve share -> expected QBER, for the chart
    spec: dict[str, Any]
    summary: str


def photon_spec(bit: int, basis: str, bob: str, eve: str | None = None) -> dict[str, Any]:
    """One photon as a circuit: Alice's preparation, Eve's measurement (as a CX onto her qubit), Bob's basis."""
    ops: list[dict[str, Any]] = []
    if bit:
        ops.append({"gate": "X", "targets": [0]})
    if basis == "x":
        ops.append({"gate": "H", "targets": [0]})
    n = 1
    if eve is not None:
        n = 2
        if eve == "x":
            ops.append({"gate": "H", "targets": [0]})
        ops.append({"gate": "CX", "controls": [0], "targets": [1]})  # Eve copies what she measures into q1
        if eve == "x":
            ops.append({"gate": "H", "targets": [0]})
    if bob == "x":
        ops.append({"gate": "H", "targets": [0]})
    return {"kind": "circuit", "version": "1.0", "num_qubits": n, "num_clbits": n, "operations": ops,
            "measurements": [{"qubit": q, "clbit": q} for q in range(n)],
            "metadata": {"title": f"BB84 photon: Alice {bit}{basis}, {'Eve ' + eve + ', ' if eve else ''}Bob {bob}",
                         "origin": "manual",
                         "notes": ("q0 is the photon; Alice sets the bit with X and the basis with H, Bob's H picks his "
                                   "basis. " + ("Eve's measurement is a CX into q1 (her record), in her basis. "
                                                if eve else "") + "Clbit 0 is Bob's reading.")}}


def bb84(photons: int = 1000, eve: float = 0.0, noise: float = 0.01, seed: int = 7) -> QkdLab:
    if not 16 <= photons <= 100_000:
        raise ValueError("send between 16 and 100,000 photons")
    if not (0 <= eve <= 1 and 0 <= noise <= 0.2):
        raise ValueError("eve is a share from 0 to 1 and noise at most 0.2")
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, photons)
    a_basis = rng.integers(0, 2, photons)  # 0 = +, 1 = x
    b_basis = rng.integers(0, 2, photons)
    tapped = rng.random(photons) < eve
    e_basis = rng.integers(0, 2, photons)
    # what travels on after Eve: her reading, in her basis, or Alice's photon untouched
    e_bit = np.where(e_basis == a_basis, bits, rng.integers(0, 2, photons))
    sent_bit = np.where(tapped, e_bit, bits)
    sent_basis = np.where(tapped, e_basis, a_basis)
    b_bit = np.where(b_basis == sent_basis, sent_bit, rng.integers(0, 2, photons))
    b_bit = np.where(rng.random(photons) < noise, 1 - b_bit, b_bit)  # the channel and detectors flip some
    kept = a_basis == b_basis
    err = kept & (b_bit != bits)
    sifted = int(kept.sum())
    idx = np.flatnonzero(kept)
    reveal = rng.random(len(idx)) < 0.5
    checked = int(reveal.sum())
    seen = int(err[idx[reveal]].sum())
    qber = seen / checked if checked else 0.0
    qerr = math.sqrt(max(qber * (1 - qber), 1e-9) / max(checked, 1))
    caught = qber > ABORT
    remaining = sifted - checked
    key = 0 if caught else max(0, int(remaining * (1 - 2 * h2(qber))))
    secret_idx = idx[~reveal]
    eve_right = tapped[secret_idx] & (e_bit[secret_idx] == bits[secret_idx]) if len(secret_idx) else np.array([])
    eve_knows = float(eve_right.mean()) if len(secret_idx) else 0.0
    B = "+x"
    shown = [Photon(bit=int(bits[i]), basis=B[a_basis[i]], eve=B[e_basis[i]] if tapped[i] else None,
                    eve_bit=int(e_bit[i]) if tapped[i] else None, bob_basis=B[b_basis[i]], bob_bit=int(b_bit[i]),
                    kept=bool(kept[i]), error=bool(err[i])) for i in range(min(SHOWN, photons))]
    exp_q = noise + eve / 4 - noise * eve / 2  # a flip on top of Eve's error can undo it
    first = shown[0]
    lab = QkdLab(photons=photons, eve=eve, noise=noise, seed=seed, shown=shown, sifted=sifted, checked=checked,
                 errors_seen=seen, qber=qber, qber_err=qerr, expected_qber=exp_q, caught=caught, key_bits=key,
                 eve_knows=eve_knows,
                 curve=[(f, noise + f / 4 - noise * f / 2) for f in np.round(np.linspace(0, 1, 21), 3).tolist()],
                 spec=photon_spec(first.bit, first.basis, first.bob_basis, first.eve), summary="")
    lab.summary = _summary(lab)
    return lab


def _summary(lab: QkdLab) -> str:
    pct = lambda p: f"{p * 100:.1f}%"  # noqa: E731
    text = (f"Of {lab.photons:,} photons, {lab.sifted:,} had matching bases ({pct(lab.sifted / lab.photons)}; about "
            f"half, as expected). Alice and Bob revealed {lab.checked:,} of those and found {lab.errors_seen} errors: "
            f"QBER {pct(lab.qber)} ± {pct(lab.qber_err)}. ")
    if lab.caught:
        text += (f"That is above {pct(ABORT)}, so they abort: someone is listening. Eve's {pct(lab.eve)} share "
                 "of measurements disturbed the photons she guessed the wrong basis for, and that disturbance is what "
                 "gave her away. No key is used.")
    elif lab.eve > 0:
        text += (f"Below {pct(ABORT)}, so they keep {lab.key_bits:,} secret bits after privacy amplification, which "
                 f"removes what Eve could know: she listened to {pct(lab.eve)} of photons and guessed "
                 f"{pct(lab.eve_knows)} of the kept bits, information the shrinking erases.")
    else:
        text += (f"Below {pct(ABORT)}, so they keep {lab.key_bits:,} secret bits after error correction and privacy "
                 "amplification. Slide Eve up and watch the error rate give her away.")
    return text
