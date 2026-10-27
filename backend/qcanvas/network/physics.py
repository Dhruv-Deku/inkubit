"""Physical constants and per-link formulas for the analytic network model.

Every number here is a stated assumption (DECISIONS.md D12), chosen so the
satellite preset lands near published Micius results (~1 pair/s over
1,200 km, ~64-82 dB two-downlink loss), not tuned to any test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Fiber (1550 nm telecom)
FIBER_DB_PER_KM = 0.2
FIBER_SPEED_KM_S = 2.0e5
FIBER_DETECTOR_EFF = 0.8  # superconducting nanowire detectors
FIBER_DARK_PER_GATE = 1e-7

# Free space (810 nm)
WAVELENGTH_M = 810e-9
TX_APERTURE_M = 0.30  # satellite transmitter telescope
RX_APERTURE_M = 1.0  # default ground telescope
TURBULENCE_DIVERGENCE_RAD = 8e-6  # beam broadening + pointing jitter
DOWNLINK_ATMOSPHERE_DB = 4.0  # whole-atmosphere pass at typical elevation
HORIZONTAL_ATMOSPHERE_DB_PER_KM = 0.1  # ground-to-ground clear air
OPTICS_DB = 8.0  # telescope optics, coupling and pointing losses
FREE_SPACE_DETECTOR_EFF = 0.6  # silicon single-photon detectors
FREE_SPACE_DARK_PER_GATE = 1e-5  # includes background light

# Sources, memories, swapping
SOURCE_RATE_HZ = 1e8  # pump pulses per second
PAIR_PROB = 0.1  # pair emission probability per pulse (keeps multi-pairs low)
SOURCE_FIDELITY = 0.98  # intrinsic Werner fidelity of a fresh pair
MULTIPLEX_MODES = 100  # parallel modes per memory heralding window
BSM_SUCCESS = 0.5  # linear-optics Bell-state measurement
SWAP_FIDELITY = 0.99  # Werner factor lost per swap operation
DEFAULT_T2_MS = 10.0
FREE_SPACE_SPEED_KM_S = 3.0e5


@dataclass(frozen=True)
class LinkLoss:
    """Loss of one link and its parts (all in dB)."""

    total_db: float
    parts: dict[str, float]

    @property
    def transmissivity(self) -> float:
        return 10 ** (-self.total_db / 10)


def db(x: float) -> float:
    """Linear transmissivity -> dB loss."""
    return -10 * math.log10(max(x, 1e-300))


def fiber_loss(length_km: float) -> LinkLoss:
    """Attenuation only (connectors folded into the 0.2 dB/km figure)."""
    return LinkLoss(FIBER_DB_PER_KM * length_km, {"attenuation": FIBER_DB_PER_KM * length_km})


def free_space_loss(length_km: float, satellite: bool, rx_aperture_m: float | None = None) -> LinkLoss:
    """Diffraction + turbulence spot vs receiver aperture, plus atmosphere and optics."""
    d_rx = rx_aperture_m or RX_APERTURE_M
    theta_d = 1.22 * WAVELENGTH_M / TX_APERTURE_M
    theta = math.hypot(theta_d, TURBULENCE_DIVERGENCE_RAD)
    spot_m = theta * length_km * 1e3
    geometric = min(1.0, (d_rx / spot_m) ** 2) if spot_m > 0 else 1.0
    atmosphere = DOWNLINK_ATMOSPHERE_DB if satellite else HORIZONTAL_ATMOSPHERE_DB_PER_KM * length_km
    parts = {"diffraction": db(geometric), "atmosphere": atmosphere, "optics": OPTICS_DB}
    return LinkLoss(sum(parts.values()), parts)


def binary_entropy(p: float) -> float:
    """h(p) in bits, 0 at the ends."""
    if p <= 0 or p >= 1:
        return 0.0
    return -p * math.log2(p) - (1 - p) * math.log2(1 - p)


def werner_from_fidelity(f: float) -> float:
    """Werner parameter w with F = (3w + 1) / 4."""
    return (4 * f - 1) / 3


def fidelity_from_werner(w: float) -> float:
    return (3 * w + 1) / 4


def bbm92_key_fraction(qber: float, ec_inefficiency: float = 1.16) -> float:
    """Asymptotic secret fraction 1 - f h(e) - h(e), clamped at 0."""
    return max(0.0, 1 - ec_inefficiency * binary_entropy(qber) - binary_entropy(qber))
