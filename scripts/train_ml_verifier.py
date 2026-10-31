"""Train the ML verifier (backend/qcanvas/mlverify.py) and write backend/qcanvas/data/ml_verifier.json.

    .venv/Scripts/python scripts/train_ml_verifier.py [samples]

1. Random circuits of 1 to 7 qubits in five styles (gate soup, layered entanglers, a few gates, mirror circuits
   that undo themselves so the answer is certain, and reversible logic of X, CNOT, Toffoli and SWAP on partly
   superposed inputs, the shape of textbook oracles), random measured subsets, noise scales log-uniform from 0.05x to 5x the realistic preset; each labelled by exact density-matrix
   simulation. Seeded, so a re-run gives the same file.
2. Split 70 / 15 / 15 into training, conformal calibration and test.
3. Five tanh MLPs (16-48-48-1, sigmoid output) trained full-batch with Adam on squared error; the ensemble mean is the
   prediction.
4. Adaptive conformal interval: scores |error| / (ensemble spread + 0.01) on the calibration set; the
   ceil((n+1) 0.9)-th smallest is q, and a prediction's interval is +- q (spread + 0.01), so it widens where the five
   networks disagree.
5. Report on the test set and on the textbook gallery (never seen in training) against the physics baseline.
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from qcanvas.mlverify import FEATURES, WEIGHTS, exact_fidelity, features, mlp_forward  # noqa: E402
from qcanvas.spec import parse_spec  # noqa: E402
from qcanvas.verify.expected import ideal_distribution  # noqa: E402

ONE = ["H", "X", "Y", "Z", "S", "T", "SDG", "TDG", "SX"]
BETA = 0.01  # floor added to the ensemble spread in the adaptive interval
ROT = ["RX", "RY", "RZ"]


def random_circuit(rng: random.Random) -> dict:
    n = rng.choices(range(1, 8), weights=[1, 3, 4, 4, 3, 2, 1])[0]
    style = rng.choices(["soup", "layered", "few", "mirror", "logic"], weights=[4, 3, 2, 2, 2])[0]
    ops: list[dict] = []

    def one(q: int) -> None:
        if rng.random() < 0.4:
            ops.append({"gate": rng.choice(ROT), "targets": [q], "params": [round(rng.uniform(-math.pi, math.pi), 3)]})
        else:
            ops.append({"gate": rng.choice(ONE), "targets": [q]})

    def two() -> None:
        c, t = rng.sample(range(n), 2)
        g = rng.choices(["CX", "CZ", "CP", "SWAP"], weights=[6, 2, 1, 1])[0]
        op = {"gate": g, "controls": [c], "targets": [t]} if g != "SWAP" else {"gate": "SWAP", "targets": [c, t]}
        if g == "CP":
            op["params"] = [round(rng.uniform(-math.pi, math.pi), 3)]
        ops.append(op)

    cap = 30 if n >= 6 else 45
    if style == "few":
        for _ in range(rng.randint(1, 6)):
            two() if n > 1 and rng.random() < 0.5 else one(rng.randrange(n))
    elif style == "layered":
        ops.append({"gate": "H", "targets": list(range(n))})
        for _ in range(rng.randint(1, 4)):
            for q in range(rng.randrange(2), n - 1, 2):
                ops.append({"gate": "CX", "controls": [q], "targets": [q + 1]})
            for q in range(n):
                if rng.random() < 0.6:
                    one(q)
            if len(ops) > cap:
                break
    elif style == "mirror":
        half: list[dict] = []
        for _ in range(rng.randint(1, cap // 2)):
            if n > 1 and rng.random() < 0.45:
                c, t = rng.sample(range(n), 2)
                half.append({"gate": rng.choice(["CX", "CZ"]), "controls": [c], "targets": [t]})
            else:
                g = rng.choice(["H", "X", "S", "T", "RX", "RY", "RZ"])
                op = {"gate": g, "targets": [rng.randrange(n)]}
                if g in ROT:
                    op["params"] = [round(rng.uniform(-math.pi, math.pi), 3)]
                half.append(op)
        inverse = {"S": "SDG", "T": "TDG"}
        undo = []
        for op in reversed(half):
            back = dict(op, gate=inverse.get(op["gate"], op["gate"]))
            if "params" in op:
                back["params"] = [-op["params"][0]]
            undo.append(back)
        ops += half + undo
        for q in range(n):
            if rng.random() < 0.3:
                ops.append({"gate": "X", "targets": [q]})
    elif style == "logic":
        for q in range(n):
            if rng.random() < 0.35:
                ops.append({"gate": rng.choice(["H", "X"]), "targets": [q]})
        for _ in range(rng.randint(1, cap)):
            r = rng.random()
            if n >= 3 and r < 0.3:
                c1, c2, t = rng.sample(range(n), 3)
                ops.append({"gate": "CCX", "controls": [c1, c2], "targets": [t]})
            elif n >= 2 and r < 0.75:
                c, t = rng.sample(range(n), 2)
                ops.append({"gate": "CX", "controls": [c], "targets": [t]} if rng.random() < 0.8
                           else {"gate": "SWAP", "targets": [c, t]})
            else:
                ops.append({"gate": "X", "targets": [rng.randrange(n)]})
    else:
        for _ in range(rng.randint(2, cap)):
            r = rng.random()
            if n >= 3 and r < 0.06:
                c1, c2, t = rng.sample(range(n), 3)
                ops.append({"gate": "CCX", "controls": [c1, c2], "targets": [t]})
            elif n >= 2 and r < 0.45:
                two()
            else:
                one(rng.randrange(n))
    measured = list(range(n)) if rng.random() < 0.75 else sorted(rng.sample(range(n), rng.randint(1, n)))
    return {"kind": "circuit", "num_qubits": n, "num_clbits": len(measured), "operations": ops,
            "measurements": [{"qubit": q, "clbit": i} for i, q in enumerate(measured)]}


def dataset(count: int, seed: int) -> tuple[np.ndarray, np.ndarray, float]:
    rng = random.Random(seed)
    xs, ys, spent = [], [], 0.0
    while len(xs) < count:
        spec = parse_spec(random_circuit(rng))
        scale = math.exp(rng.uniform(math.log(0.05), math.log(5.0)))
        ideal = ideal_distribution(spec)
        start = time.perf_counter()
        y = exact_fidelity(spec, scale, ideal)
        spent += time.perf_counter() - start
        xs.append(features(spec, scale, ideal))
        ys.append(y)
        if len(xs) % 500 == 0:
            print(f"  {len(xs)} labelled", flush=True)
    return np.array(xs), np.array(ys), spent / count


def train_mlp(x: np.ndarray, y: np.ndarray, seed: int, hidden: int = 48, epochs: int = 4000, lr: float = 4e-3,
              l2: float = 1e-5) -> list[tuple[np.ndarray, np.ndarray]]:
    rng = np.random.default_rng(seed)
    sizes = [x.shape[1], hidden, hidden, 1]
    params = []
    for a, b in zip(sizes, sizes[1:]):
        params += [rng.normal(0, math.sqrt(1 / a), (a, b)), np.zeros(b)]
    m = [np.zeros_like(p) for p in params]
    v = [np.zeros_like(p) for p in params]
    n = len(y)
    for step in range(1, epochs + 1):
        w1, b1, w2, b2, w3, b3 = params
        h1 = np.tanh(x @ w1 + b1)
        h2 = np.tanh(h1 @ w2 + b2)
        out = 1 / (1 + np.exp(-(h2 @ w3 + b3)[:, 0]))
        g = (2 * (out - y) / n * out * (1 - out))[:, None]
        dw3, db3 = h2.T @ g, g.sum(0)
        d2 = (g @ w3.T) * (1 - h2 ** 2)
        dw2, db2 = h1.T @ d2, d2.sum(0)
        d1 = (d2 @ w2.T) * (1 - h1 ** 2)
        dw1, db1 = x.T @ d1, d1.sum(0)
        grads = [dw1 + 2 * l2 * w1, db1, dw2 + 2 * l2 * w2, db2, dw3 + 2 * l2 * w3, db3]
        for i, gr in enumerate(grads):
            m[i] = 0.9 * m[i] + 0.1 * gr
            v[i] = 0.999 * v[i] + 0.001 * gr * gr
            params[i] -= lr * (m[i] / (1 - 0.9 ** step)) / (np.sqrt(v[i] / (1 - 0.999 ** step)) + 1e-8)
    return [(params[0], params[1]), (params[2], params[3]), (params[4], params[5])]


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    t0 = time.perf_counter()
    print(f"labelling {count} random circuits by exact simulation", flush=True)
    x, y, exact_s = dataset(count, seed=2026)
    idx = np.random.default_rng(7).permutation(count)
    n_tr, n_cal = int(0.7 * count), int(0.15 * count)
    tr, cal, te = idx[:n_tr], idx[n_tr:n_tr + n_cal], idx[n_tr + n_cal:]
    mean, std = x[tr].mean(0), x[tr].std(0) + 1e-9
    z = (x - mean) / std
    print("training 5 networks", flush=True)
    nets = [train_mlp(z[tr], y[tr], seed) for seed in range(5)]

    def outputs(rows: np.ndarray) -> np.ndarray:
        return np.array([mlp_forward((np.atleast_2d(rows) - mean) / std, net) for net in nets])

    def predict(rows: np.ndarray) -> np.ndarray:
        return outputs(rows).mean(axis=0)

    def spread(rows: np.ndarray) -> np.ndarray:
        return outputs(rows).std(axis=0) + BETA

    scores = np.sort(np.abs(predict(x[cal]) - y[cal]) / spread(x[cal]))
    q90 = float(scores[min(len(scores) - 1, math.ceil((len(scores) + 1) * 0.9) - 1)])
    p_te = predict(x[te])
    w_te = q90 * spread(x[te])
    base = FEATURES.index("baseline")
    dep = FEATURES.index("depolarizing_model")
    err_ml, err_base, err_dep = np.abs(p_te - y[te]), np.abs(x[te, base] - y[te]), np.abs(x[te, dep] - y[te])

    gallery = []
    for path in sorted((ROOT / "examples" / "specs").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("kind") != "circuit" or path.stem == "invalid_circuit":
            continue
        spec = parse_spec(raw)
        ideal = ideal_distribution(spec)
        for scale in (0.5, 1.0, 2.0):
            f = features(spec, scale, ideal)
            exact = exact_fidelity(spec, scale, ideal)
            ml = float(predict(f)[0])
            half = float(q90 * spread(f)[0])
            gallery.append({"circuit": spec.metadata.title or path.stem, "scale": scale, "exact": round(exact, 4),
                            "ml": round(ml, 4), "half_width": round(half, 4), "baseline": round(float(f[base]), 4),
                            "depolarizing": round(float(f[dep]), 4)})
    g_ml = np.array([abs(g["ml"] - g["exact"]) for g in gallery])
    g_half = np.array([g["half_width"] for g in gallery])
    g_dep = np.array([abs(g["depolarizing"] - g["exact"]) for g in gallery])
    g_base = np.array([abs(g["baseline"] - g["exact"]) for g in gallery])

    start = time.perf_counter()
    for _ in range(200):
        predict(x[te[0]])
    predict_us = (time.perf_counter() - start) / 200 * 1e6
    metrics = {
        "samples": count, "train": int(n_tr), "calibration": int(n_cal), "test": int(len(te)),
        "test_mae_ml": round(float(err_ml.mean()), 4), "test_mae_baseline": round(float(err_base.mean()), 4),
        "test_mae_depolarizing": round(float(err_dep.mean()), 4),
        "test_max_error_ml": round(float(err_ml.max()), 4),
        "test_coverage": round(float((err_ml <= w_te + 1e-12).mean()), 4),
        "test_mean_half_width": round(float(w_te.mean()), 4),
        "gallery_cases": len(gallery), "gallery_mae_ml": round(float(g_ml.mean()), 4),
        "gallery_mae_baseline": round(float(g_base.mean()), 4),
        "gallery_mae_depolarizing": round(float(g_dep.mean()), 4),
        "gallery_coverage": round(float((g_ml <= g_half + 1e-12).mean()), 4),
        "exact_ms_mean": round(exact_s * 1e3, 2), "predict_us": round(predict_us, 1),
        "trained_qubits": "1 to 7", "seconds": round(time.perf_counter() - t0, 1),
    }
    out = {
        "features": FEATURES, "mean": mean.round(8).tolist(), "std": std.round(8).tolist(),
        "ensemble": [[(w.round(7).tolist(), b.round(7).tolist()) for w, b in net] for net in nets],
        "q90": round(q90, 5), "beta": BETA, "metrics": metrics,
        "scatter": [(round(float(y[i]), 4), round(float(p), 4), round(float(x[i, base]), 4))
                    for i, p in zip(te[:500], p_te[:500])],
        "gallery": gallery,
    }
    WEIGHTS.parent.mkdir(parents=True, exist_ok=True)
    WEIGHTS.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(metrics, indent=1))
    print(f"wrote {WEIGHTS} ({WEIGHTS.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
