"""When does quantum win for my problem? Error-corrected resource estimates against the best classical route.

Families, each with its algorithm cost from the literature:

* Factoring an n-bit RSA modulus: Gidney & Ekera, "How to factor 2048 bit RSA integers in 8 hours using 20 million
  noisy qubits", Quantum 5, 433 (2021): 3n + 0.002 n lg n logical qubits, 0.3 n^3 + 0.0005 n^3 lg n Toffolis and
  500 n^2 + n^2 lg n measurement depth. Classical: the general number field sieve, scaled from RSA-250 (829 bits,
  factored in 2020 with about 2,700 core-years, Boudot et al.) by the ratio of L_n[1/3, (64/9)^(1/3)].
* Unstructured search over N = 2^k candidates: Grover with (pi/4) sqrt(N) queries; the user (or Muse Spark) gives the
  oracle's Toffoli count and how fast one classical core checks a candidate. Classical: N/2 checks on a stated number
  of cores. Babbush et al., PRX Quantum 2, 010103 (2021) explain why quadratic speedups rarely pay off once error
  correction is counted; this estimate shows the same.
* Simulating a 2D transverse-field Ising magnet (L x L spins, J = h = 1) for time t to accuracy eps: first-order
  Trotter with the rigorous bound ||[A, B]|| <= 8 n J h, so r = ceil(4 n J h t^2 / eps) steps; each step has 3n
  rotations, each synthesised with about 3 log2(1/delta) T gates (Ross & Selinger 2016), delta = eps / rotations.
  Classical: an exact state vector needs 16 * 2^n bytes (the observatory's memory wall); approximate methods are not
  bounded here, which the verdict says.

Error correction (surface code, in the style of Beverland et al., arXiv:2211.07629): logical error per patch per
cycle P_L(d) = 0.03 (p / 0.01)^((d+1)/2); the code distance is the smallest odd d with patches * cycles * P_L <= 0.5%;
patches = 2Q + ceil(sqrt(8Q)) + 1 for Q algorithm qubits (routing space); each patch is 2 d^2 physical qubits; each
logical step lasts d cycles. Magic states (4 T per Toffoli) come from factories modelled as 25 patches producing one T
state every 10 d cycles after two rounds of 15-to-1 distillation (output error 35 (35 p^3)^3); there are as many as the
consumption rate needs. These are simplifications: the model is checked against Gidney and Ekera's published RSA-2048
figure on every factoring result, so its error is visible.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel

BUDGET = 0.01  # total failure probability of a run
TODAY_PHYSICAL_QUBITS = 1_000  # order of today's largest chips (IBM Condor: 1,121)
RSA250_BITS, RSA250_CORE_YEARS = 829, 2_700
SECONDS_PER_YEAR = 3.156e7


class Hardware(BaseModel):
    id: str
    label: str
    p: float  # physical error rate
    cycle_s: float


HARDWARE = {
    "superconducting": Hardware(id="superconducting", label="Superconducting, 0.1% error, 1 µs cycle", p=1e-3,
                                cycle_s=1e-6),
    "better": Hardware(id="better", label="Ten times cleaner qubits, 0.01% error, 1 µs cycle", p=1e-4, cycle_s=1e-6),
    "ions": Hardware(id="ions", label="Slower, cleaner-gate qubits (ion style), 0.1% error, 100 µs cycle", p=1e-3,
                     cycle_s=1e-4),
}


class Algorithm(BaseModel):
    logical_qubits: float
    toffolis: float
    depth: float  # logical time steps


class Quantum(BaseModel):
    code_distance: int
    logical_qubits: int
    patches: int
    physical_qubits: float
    data_qubits: float
    factory_qubits: float
    factories: int
    t_count: float
    runtime_s: float
    feasible: bool
    note: str = ""


def p_logical(d: int, p: float) -> float:
    return 0.03 * (p / 0.01) ** ((d + 1) / 2)


def surface_code(alg: Algorithm, hw: Hardware) -> Quantum:
    q = max(1, math.ceil(alg.logical_qubits))
    patches = 2 * q + math.ceil(math.sqrt(8 * q)) + 1
    if hw.p >= 0.01:
        return Quantum(code_distance=0, logical_qubits=q, patches=patches, physical_qubits=math.inf, data_qubits=0,
                       factory_qubits=0, factories=0, t_count=4 * alg.toffolis, runtime_s=math.inf, feasible=False,
                       note="physical error at or above the 1% threshold: error correction cannot help")
    d = 3
    while d < 201:
        cycles = alg.depth * d
        if patches * cycles * p_logical(d, hw.p) <= BUDGET / 2:
            break
        d += 2
    runtime = alg.depth * d * hw.cycle_s
    t_count = 4 * alg.toffolis
    t_out = 35 * (35 * hw.p ** 3) ** 3
    note = ""
    if t_out * t_count > BUDGET / 2:
        note = "two rounds of distillation are not enough for this many T gates; a third round would be needed"
    rate = t_count / runtime if runtime > 0 else 0.0
    factories = max(1, math.ceil(rate * 10 * d * hw.cycle_s)) if t_count else 0
    data = patches * 2 * d * d
    fq = factories * 25 * 2 * d * d
    return Quantum(code_distance=d, logical_qubits=q, patches=patches, physical_qubits=data + fq, data_qubits=data,
                   factory_qubits=fq, factories=factories, t_count=t_count, runtime_s=runtime, feasible=True, note=note)


# ---------------------------------------------------------------- the families

def factoring_algorithm(n: int) -> Algorithm:
    lg = math.log2(n)
    return Algorithm(logical_qubits=3 * n + 0.002 * n * lg, toffolis=0.3 * n ** 3 + 0.0005 * n ** 3 * lg,
                     depth=500 * n ** 2 + n ** 2 * lg)


def gnfs_core_years(bits: int) -> float:
    def L(b: int) -> float:
        ln = b * math.log(2)
        return math.exp((64 / 9) ** (1 / 3) * ln ** (1 / 3) * math.log(ln) ** (2 / 3))
    return RSA250_CORE_YEARS * L(bits) / L(RSA250_BITS)


def search_algorithm(k: float, oracle_toffolis: float) -> Algorithm:
    queries = math.pi / 4 * math.sqrt(2 ** k)
    per_query = oracle_toffolis + k  # oracle plus the diffuser's multi-controlled flip
    return Algorithm(logical_qubits=2 * k + 10, toffolis=queries * per_query, depth=queries * per_query)


def simulation_algorithm(side: int, t: float, eps: float) -> tuple[Algorithm, dict[str, float]]:
    n = side * side
    steps = math.ceil(4 * n * t * t / eps)
    rotations = 3 * n * steps
    t_per_rotation = 3 * math.log2(rotations / eps)
    alg = Algorithm(logical_qubits=n + 2, toffolis=rotations * t_per_rotation / 4,
                    depth=steps * 3 * t_per_rotation)
    return alg, {"spins": n, "trotter_steps": steps, "rotations": rotations, "t_per_rotation": t_per_rotation}


class Point(BaseModel):
    x: float
    quantum_s: float | None
    classical_s: float | None
    physical_qubits: float | None


class Estimate(BaseModel):
    family: str  # factoring | search | simulation | none
    title: str
    hardware: Hardware
    verdict: str  # classical wins | quantum wins, with a large machine | no known quantum speedup | ...
    headline: str
    quantum: Quantum | None
    classical_s: float | None
    classical_note: str
    details: dict[str, Any]
    curve: list[Point]
    curve_x: str
    check: str = ""  # the model against a published figure
    assumptions: list[str]
    sources: list[str]
    read_by: str = "preset"  # preset | muse | offline


def _years(s: float) -> str:
    if s is None or math.isinf(s):
        return "never"
    if s < 60:
        return f"{s:.3g} seconds"
    if s < 3600:
        return f"{s / 60:.3g} minutes"
    if s < 86400 * 2:
        return f"{s / 3600:.3g} hours"
    if s < SECONDS_PER_YEAR:
        return f"{s / 86400:.3g} days"
    y = s / SECONDS_PER_YEAR
    return f"{y:,.3g} years" if y < 1e6 else f"{y:.2g} years"


def _qubits(x: float) -> str:
    return "infinitely many" if math.isinf(x) else f"{x / 1e6:.3g} million" if x >= 1e6 else f"{x:,.0f}"


COMMON = [
    "Surface code: logical error 0.03 (p/0.01)^((d+1)/2) per patch per cycle; 2d² physical qubits per patch; "
    "routing space 2Q + √(8Q) + 1 patches; one logical step per d cycles; 1% total failure budget.",
    "Magic states: 4 T per Toffoli; factories of 25 patches, one T state per 10 d cycles, two rounds of 15-to-1.",
    "Simplified on purpose: detailed compilations differ by factors of a few, as the check against a published "
    "figure shows.",
]
SOURCES_QEC = ["Beverland et al., Assessing requirements to scale to practical quantum advantage, arXiv:2211.07629 "
               "(2022)", "Fowler et al., Surface codes: towards practical large-scale quantum computation, "
               "PRA 86, 032324 (2012)"]


def estimate_factoring(bits: int, hw: Hardware) -> Estimate:
    bits = max(64, min(int(bits), 8192))
    qc = surface_code(factoring_algorithm(bits), hw)
    cl = gnfs_core_years(bits) * SECONDS_PER_YEAR
    ref = surface_code(factoring_algorithm(2048), HARDWARE["superconducting"])
    check = (f"Model check: for RSA-2048 on 0.1%-error, 1 µs hardware this model gives {_qubits(ref.physical_qubits)} "
             f"physical qubits and {_years(ref.runtime_s)}; Gidney & Ekerå (2021) report 20 million and 8 hours. "
             "Newer constructions (Gidney 2025) bring it under a million qubits in under a week.")
    curve = []
    for b in (512, 768, 1024, 1536, 2048, 3072, 4096):
        q = surface_code(factoring_algorithm(b), hw)
        curve.append(Point(x=b, quantum_s=q.runtime_s, classical_s=gnfs_core_years(b) * SECONDS_PER_YEAR,
                           physical_qubits=q.physical_qubits))
    quantum_faster = qc.runtime_s < cl
    verdict = "quantum wins, with a large machine" if quantum_faster else "classical wins"
    headline = (f"Factoring a {bits}-bit RSA key: about {_qubits(qc.physical_qubits)} physical qubits running for "
                f"{_years(qc.runtime_s)}, {qc.physical_qubits / TODAY_PHYSICAL_QUBITS:,.0f} times more qubits than "
                f"today's largest chips. The best classical method needs about {_years(cl / 1)} of one CPU core.")
    return Estimate(
        family="factoring", title=f"Factor a {bits}-bit RSA key", hardware=hw, verdict=verdict, headline=headline,
        quantum=qc, classical_s=cl,
        classical_note=f"General number field sieve, one core, scaled from RSA-250 ({RSA250_CORE_YEARS:,} core-years "
                       "in 2020); a big cluster divides this by its core count.",
        details={"bits": bits, "toffolis": factoring_algorithm(bits).toffolis}, curve=curve, curve_x="key size, bits",
        check=check,
        assumptions=["Gidney & Ekerå's construction: 3n + 0.002 n lg n logical qubits, 0.3 n³ + 0.0005 n³ lg n "
                     "Toffolis, measurement depth 500 n² + n² lg n."] + COMMON,
        sources=["Gidney & Ekerå, How to factor 2048 bit RSA integers in 8 hours using 20 million noisy qubits, "
                 "Quantum 5, 433 (2021)", "Gidney, How to factor 2048 bit RSA integers with less than a million "
                 "noisy qubits, arXiv:2505.15917 (2025)", "Boudot et al., Comparing the difficulty of factorization "
                 "and discrete logarithm: a 240-digit experiment, CRYPTO 2020 (RSA-250)"] + SOURCES_QEC)


def estimate_search(k: float, oracle_toffolis: float, checks_per_s: float, cores: float, hw: Hardware) -> Estimate:
    k = max(10.0, min(float(k), 256.0))
    oracle_toffolis = max(1.0, float(oracle_toffolis))

    def classical(kk: float) -> float:
        return 2 ** kk / 2 / (checks_per_s * cores)

    qc = surface_code(search_algorithm(k, oracle_toffolis), hw)
    curve = [Point(x=kk, quantum_s=surface_code(search_algorithm(kk, oracle_toffolis), hw).runtime_s,
                   classical_s=classical(kk), physical_qubits=None) for kk in range(20, 129, 4)]
    cross = next((p.x for p in curve if p.quantum_s is not None and p.classical_s is not None
                  and p.quantum_s < p.classical_s), None)
    cl = classical(k)
    wins = qc.runtime_s < cl
    verdict = "quantum wins, with a large machine" if wins else "classical wins"
    tail = (f" The quantum computer only pulls ahead from about 2^{cross:.0f} candidates, where the classical search "
            f"already takes {_years(classical(cross))}." if cross else
            " Within this range the quantum computer never pulls ahead.")
    headline = (f"Searching 2^{k:.0f} candidates: the error-corrected quantum computer takes {_years(qc.runtime_s)} "
                f"on {_qubits(qc.physical_qubits)} physical qubits; {cores:,.0f} classical cores take {_years(cl)}."
                + tail)
    return Estimate(
        family="search", title=f"Search 2^{k:.0f} candidates", hardware=hw, verdict=verdict, headline=headline,
        quantum=qc, classical_s=cl,
        classical_note=f"{checks_per_s:,.3g} checks per second per core on {cores:,.0f} cores, half the space on "
                       "average.",
        details={"log2_candidates": k, "oracle_toffolis": oracle_toffolis, "queries": math.pi / 4 * math.sqrt(2 ** k),
                 "crossover_log2": cross},
        curve=curve, curve_x="candidates, log2",
        assumptions=["Grover: (π/4)√N queries, each the oracle's Toffolis plus about k for the diffuser, run one "
                     "after another; 2k + 10 logical qubits."] + COMMON,
        sources=["Grover, A fast quantum mechanical algorithm for database search, STOC 1996",
                 "Babbush et al., Focus beyond quadratic speedups for error-corrected quantum advantage, PRX Quantum 2, "
                 "010103 (2021)"] + SOURCES_QEC)


def estimate_simulation(side: int, t: float, eps: float, hw: Hardware) -> Estimate:
    side = max(2, min(int(side), 40))
    t, eps = max(0.1, float(t)), min(max(float(eps), 1e-6), 0.1)
    alg, info = simulation_algorithm(side, t, eps)
    qc = surface_code(alg, hw)
    n = info["spins"]
    mem = 16 * 2.0 ** n
    curve = []
    for s in range(3, 15):
        a, _ = simulation_algorithm(s, t, eps)
        q = surface_code(a, hw)
        curve.append(Point(x=s * s, quantum_s=q.runtime_s, classical_s=None, physical_qubits=q.physical_qubits))
    exact = n <= 49
    verdict = "classical can still do it exactly" if exact else "quantum wins, with a large machine (contested)"
    headline = (f"Simulating {n} interacting spins for time {t:g} to accuracy {eps:g}: about "
                f"{_qubits(qc.physical_qubits)} physical qubits for {_years(qc.runtime_s)}. An exact classical "
                f"simulation needs {mem / 1e15:,.3g} PB of memory"
                + (", which a supercomputer has." if exact else ", more than any computer has; approximate classical "
                   "methods may still cope for short times or weak entanglement, so this is where claims of quantum "
                   "advantage are argued."))
    return Estimate(
        family="simulation", title=f"Simulate a {side}×{side} quantum magnet", hardware=hw, verdict=verdict,
        headline=headline, quantum=qc, classical_s=None,
        classical_note=f"Exact state vector: 16 × 2^{n} bytes = {mem:.3g} bytes; the largest supercomputers hold "
                       "about 10^16.",
        details=info, curve=curve, curve_x="spins",
        assumptions=["H = Σ Z_i Z_j + Σ X_i on a periodic L×L lattice; first-order Trotter with the rigorous "
                     "commutator bound ‖[A,B]‖ ≤ 8n, r = ⌈4 n t² / ε⌉ steps; 3n rotations per step, each about "
                     "3 log₂(1/δ) T gates.", "This is a worst-case bound on purpose: higher-order product formulas "
                     "and tighter error estimates cut the step count by orders of magnitude, so read it as an upper "
                     "end."] + COMMON,
        sources=["Childs et al., Theory of Trotter error with commutator scaling, PRX 11, 011020 (2021)",
                 "Ross & Selinger, Optimal ancilla-free Clifford+T approximation of z-rotations, QIC 16 (2016)"]
        + SOURCES_QEC)


def estimate_none(title: str, reason: str, hw: Hardware) -> Estimate:
    return Estimate(family="none", title=title, hardware=hw, verdict="no known quantum speedup",
                    headline=f"{title}: no quantum algorithm is known to do this faster than a classical computer. "
                             f"{reason}".strip(),
                    quantum=None, classical_s=None, classical_note="", details={}, curve=[], curve_x="",
                    assumptions=[], sources=["Aaronson, Read the fine print, Nature Physics 11, 291 (2015)"])


PRESETS = {
    "rsa2048": {"label": "Break RSA-2048", "family": "factoring", "bits": 2048},
    "password": {"label": "Crack a 64-bit key by search", "family": "search", "log2_candidates": 64,
                 "oracle_toffolis": 1000, "checks_per_second": 1e8, "cores": 1e4},
    "magnet": {"label": "Simulate 100 interacting spins", "family": "simulation", "side": 10, "time": 10,
               "accuracy": 1e-3},
    "sort": {"label": "Sort a billion numbers", "family": "none",
             "reason": "Sorting needs to look at every item; quantum computers cannot beat n log n comparisons "
                       "for it, and loading the data is already the bottleneck."},
}


def estimate(params: dict[str, Any], hardware: str = "superconducting") -> Estimate:
    hw = HARDWARE.get(hardware, HARDWARE["superconducting"])
    fam = params.get("family")
    if fam == "factoring":
        return estimate_factoring(int(params.get("bits") or 2048), hw)
    if fam == "search":
        return estimate_search(float(params.get("log2_candidates") or 64), float(params.get("oracle_toffolis") or 1000),
                               float(params.get("checks_per_second") or 1e8), float(params.get("cores") or 1e4), hw)
    if fam == "simulation":
        return estimate_simulation(int(params.get("side") or 10), float(params.get("time") or 10),
                                   float(params.get("accuracy") or 1e-3), hw)
    return estimate_none(str(params.get("title") or params.get("label") or "This problem"),
                         str(params.get("reason") or ""), hw)


MAP_SCHEMA = {"type": "object", "additionalProperties": False,
              "required": ["family", "title", "bits", "log2_candidates", "oracle_toffolis", "checks_per_second",
                           "cores", "side", "time", "accuracy", "reason"],
              "properties": {
                  "family": {"type": "string", "enum": ["factoring", "search", "simulation", "none"]},
                  "title": {"type": "string", "description": "The problem in a few words."},
                  "bits": {"type": "integer", "description": "factoring: key size in bits, else 0"},
                  "log2_candidates": {"type": "number", "description": "search: log2 of the number of candidates"},
                  "oracle_toffolis": {"type": "number", "description": "search: Toffoli gates to check one candidate "
                                                                       "on a quantum computer"},
                  "checks_per_second": {"type": "number", "description": "search: candidates one CPU core checks "
                                                                         "per second"},
                  "cores": {"type": "number", "description": "search: classical cores used"},
                  "side": {"type": "integer", "description": "simulation: lattice side L (L x L spins)"},
                  "time": {"type": "number", "description": "simulation: evolution time in units of the coupling"},
                  "accuracy": {"type": "number", "description": "simulation: target error"},
                  "reason": {"type": "string", "description": "none: why no quantum speedup is known; else empty"}}}
MAP_SYSTEM = (
    "Map a real-world problem onto the closest quantum algorithm family Inkubit can estimate: factoring (breaking "
    "RSA and similar public-key cryptography), search (brute-force search with a checkable answer, e.g. keys, "
    "passwords, constraint satisfaction, unstructured optimisation), simulation (quantum systems: magnets, "
    "materials, molecules as interacting spins), or none (no known quantum speedup: sorting, databases, web "
    "serving, training neural networks, most business software). Choose realistic sizes for the problem as "
    "described; use 0 or empty for fields of other families. Be honest: if quantum computers do not help, say none.")


def offline_map(text: str) -> dict[str, Any]:
    import re

    t = text.lower()
    if any(w in t for w in ("rsa", "factor", "encryption", "public key", "crypto")):
        m = re.search(r"(\d{3,4})", t)
        return {"family": "factoring", "bits": int(m.group(1)) if m else 2048}
    if any(w in t for w in ("password", "brute", "search", "key", "sat", "optimi")):
        m = re.search(r"2\^(\d+)|(\d+)[- ]bit", t)
        k = float(m.group(1) or m.group(2)) if m else 64
        return {"family": "search", "log2_candidates": k, "oracle_toffolis": 1000, "checks_per_second": 1e8,
                "cores": 1e4}
    if any(w in t for w in ("simulat", "magnet", "spin", "material", "molecule", "chemistry")):
        return {"family": "simulation", "side": 10, "time": 10, "accuracy": 1e-3}
    return {"family": "none", "title": text.strip()[:80] or "This problem",
            "reason": "Offline, the keyword reader found no quantum family for it; with a key Muse Spark reads it."}
