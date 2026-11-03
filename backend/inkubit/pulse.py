"""Pulse lab: a gate as the microwave pulse that drives a superconducting qubit, simulated with its third level.

Model (rotating frame at the qubit frequency, rotating-wave approximation, time in ns, angular units rad/ns):
a transmon truncated to |0>, |1>, |2> with anharmonicity alpha = -2 pi x 300 MHz (typical for today's chips), so
H(t) = alpha |2><2| + (Omega_x(t)/2)(a + a^dag) + (Omega_y(t)/2) i(a^dag - a), with a|1> = |0>, a|2> = sqrt2 |1>.
The pi pulse (an X gate) is a Gaussian envelope, sigma = duration / 4, cut at the ends and shifted to start and end
at zero, scaled so its area is pi. DRAG (Motzoi et al., PRL 103, 110501, 2009) adds the quadrature
Omega_y = -beta dOmega_x/dt / alpha; beta is tuned by a 1-D search for the best fidelity, as a calibration would.
Decoherence uses the realistic preset (T1 = 100 us, T2 = 80 us) as Lindblad jumps, sqrt(1/T1) a and pure dephasing
on the number operator. The superoperator is integrated in 400 piecewise-constant steps with exact exponentials.

Reported: leakage (population left in |2> starting from |0>), and the average gate fidelity of the qubit-subspace
channel against X, F_avg = (2 F_pro + 1) / 3, where leakage counts as error. The sweep over duration shows the
trade-off every superconducting chip lives with: short pulses leak through |2>, long pulses decohere; DRAG is what
lets gates run in 10 to 20 ns.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from pydantic import BaseModel
from scipy.linalg import expm

ALPHA = -2 * math.pi * 0.300  # rad/ns
T1_NS, T2_NS = 100_000.0, 80_000.0
STEPS = 400
DIM = 3

_a = np.diag([1.0, math.sqrt(2)], 1).astype(complex)
_ad = _a.conj().T
_n = _ad @ _a
_I = np.eye(DIM, dtype=complex)
_HX = _a + _ad
_HY = 1j * (_ad - _a)
_H2 = np.diag([0.0, 0.0, 1.0]).astype(complex)
X_IDEAL = np.array([[0, 1], [1, 0]], complex)


def envelope(duration: float, steps: int = STEPS) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Times (step centres), Omega_x and its derivative for a pi pulse of the given length."""
    t = (np.arange(steps) + 0.5) * duration / steps
    sigma = duration / 4
    g = np.exp(-((t - duration / 2) ** 2) / (2 * sigma ** 2))
    edge = math.exp(-((duration / 2) ** 2) / (2 * sigma ** 2))
    shape = (g - edge) / (1 - edge)
    dt = duration / steps
    omega = shape * math.pi / (shape.sum() * dt)
    deriv = np.gradient(omega, dt)
    return t, omega, deriv


def _lindblad(h: np.ndarray, deco: bool) -> np.ndarray:
    """Liouvillian for column-stacked density matrices: vec(A rho B) = (B^T kron A) vec(rho)."""
    L = -1j * (np.kron(_I, h) - np.kron(h.T, _I))
    if deco:
        gamma1 = 1 / T1_NS
        gphi = max(0.0, 1 / T2_NS - 1 / (2 * T1_NS))
        for c in (math.sqrt(gamma1) * _a, math.sqrt(2 * gphi) * _n):
            cdc = c.conj().T @ c
            L += np.kron(c.conj(), c) - 0.5 * np.kron(_I, cdc) - 0.5 * np.kron(cdc.T, _I)
    return L


def propagate(duration: float, beta: float, deco: bool = True, track: bool = False, steps: int = STEPS
              ) -> tuple[np.ndarray, np.ndarray | None]:
    """Superoperator of the whole pulse (and, if asked, populations over time starting from |0>)."""
    t, ox, dox = envelope(duration, steps)
    oy = -beta * dox / ALPHA
    dt = duration / steps
    S = np.eye(DIM * DIM, dtype=complex)
    rho = np.zeros(DIM * DIM, complex)
    rho[0] = 1.0
    pops = np.zeros((steps + 1, DIM)) if track else None
    if track:
        pops[0] = [1, 0, 0]
    for k in range(steps):
        h = ALPHA * _H2 + 0.5 * ox[k] * _HX + 0.5 * oy[k] * _HY
        step = expm(_lindblad(h, deco) * dt)
        S = step @ S
        if track:
            rho = step @ rho
            pops[k + 1] = np.real(np.diag(rho.reshape(DIM, DIM, order="F")))
    return S, pops


