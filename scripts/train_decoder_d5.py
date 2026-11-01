"""Distance 5: matching at distance 3 and 5 (error suppression, Lambda) and a neural decoder on top of matching.

    .venv/Scripts/python scripts/train_decoder_d5.py [million_training_shots]

Memory experiments of d rounds (3 at d = 3, 5 at d = 5) under the same phenomenological noise as the distance-3
study (backend/qcanvas/decoder.py). Matching is PyMatching on the same space-time graph and weights, checked equal to
the exact matcher at d = 3 (tests). Per-round logical error e from 1 - 2P = (1 - 2e)^rounds; below threshold a
bigger code suppresses errors by Lambda = e3 / e5 (Google's Willow chip measured 2.14 from distance 5 to 7, 2024).

Neural at d = 5: a 172-256-256-1 network on top of matching. It sees every detection event of both check types
(72 Z, 48 X), where matching puts its X corrections (from the Z checks) and where a second matching on the X checks
puts Z corrections (25 + 25: a qubit in both is the signature of a Y error, which matching on one check type cannot
see), matching's verdict and log p. Trained by streaming fresh shots at five noise levels (no shot is seen twice),
Adam with a cosine learning rate; scored with matching on the same new shots: 95% intervals by the normal
approximation, and a paired (McNemar) test on the shots one decoder gets right and the other wrong.
(A first version that saw only the events and matching's verdict learned to copy matching: +0% at every noise level.)
--eval-only re-scores the stored network.
Writes backend/qcanvas/data/decoder_d5.json.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from qcanvas.decoder import WEIGHTS_D5, inputs_d5 as inputs, matching, mlp_forward, per_round, sample  # noqa: E402

TRAIN_P = [0.01, 0.015, 0.02, 0.03, 0.04]
TEST_P = [0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.06]
CHUNK = 100_000  # shots per noise level per streamed chunk
N_IN = 72 + 48 + 25 + 25 + 2


class Net:
    def __init__(self, sizes: list[int], seed: int = 0):
        rng = np.random.default_rng(seed)
        self.params: list[np.ndarray] = []
        for a, b in zip(sizes, sizes[1:]):
            self.params += [rng.normal(0, math.sqrt(2 / a), (a, b)).astype(np.float32), np.zeros(b, np.float32)]
        self.m = [np.zeros_like(p) for p in self.params]
        self.v = [np.zeros_like(p) for p in self.params]
        self.step = 0

    def layers(self) -> list[tuple[np.ndarray, np.ndarray]]:
        return [(self.params[i], self.params[i + 1]) for i in range(0, len(self.params), 2)]

    def fit(self, x: np.ndarray, y: np.ndarray, lr: float, batch: int = 2048, seed: int = 0) -> float:
        order = np.random.default_rng(seed).permutation(len(y))
        loss = 0.0
        for k in range(0, len(y), batch):
            idx = order[k:k + batch]
            xb, yb = x[idx], y[idx]
            acts, zs = [xb], []
            for i in range(0, len(self.params) - 2, 2):
                z = acts[-1] @ self.params[i] + self.params[i + 1]
                zs.append(z)
                acts.append(np.maximum(z, 0))
            out = 1 / (1 + np.exp(-(acts[-1] @ self.params[-2] + self.params[-1])[:, 0]))
            loss += float(-np.sum(yb * np.log(out + 1e-7) + (1 - yb) * np.log(1 - out + 1e-7)))
            g = ((out - yb) / len(idx))[:, None].astype(np.float32)
            grads = [None] * len(self.params)
            grads[-2], grads[-1] = acts[-1].T @ g, g.sum(0)
            delta = g @ self.params[-2].T
            for li in range(len(zs) - 1, -1, -1):
                delta = delta * (zs[li] > 0)
                grads[2 * li], grads[2 * li + 1] = acts[li].T @ delta, delta.sum(0)
                if li:
                    delta = delta @ self.params[2 * li].T
            self.step += 1
            for i, gr in enumerate(grads):
                self.m[i] = 0.9 * self.m[i] + 0.1 * gr
                self.v[i] = 0.999 * self.v[i] + 0.001 * gr * gr
                self.params[i] -= lr * (self.m[i] / (1 - 0.9 ** self.step)) / (np.sqrt(self.v[i] / (1 - 0.999 ** self.step)) + 1e-8)
        return loss / len(y)


def half(e: float, n: int) -> float:
    return 1.96 * math.sqrt(max(e, 1 / n) * (1 - e) / n)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    million = float(args[0]) if args else 12
    chunks = 0 if "--eval-only" in sys.argv else max(1, round(million * 1e6 / (CHUNK * len(TRAIN_P))))
    t0 = time.time()
    net = Net([N_IN, 256, 256, 1])
    seen = 0
    if not chunks:  # keep the trained network, score it again
        old = json.loads(WEIGHTS_D5.read_text(encoding="utf-8"))
        net.params = [np.array(a, np.float32) for w, b in old["layers"] for a in (w, b)]
        seen = old["train_shots"]
    for c in range(chunks):
        xs, ys = [], []
        for i, p in enumerate(TRAIN_P):
            s = sample(CHUNK, p, rounds=5, d=5, seed=10_000 + c * 100 + i)
            mw = matching(s["dz"], p, 5)
            xs.append(inputs(s, mw, p))
            ys.append(s["flip"].astype(np.float32))
        x, y = np.concatenate(xs), np.concatenate(ys)
        lr = 2e-4 + 0.5 * (2e-3 - 2e-4) * (1 + math.cos(math.pi * c / chunks))
        loss = net.fit(x, y, lr, seed=c)
        seen += len(y)
        if c % 5 == 0 or c == chunks - 1:
            print(f"  chunk {c + 1}/{chunks}: {seen:,} shots, loss {loss:.5f}, lr {lr:.1e}, {time.time() - t0:.0f} s", flush=True)
    layers = net.layers()
    rows = []
    for j, p in enumerate(TEST_P):
        n5 = 1_000_000 if p < 0.01 else 400_000
        err_mw = err_nn = fixes = breaks = 0
        for part in range(n5 // 200_000):
            s = sample(200_000, p, rounds=5, d=5, seed=900_000 + j * 100 + part)
            mw = matching(s["dz"], p, 5)
            nn = (mlp_forward(inputs(s, mw, p), layers) > 0.5).astype(np.uint8)
            err_mw += int((mw != s["flip"]).sum())
            err_nn += int((nn != s["flip"]).sum())
            fixes += int(((nn == s["flip"]) & (mw != s["flip"])).sum())  # shots the network gets right and matching wrong
            breaks += int(((nn != s["flip"]) & (mw == s["flip"])).sum())
        s3 = sample(n5, p, rounds=3, d=3, seed=800_000 + j)
        e3 = float((matching(s3["dz"], p, 3) != s3["flip"]).mean())
        e5, en = err_mw / n5, err_nn / n5
        r3, r5, rn = per_round(e3, 3), per_round(e5, 5), per_round(en, 5)
        rows.append({"p": p, "shots": n5, "d3": e3, "d3_ci": half(e3, n5), "d5": e5, "d5_ci": half(e5, n5),
                     "neural": en, "neural_ci": half(en, n5), "per_round_d3": r3, "per_round_d5": r5,
                     "per_round_neural": rn, "lam": r3 / r5 if r5 > 0 else None,
                     # paired (McNemar) test on the same shots: z = (fixes - breaks) / sqrt(fixes + breaks)
                     "fixes": fixes, "breaks": breaks, "paired_z": (fixes - breaks) / math.sqrt(fixes + breaks) if fixes + breaks else 0.0})
        print(f"p={p}: d3 {e3:.5f} | d5 matching {e5:.5f} neural {en:.5f} ({(1 - en / e5) * 100 if e5 else 0:+.0f}%, "
              f"fixes {fixes} breaks {breaks}, z {rows[-1]['paired_z']:.1f}) | "
              f"per round d3 {r3:.2e} d5 {r5:.2e}, Lambda {r3 / r5 if r5 else float('nan'):.2f}", flush=True)
    out = {"distance": 5, "rounds": 5, "train_p": TRAIN_P, "train_shots": seen,
           "layers": [(w.round(6).tolist(), b.round(6).tolist()) for w, b in layers], "curve": rows,
           "seconds": round(time.time() - t0, 1)}
    WEIGHTS_D5.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {WEIGHTS_D5} in {out['seconds']} s")


if __name__ == "__main__":
    main()
