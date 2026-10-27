"""Noise presets shared by the code generator and the independent verifier.

The numbers are deliberately ordinary for today's superconducting hardware
(see DECISIONS.md D7), not tuned to make any circuit pass.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from qiskit_aer.noise import NoiseModel, ReadoutError, depolarizing_error, thermal_relaxation_error

NoisePresetName = Literal["ideal", "low_noise", "realistic"]

ONE_QUBIT_GATES = ["h", "x", "y", "z", "s", "t", "rx", "ry", "rz"]
TWO_QUBIT_GATES = ["cx", "cz", "swap"]


@dataclass(frozen=True)
class NoisePreset:
    """Parameters of one noise preset. Times are in microseconds."""

    name: NoisePresetName
    label: str
    p1: float = 0.0  # depolarizing probability per 1-qubit gate
    p2: float = 0.0  # depolarizing probability per 2-qubit gate
    readout_p01: float = 0.0  # P(read 1 | prepared 0)
    readout_p10: float = 0.0  # P(read 0 | prepared 1)
    t1_us: float | None = None
    t2_us: float | None = None
    gate_1q_us: float = 0.05
    gate_2q_us: float = 0.4

    @property
    def is_ideal(self) -> bool:
        return self.p1 == self.p2 == self.readout_p01 == self.readout_p10 == 0 and self.t1_us is None

    def as_dict(self) -> dict[str, object]:
        """Plain-dict form for JSON responses."""
        return asdict(self)


PRESETS: dict[str, NoisePreset] = {
    "ideal": NoisePreset(name="ideal", label="Ideal (no noise)"),
    "low_noise": NoisePreset(
        name="low_noise", label="Low noise", p1=0.0005, p2=0.005, readout_p01=0.005, readout_p10=0.01
    ),
    "realistic": NoisePreset(
        name="realistic", label="Realistic superconducting", p1=0.001, p2=0.015,
        readout_p01=0.02, readout_p10=0.04, t1_us=100.0, t2_us=80.0,
    ),
}


def get_preset(name: str) -> NoisePreset:
    """Look up a preset by name, with a readable error."""
    try:
        return PRESETS[name]
    except KeyError:
        raise ValueError(f"unknown noise preset '{name}'; choose one of {', '.join(PRESETS)}") from None


def build_gate_noise_model(preset: NoisePreset) -> NoiseModel | None:
    """Gate noise only (depolarizing + thermal relaxation), no readout error.

    The verifier applies readout error separately and exactly.
    """
    if preset.p1 == 0 and preset.p2 == 0 and preset.t1_us is None:
        return None
    noise = NoiseModel()
    one_q = depolarizing_error(preset.p1, 1)
    two_q = depolarizing_error(preset.p2, 2)
    if preset.t1_us is not None and preset.t2_us is not None:
        r1 = thermal_relaxation_error(preset.t1_us, preset.t2_us, preset.gate_1q_us)
        r2 = thermal_relaxation_error(preset.t1_us, preset.t2_us, preset.gate_2q_us)
        one_q = one_q.compose(r1)
        two_q = two_q.compose(r2.expand(r2))
    noise.add_all_qubit_quantum_error(one_q, ONE_QUBIT_GATES)
    noise.add_all_qubit_quantum_error(two_q, TWO_QUBIT_GATES)
    return noise


def build_noise_model(preset: NoisePreset) -> NoiseModel | None:
    """Full noise model (gate noise + readout error), or None for ideal."""
    if preset.is_ideal:
        return None
    noise = build_gate_noise_model(preset) or NoiseModel()
    if preset.readout_p01 or preset.readout_p10:
        noise.add_all_qubit_readout_error(
            ReadoutError([[1 - preset.readout_p01, preset.readout_p01],
                          [preset.readout_p10, 1 - preset.readout_p10]])
        )
    return noise