def qubit_metrics(S: np.ndarray, target: np.ndarray = X_IDEAL) -> tuple[float, float]:
    """(average gate fidelity against ``target`` in the qubit subspace, leakage from |0>)."""
    def apply(m: np.ndarray) -> np.ndarray:
        full = np.zeros((DIM, DIM), complex)
        full[:2, :2] = m
        return (S @ full.reshape(-1, order="F")).reshape(DIM, DIM, order="F")[:2, :2]

    d = 2
    choi = np.zeros((4, 4), complex)
    for i in range(2):
        for j in range(2):
            e = np.zeros((2, 2), complex)
            e[i, j] = 1
            choi += np.kron(e, apply(e))
    phi = (np.kron(np.eye(2), target) @ np.array([1, 0, 0, 1], complex)) / math.sqrt(d)
    f_pro = float(np.real(phi.conj() @ (choi / d) @ phi))
    rho0 = np.zeros((DIM, DIM), complex)
    rho0[0, 0] = 1
    leak = float(np.real((S @ rho0.reshape(-1, order="F")).reshape(DIM, DIM, order="F")[2, 2]))
    return (d * f_pro + 1) / (d + 1), leak


@lru_cache(maxsize=64)
def best_beta(duration: float) -> float:
    """The DRAG coefficient for a pulse length: stored with the app for the lab's lengths, else calibrated."""
    from inkubit import precomputed

    stored = precomputed.load_raw("pulse_betas") or {}
    return stored.get(f"{duration:g}") if f"{duration:g}" in stored else calibrate_beta(duration)


def calibrate_beta(duration: float) -> float:
    """1-D calibration of the DRAG coefficient (golden-section search on the gate error)."""
    lo, hi = 0.0, 2.0
    g = (math.sqrt(5) - 1) / 2
    f = lambda b: 1 - qubit_metrics(propagate(duration, b, deco=False, steps=200)[0])[0]  # noqa: E731
    c, d = hi - g * (hi - lo), lo + g * (hi - lo)
    fc, fd = f(c), f(d)
    for _ in range(12):  # brackets beta to about 0.01, plenty for a calibration
        if fc < fd:
            hi, d, fd = d, c, fc
            c = hi - g * (hi - lo)
            fc = f(c)
        else:
            lo, c, fc = c, d, fd
            d = lo + g * (hi - lo)
            fd = f(d)
    return round((lo + hi) / 2, 4)


class PulseRun(BaseModel):
    duration_ns: float
    drag: bool
    beta: float
    times: list[float]
    omega_x_mhz: list[float]  # drive amplitude as a Rabi frequency, MHz
    omega_y_mhz: list[float]
    populations: list[tuple[float, float, float]]
    fidelity: float
    leakage: float
    fidelity_no_decoherence: float


class Sweep(BaseModel):
    durations: list[float]
    gaussian_error: list[float]
    drag_error: list[float]
    gaussian_leak: list[float]
    drag_leak: list[float]
    decoherence_only: list[float]
    best_gaussian: tuple[float, float]
    best_drag: tuple[float, float]


def run(duration: float, drag: bool) -> PulseRun:
    duration = float(min(max(duration, 4.0), 100.0))
    beta = best_beta(round(duration, 2)) if drag else 0.0
    S, pops = propagate(duration, beta, deco=True, track=True)
    fid, leak = qubit_metrics(S)
    fid0, _ = qubit_metrics(propagate(duration, beta, deco=False)[0])
    t, ox, dox = envelope(duration)
    oy = -beta * dox / ALPHA
    keep = slice(None, None, 4)
    to_mhz = 1 / (2 * math.pi) * 1000
    return PulseRun(duration_ns=duration, drag=drag, beta=beta, times=[round(float(x), 3) for x in t[keep]],
                    omega_x_mhz=[round(float(x) * to_mhz, 3) for x in ox[keep]],
                    omega_y_mhz=[round(float(x) * to_mhz, 3) for x in oy[keep]],
                    populations=[(round(float(a), 6), round(float(b), 6), round(float(c), 6)) for a, b, c in pops[::4]],
                    fidelity=fid, leakage=leak, fidelity_no_decoherence=fid0)


DURATIONS = [4, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 70, 100]


@lru_cache(maxsize=1)
def sweep() -> Sweep:
    """Gaussian against DRAG over the lab's pulse lengths: stored with the app when available, else computed."""
    from inkubit import precomputed

    return precomputed.load("pulse_sweep", Sweep) or compute_sweep()


def compute_sweep() -> Sweep:
    durations = DURATIONS
    ge, de, gl, dl, deco = [], [], [], [], []
    for d in durations:
        fg, lg = qubit_metrics(propagate(d, 0.0, steps=200)[0])
        fd, ld = qubit_metrics(propagate(d, best_beta(float(d)), steps=200)[0])
        ge.append(1 - fg)
        de.append(1 - fd)
        gl.append(lg)
        dl.append(ld)
        idle = expm(_lindblad(np.zeros((DIM, DIM), complex), True) * d)  # T1/T2 alone over the same time
        deco.append(1 - qubit_metrics(idle, np.eye(2, dtype=complex))[0])
    bg = min(zip(ge, durations))
    bd = min(zip(de, durations))
    return Sweep(durations=durations, gaussian_error=ge, drag_error=de, gaussian_leak=gl, drag_leak=dl,
                 decoherence_only=deco, best_gaussian=(bg[1], bg[0]), best_drag=(bd[1], bd[0]))
