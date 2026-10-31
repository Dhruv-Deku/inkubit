"""Simulation observatory: five exact sweeps that show where quantum technology stands today.

1. Satellites vs fiber: the secret-key rate between two cities as they move apart, from the same analytic network
   model as the network planner (network/model.py, DECISIONS.md D12): direct fiber, and a satellite at 500 km over
   the midpoint (slant ranges from spherical geometry, only while both stations see it at least 15 degrees above the
   horizon). Micius's 1,203 km entanglement distribution (Yin et al., Science 2017) is marked for scale.
2. Quantum walk: a Hadamard walk on a line, evolved exactly, against a classical random walk. The quantum walker
   spreads in proportion to time, the classical one only to its square root.
3. Grover vs noise: the chance of finding one marked item after k oracle queries, ideal, under the realistic preset
   (the circuit is compiled to CX and one-qubit gates and evolved as a density matrix with the verifier's gate
   channels, then readout error), and for a classical search with the same number of looks.
4. Entanglement growth: half-chain entanglement of 10 qubits under random two-qubit gates, against Page's limit for
   a random state. Once it saturates there is no compact description left to exploit.
5. The exponential wall: memory to store an n-qubit state exactly (2^n complex amplitudes at 16 bytes each).

Everything is deterministic (fixed seeds) and computed once per process.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from pydantic import BaseModel
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import DensityMatrix

from qcanvas.insights.circuit import gate_channels
from qcanvas.network.model import simulate
from qcanvas.sim.noise import get_preset
from qcanvas.spec.models import NetworkSpec

EARTH_RADIUS_KM = 6371.0
SAT_ALTITUDE_KM = 500.0
MIN_ELEVATION_DEG = 15.0
MICIUS_KM = 1203
DISTANCES_KM = [25, 50, 100, 150, 200, 300, 400, 500, 600, 800, 1000, 1200, 1500, 1800, 2100, 2400, 2700, 3000]

WALK_STEPS = 60
GROVER_QUBITS = (2, 3, 4, 5)
CHAIN_QUBITS, CHAIN_DEPTH, CHAIN_SEEDS = 10, 24, 8
WALL_QUBITS = 60
BYTES_PER_AMPLITUDE = 16  # complex128


class Series(BaseModel):
    id: str
    label: str
    points: list[tuple[float, float | None]]  # None where the quantity does not exist (e.g. satellite out of view)


class Reference(BaseModel):
    value: float
    label: str
    axis: str = "y"  # "y": a horizontal line at this value; "x": a vertical one


class Chart(BaseModel):
    id: str
    title: str
    finding: str  # one sentence, numbers filled in from the data
    x_label: str
    y_label: str
    x_log: bool = False
    y_log: bool = False
    series: list[Series]
    references: list[Reference] = []
    method: str


class WalkFrames(BaseModel):
    positions: list[int]  # even sites -T..T (odd sites are empty after an even number of steps)
    steps: list[int]
    quantum: list[list[float]]  # probability per position, one row per step (even steps only)
    classical: list[list[float]]


class GroverCase(BaseModel):
    qubits: int
    marked: str
    best_k: int
    cx_per_query: int
    chart: Chart


class Observatory(BaseModel):
    satellite: Chart
    walk: Chart
    walk_frames: WalkFrames
    grover: list[GroverCase]
    entanglement: Chart
    wall: Chart


# ---------------------------------------------------------------- satellites vs fiber

def _ground(i: str, label: str) -> dict:
    return {"id": i, "type": "ground_station", "label": label}


def _key_rate(spec: dict) -> tuple[float, float]:
    end = simulate(NetworkSpec.model_validate(spec)).end_to_end
    return end.key_rate_bps, end.fidelity


def satellite_geometry(ground_km: float, altitude_km: float = SAT_ALTITUDE_KM) -> tuple[float, float]:
    """Slant range (km) and elevation (degrees) from a station to a satellite over the midpoint."""
    r, s = EARTH_RADIUS_KM, EARTH_RADIUS_KM + altitude_km
    theta = ground_km / 2 / r
    slant = math.sqrt(r * r + s * s - 2 * r * s * math.cos(theta))
    elevation = math.degrees(math.asin((s * math.cos(theta) - r) / slant))
    return slant, elevation


def _fiber(d: float) -> dict:
    return {"nodes": [_ground("a", "City A"), _ground("b", "City B")],
            "links": [{"from": "a", "to": "b", "medium": "fiber", "length_km": d}], "source": "a", "destination": "b"}


def _satellite(d: float) -> dict | None:
    slant, elevation = satellite_geometry(d)
    if elevation < MIN_ELEVATION_DEG:
        return None
    return {"nodes": [_ground("a", "City A"), {"id": "s", "type": "satellite"}, _ground("b", "City B")],
            "links": [{"from": "a", "to": "s", "medium": "free_space", "length_km": slant},
                      {"from": "s", "to": "b", "medium": "free_space", "length_km": slant}],
            "source": "a", "destination": "b"}


def _positive(v: float) -> float | None:
    return float(f"{v:.4g}") if v > 0 else None


def crossover_km(fiber: list[tuple[float, float | None]], sat: list[tuple[float, float | None]]) -> float | None:
    """Distance where the satellite first beats fiber, interpolated in log-log between sample points."""
    prev = None
    for (d, f), (_, sv) in zip(fiber, sat):
        if sv is not None and (f is None or sv > f):
            if prev is None or f is None:
                return d
            d0, f0, s0 = prev
            g0, g1 = math.log(f0 / s0), math.log(f / sv)  # fiber's lead on a log scale: positive, then negative
            t = g0 / (g0 - g1)
            return math.exp(math.log(d0) + t * (math.log(d) - math.log(d0)))
        prev = (d, f, sv) if f is not None and sv is not None else None
    return None


def satellite_chart() -> Chart:
    fiber, sat = [], []
    for d in DISTANCES_KM:
        fiber.append((d, _positive(_key_rate(_fiber(d))[0])))
        spec = _satellite(d)
        sat.append((d, _positive(_key_rate(spec)[0]) if spec else None))
    fiber_end = max((d for d, v in fiber if v is not None), default=0)
    cross = crossover_km(fiber, sat) or 0.0
    micius = _key_rate(_satellite(MICIUS_KM))[0]
    sat_far = max(((d, v) for d, v in sat if v is not None), key=lambda p: p[0])
    finding = (f"Past about {round(cross, -1):,.0f} km the satellite beats fiber, and fiber gives no secret key at "
               f"all beyond {fiber_end:,} km. At {MICIUS_KM:,} km, the distance Micius bridged in 2017, the modelled "
               f"satellite still gives {micius:.1f} key bits per second, and {sat_far[1]:.2g} at {sat_far[0]:,} km.")
    return Chart(
        id="satellite", title="Why satellites: secret key between two cities", finding=finding,
        x_label="distance between the cities, km", y_label="secret key, bits per second", x_log=True, y_log=True,
        series=[Series(id="satellite", label="Satellite, 500 km up", points=sat),
                Series(id="fiber", label="Direct fiber", points=fiber)],
        references=[Reference(value=1.0, label="1 bit per second"),
                    Reference(value=MICIUS_KM, label="Micius 2017", axis="x")],
        method=("Network planner model (D12): 0.2 dB/km fiber with nanowire detectors; a diffraction-limited 30 cm "
                "satellite telescope into 1 m ground telescopes with atmosphere and optics losses; BBM92 key "
                f"fraction. Satellite curve only while both stations see it at least {MIN_ELEVATION_DEG:.0f} degrees "
                "up."))


# ---------------------------------------------------------------- quantum walk

def walk_frames(steps: int = WALK_STEPS) -> WalkFrames:
    """Hadamard walk from the origin with the symmetric coin (|0> + i|1>)/sqrt2, and the classical binomial walk."""
    size = 2 * steps + 1
    psi = np.zeros((size, 2), complex)
    psi[steps] = [1 / math.sqrt(2), 1j / math.sqrt(2)]
    h = np.array([[1, 1], [1, -1]]) / math.sqrt(2)
    classical = np.zeros(size)
    classical[steps] = 1.0
    even = list(range(0, size, 2))
    q_rows, c_rows, kept = [], [], []
    for t in range(steps + 1):
        if t % 2 == 0:
            q_rows.append([round(float(x), 6) for x in (np.abs(psi) ** 2).sum(axis=1)[even]])
            c_rows.append([round(float(x), 6) for x in classical[even]])
            kept.append(t)
        psi = psi @ h.T
        moved = np.zeros_like(psi)
        moved[:-1, 0] = psi[1:, 0]  # coin 0 steps left
        moved[1:, 1] = psi[:-1, 1]  # coin 1 steps right
        psi = moved
        classical = 0.5 * (np.roll(classical, -1) + np.roll(classical, 1))
    return WalkFrames(positions=[i - steps for i in even], steps=kept, quantum=q_rows, classical=c_rows)


def _spread(row: list[float], positions: list[int]) -> float:
    p = np.array(row)
    x = np.array(positions, float)
    mean = float(p @ x)
    return math.sqrt(max(0.0, float(p @ (x - mean) ** 2)))


def walk_chart(frames: WalkFrames) -> Chart:
    q = [(t, round(_spread(r, frames.positions), 4)) for t, r in zip(frames.steps, frames.quantum)]
    c = [(t, round(_spread(r, frames.positions), 4)) for t, r in zip(frames.steps, frames.classical)]
    t_end, q_end, c_end = q[-1][0], q[-1][1], c[-1][1]
    finding = (f"After {t_end} steps the quantum walker has spread {q_end:.1f} sites against {c_end:.1f} for a "
               f"coin-tossing walker, {q_end / c_end:.1f} times as far, and the gap keeps growing: interference "
               "turns diffusion into a front that moves at constant speed.")
    return Chart(
        id="walk", title="Quantum walk: interference beats diffusion", finding=finding,
        x_label="steps", y_label="spread (standard deviation), sites",
        series=[Series(id="quantum", label="Quantum walk", points=q),
                Series(id="classical", label="Classical random walk", points=c)],
        method=("Exact unitary evolution: Hadamard coin, then shift left or right by the coin, from the origin "
                "with coin (|0> + i|1>)/sqrt2. Classical: fair coin, binomial distribution."))


# ---------------------------------------------------------------- Grover vs noise

def _grover_parts(n: int, marked: str) -> tuple[QuantumCircuit, QuantumCircuit]:
    """Preparation and one Grover iteration (oracle + diffuser), compiled to CX and one-qubit gates."""
    def phase_on(bits: str) -> QuantumCircuit:
        qc = QuantumCircuit(n)
        zeros = [q for q in range(n) if bits[n - 1 - q] == "0"]
        if zeros:
            qc.x(zeros)
        qc.h(n - 1)
        qc.mcx(list(range(n - 1)), n - 1)
        qc.h(n - 1)
        if zeros:
            qc.x(zeros)
        return qc

    prep = QuantumCircuit(n)
    prep.h(range(n))
    step = phase_on(marked)
    step.h(range(n))
    step.compose(phase_on("0" * n), inplace=True)
    step.h(range(n))
    basis = ["cx", "rz", "sx", "x"]
    return (transpile(prep, basis_gates=basis, optimization_level=1, seed_transpiler=7),
            transpile(step, basis_gates=basis, optimization_level=1, seed_transpiler=7))


def _evolve(rho: DensityMatrix, qc: QuantumCircuit, channels: dict) -> DensityMatrix:
    for inst in qc.data:
        qargs = [qc.find_bit(q).index for q in inst.qubits]
        rho = rho.evolve(inst.operation, qargs=qargs)
        if channels and len(qargs) in channels:
            rho = rho.evolve(channels[len(qargs)], qargs=qargs)
    return rho


def _read_marked(rho: DensityMatrix, marked: str, p01: float, p10: float) -> float:
    """Chance the readout shows ``marked`` (Qiskit order: rightmost bit is qubit 0), with readout error."""
    probs = rho.probabilities()
    n = len(marked)
    total = 0.0
    for index, p in enumerate(probs):
        if p < 1e-15:
            continue
        keep = 1.0
        for q in range(n):
            actual, want = (index >> q) & 1, int(marked[n - 1 - q])
            keep *= (1 - p01 if want == 0 else p01) if actual == 0 else (p10 if want == 0 else 1 - p10)
        total += p * keep
    return total


def grover_case(n: int) -> GroverCase:
    size = 2 ** n
    marked = format(size - 1 - (size // 3), f"0{n}b")  # a fixed, unremarkable bitstring
    theta = math.asin(1 / math.sqrt(size))
    best_k = max(1, round(math.pi / (4 * theta) - 0.5))
    k_max = 2 * best_k + 1
    preset = get_preset("realistic")
    channels = gate_channels(preset)
    prep, step = _grover_parts(n, marked)
    rho = _evolve(DensityMatrix.from_label("0" * n), prep, channels)
    ideal, noisy, classical = [], [], []
    for k in range(k_max + 1):
        if k:
            rho = _evolve(rho, step, channels)
        ideal.append((k, round(math.sin((2 * k + 1) * theta) ** 2, 6)))
        noisy.append((k, round(_read_marked(rho, marked, preset.readout_p01, preset.readout_p10), 6)))
        classical.append((k, round(min(1.0, (k + 1) / size), 6)))
    cx = sum(1 for inst in step.data if inst.operation.name == "cx")
    peak_k, peak = max(noisy, key=lambda p: p[1])
    finding = (f"Ideal Grover finds the 1 marked item among {size} with probability {ideal[best_k][1]:.0%} after "
               f"{best_k} {'query' if best_k == 1 else 'queries'}. On today's hardware ({cx} CNOTs per query) it "
               f"peaks at {peak:.0%} after {peak_k}, ")
    finding += ("still ahead of a classical search with the same looks." if peak > classical[peak_k][1] + 0.02
                else "no better than a classical search with the same looks: noise has erased the speedup.")
    chart = Chart(
        id=f"grover{n}", title=f"Grover search, {n} qubits ({size} items)", finding=finding,
        x_label="oracle queries", y_label="chance of finding the marked item",
        series=[Series(id="ideal", label="Ideal quantum", points=ideal),
                Series(id="noisy", label="Today's hardware (realistic preset)", points=noisy),
                Series(id="classical", label="Classical, same number of looks", points=classical)],
        method=(f"Circuit compiled to CX, RZ, SX and X ({cx} CNOTs per query), evolved as an exact density matrix "
                "with the realistic preset after every gate (depolarizing 0.1% / 1.5%, T1 100 us, T2 80 us), then "
                "readout error. Classical: check k items, then guess among the rest. A blind guess succeeds with 1/N."))
    return GroverCase(qubits=n, marked=marked, best_k=best_k, cx_per_query=cx, chart=chart)


# ---------------------------------------------------------------- entanglement growth

def _apply_pair(psi: np.ndarray, u: np.ndarray, q: int, n: int) -> np.ndarray:
    """Apply a 4x4 unitary to qubits q, q+1 of an n-qubit state stored as a tensor of shape (2,)*n."""
    psi = np.moveaxis(psi, (q, q + 1), (0, 1)).reshape(4, -1)
    psi = (u @ psi).reshape((2, 2) + (2,) * (n - 2))
    return np.moveaxis(psi, (0, 1), (q, q + 1))


def _haar(rng: np.random.Generator) -> np.ndarray:
    """A Haar-random 4x4 unitary (QR of a complex Gaussian matrix, phases fixed)."""
    z = (rng.standard_normal((4, 4)) + 1j * rng.standard_normal((4, 4))) / math.sqrt(2)
    q, r = np.linalg.qr(z)
    return q * (np.diag(r) / np.abs(np.diag(r)))


def _half_entropy(psi: np.ndarray, n: int) -> float:
    s = np.linalg.svd(psi.reshape(2 ** (n // 2), -1), compute_uv=False) ** 2
    s = s[s > 1e-14]
    return float(-(s * np.log2(s)).sum())


def page_entropy_bits(n_a: int, n_b: int) -> float:
    """Page's average entanglement entropy (bits) of a random pure state on n_a + n_b qubits, n_a <= n_b."""
    m, k = 2 ** n_a, 2 ** n_b
    return (sum(1 / j for j in range(k + 1, m * k + 1)) - (m - 1) / (2 * k)) / math.log(2)


