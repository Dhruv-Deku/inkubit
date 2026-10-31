"""Train the neural surface-code decoder (backend/qcanvas/decoder.py) and score it against matching.

    .venv/Scripts/python scripts/train_decoder.py [shots_per_noise_level]

Training data: fresh simulated memory experiments (d = 3, 3 rounds, phenomenological noise) at six noise levels;
inputs are every detection event of both check types plus log p (a deployed decoder is calibrated to its device).
Network: 25-128-128-1, ReLU, sigmoid output, binary cross-entropy, Adam with mini-batches, 8 epochs, fixed seeds.
Test: new shots at each noise level (other seeds), both decoders on the same shots; 95% intervals by the normal
approximation. Writes backend/qcanvas/data/decoder.json.
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

from qcanvas.decoder import WEIGHTS, features, mlp_forward, mwpm, sample, unprotected  # noqa: E402

TRAIN_P = [0.005, 0.01, 0.02, 0.03, 0.04, 0.06]
TEST_P = [0.003, 0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.06]


def inputs(s: dict, p: float) -> np.ndarray:
    x = features(s)
    return np.concatenate([x, np.full((len(x), 1), math.log(p) / 5, np.float32)], axis=1)


def train(x: np.ndarray, y: np.ndarray, epochs: int = 8, batch: int = 4096, lr: float = 2e-3, seed: int = 0):
    rng = np.random.default_rng(seed)
    sizes = [x.shape[1], 128, 128, 1]
    params = []
    for a, b in zip(sizes, sizes[1:]):
        params += [rng.normal(0, math.sqrt(2 / a), (a, b)).astype(np.float32), np.zeros(b, np.float32)]
    m = [np.zeros_like(p) for p in params]
    v = [np.zeros_like(p) for p in params]
    step = 0
    for ep in range(epochs):
        order = rng.permutation(len(y))
        loss = 0.0
        for k in range(0, len(y), batch):
            idx = order[k:k + batch]
            xb, yb = x[idx], y[idx]
            w1, b1, w2, b2, w3, b3 = params
            z1 = xb @ w1 + b1
            h1 = np.maximum(z1, 0)
            z2 = h1 @ w2 + b2
            h2 = np.maximum(z2, 0)
            out = 1 / (1 + np.exp(-(h2 @ w3 + b3)[:, 0]))
            loss += float(-np.mean(yb * np.log(out + 1e-7) + (1 - yb) * np.log(1 - out + 1e-7))) * len(idx)
            g = ((out - yb) / len(idx))[:, None].astype(np.float32)
            dw3, db3 = h2.T @ g, g.sum(0)
            d2 = (g @ w3.T) * (z2 > 0)
            dw2, db2 = h1.T @ d2, d2.sum(0)
            d1 = (d2 @ w2.T) * (z1 > 0)
            dw1, db1 = xb.T @ d1, d1.sum(0)
            step += 1
            for i, gr in enumerate([dw1, db1, dw2, db2, dw3, db3]):
                m[i] = 0.9 * m[i] + 0.1 * gr
                v[i] = 0.999 * v[i] + 0.001 * gr * gr
                params[i] -= lr * (m[i] / (1 - 0.9 ** step)) / (np.sqrt(v[i] / (1 - 0.999 ** step)) + 1e-8)
        print(f"  epoch {ep + 1}: loss {loss / len(y):.5f}", flush=True)
    return [(params[0], params[1]), (params[2], params[3]), (params[4], params[5])]


def main() -> None:
    per = int(sys.argv[1]) if len(sys.argv) > 1 else 300_000
    t0 = time.time()
    xs, ys = [], []
    for i, p in enumerate(TRAIN_P):
        s = sample(per, p, seed=100 + i)
        xs.append(inputs(s, p))
        ys.append(s["flip"].astype(np.float32))
    x, y = np.concatenate(xs), np.concatenate(ys)
    print(f"training on {len(y):,} shots", flush=True)
    layers = train(x, y)
    rows = []
    for j, p in enumerate(TEST_P):
        s = sample(200_000, p, seed=900 + j)
        nn = (mlp_forward(inputs(s, p), layers) > 0.5).astype(np.uint8)
        cache: dict = {}
        mw = np.array([mwpm(s["dz"][i], p, cache=cache) for i in range(len(s["flip"]))], np.uint8)
        e_nn, e_mw = float((nn != s["flip"]).mean()), float((mw != s["flip"]).mean())
        half = lambda e: 1.96 * math.sqrt(e * (1 - e) / len(s["flip"]))  # noqa: E731
        rows.append({"p": p, "unprotected": unprotected(p), "mwpm": e_mw, "mwpm_ci": half(e_mw), "neural": e_nn,
                     "neural_ci": half(e_nn), "shots": len(s["flip"])})
        print(f"p={p}: unprotected {unprotected(p):.5f}  matching {e_mw:.5f}  neural {e_nn:.5f}", flush=True)
    out = {"rounds": 3, "distance": 3, "train_p": TRAIN_P, "train_shots": int(len(y)),
           "layers": [(w.round(6).tolist(), b.round(6).tolist()) for w, b in layers], "curve": rows,
           "seconds": round(time.time() - t0, 1)}
    WEIGHTS.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {WEIGHTS} in {out['seconds']} s")


if __name__ == "__main__":
    main()