def entanglement_chart(n: int = CHAIN_QUBITS, depth: int = CHAIN_DEPTH, seeds: int = CHAIN_SEEDS) -> Chart:
    runs = np.zeros((seeds, depth + 1))
    for s in range(seeds):
        rng = np.random.default_rng(1000 + s)
        psi = np.zeros((2,) * n, complex)
        psi[(0,) * n] = 1
        for layer in range(1, depth + 1):
            for q in range(layer % 2, n - 1, 2):
                psi = _apply_pair(psi, _haar(rng), q, n)
            runs[s, layer] = _half_entropy(psi, n)
    mean = runs.mean(axis=0)
    page = page_entropy_bits(n // 2, n - n // 2)
    reach = next((d for d in range(depth + 1) if mean[d] >= 0.97 * page), depth)
    finding = (f"Random two-qubit gates entangle the two halves of {n} qubits layer by layer; after {reach} layers "
               f"they hold {mean[reach]:.2f} bits, within 3% of Page's limit for a random state ({page:.2f} bits). "
               "From then on there is no compact description left for a classical computer to exploit.")
    return Chart(
        id="entanglement", title="Entanglement grows until nothing can compress it", finding=finding,
        x_label="layers of random two-qubit gates", y_label="entanglement between the halves, bits",
        series=[Series(id="mean", label=f"Average of {seeds} random circuits",
                       points=[(d, round(float(v), 4)) for d, v in enumerate(mean)]),
                Series(id="low", label="lowest", points=[(d, round(float(v), 4)) for d, v in enumerate(runs.min(axis=0))]),
                Series(id="high", label="highest", points=[(d, round(float(v), 4)) for d, v in enumerate(runs.max(axis=0))])],
        references=[Reference(value=round(page, 4), label="Page limit"),
                    Reference(value=float(n // 2), label=f"maximum ({n // 2} bits)")],
        method=(f"Exact statevector of {n} qubits; each layer applies Haar-random two-qubit unitaries to "
                "alternating neighbour pairs (brickwork); von Neumann entropy of the left half from the Schmidt "
                f"values; {seeds} fixed seeds."))


# ---------------------------------------------------------------- exponential wall

def wall_chart(max_qubits: int = WALL_QUBITS) -> Chart:
    pts = [(n, float(BYTES_PER_AMPLITUDE * 2 ** n)) for n in range(1, max_qubits + 1)]
    laptop = 16e9
    giant = 1e16
    fits = max(n for n, b in pts if b <= laptop)
    giant_n = max(n for n, b in pts if b <= giant)
    finding = (f"Every extra qubit doubles the memory: a 16 GB laptop holds at most {fits} qubits exactly, and "
               f"{giant_n} qubits already need {BYTES_PER_AMPLITUDE * 2 ** giant_n / 1e15:.0f} PB, the scale of the "
               f"largest supercomputers. {max_qubits} qubits would need {BYTES_PER_AMPLITUDE * 2 ** max_qubits / 1e18:,.0f} EB.")
    return Chart(
        id="wall", title="The exponential wall", finding=finding,
        x_label="qubits", y_label="memory to store the state exactly, bytes", y_log=True,
        series=[Series(id="memory", label="Exact state vector", points=pts)],
        references=[Reference(value=laptop, label="16 GB laptop"), Reference(value=giant, label="10 PB supercomputer scale")],
        method="2^n complex amplitudes at 16 bytes each (two 64-bit floats). Exact arithmetic, no estimate.")


@lru_cache(maxsize=1)
def observatory() -> Observatory:
    frames = walk_frames()
    return Observatory(satellite=satellite_chart(), walk=walk_chart(frames), walk_frames=frames,
                       grover=[grover_case(n) for n in GROVER_QUBITS], entanglement=entanglement_chart(),
                       wall=wall_chart())
