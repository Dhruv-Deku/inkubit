"""Noise presets shared by the code generator and the independent verifier.

The numbers are deliberately ordinary for today's superconducting hardware
(see DECISIONS.md D7), not tuned to make any circuit pass.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from qiskit_aer.noise import NoiseModel, QuantumError, ReadoutError, depolarizing_error, thermal_relaxation_error

NoisePresetName = Literal["ideal", "low_noise", "realistic", "calibrated"]
CALIBRATION = Path(__file__).resolve().parents[1] / "data" / "calibration.json"

ONE_QUBIT_GATES = ["h", "x", "y", "z", "s", "t", "sdg", "tdg", "sx", "rx", "ry", "rz"]
TWO_QUBIT_GATES = ["cx", "cz", "cp", "swap"]
THREE_QUBIT_GATES = ["ccx"]
TOFFOLI_CNOTS = 6  # a Toffoli compiles to six CNOTs on today's hardware (DECISIONS.md D17)


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


def calibrated_preset(path: Path = CALIBRATION) -> NoisePreset | None:
    """The preset of a real device, from its calibration snapshot (scripts/calibration_snapshot.py); None without one.

    A reported gate error is an average gate infidelity that already includes decoherence during the gate. The thermal
    part (T1/T2 over the gate time, which gate_errors adds) is taken out first and the rest becomes depolarizing,
    p = r d / (d - 1) on d levels, as Qiskit's NoiseModel.from_backend does; so the composed error of a gate equals the
    reported one (a test checks it). The values are medians over the device: a typical qubit (DECISIONS.md D77).
    """
    if not path.exists():
        return None
    from qiskit.quantum_info import average_gate_fidelity

    c = json.loads(path.read_text(encoding="utf-8"))
    t1, t2 = c["t1_us"], min(c["t2_us"], 2 * c["t1_us"])
    g1, g2 = c["sx_ns"] / 1000, c["two_qubit_ns"] / 1000

    def thermal(t_us: float, n: int) -> float:
        err = thermal_relaxation_error(t1, t2, t_us)
        return 1 - average_gate_fidelity((err.expand(err) if n == 2 else err).to_quantumchannel())

    return NoisePreset(
        name="calibrated", label=f"Calibrated: {c['device']} ({c['taken_utc'][:10]})",
        p1=round(max(c["sx_error"] - thermal(g1, 1), 0.0) * 2, 7),
        p2=round(max(c["two_qubit_error"] - thermal(g2, 2), 0.0) * 4 / 3, 7),
        readout_p01=round(c["readout_p01"], 6), readout_p10=round(c["readout_p10"], 6),
        t1_us=round(t1, 2), t2_us=round(t2, 2), gate_1q_us=g1, gate_2q_us=g2,
    )


if (_calibrated := calibrated_preset()) is not None:
    PRESETS["calibrated"] = _calibrated


def get_preset(name: str) -> NoisePreset:
    """Look up a preset by name, with a readable error."""
    try:
        return PRESETS[name]
    except KeyError:
        raise ValueError(f"unknown noise preset '{name}'; choose one of {', '.join(PRESETS)}") from None


def gate_errors(preset: NoisePreset) -> dict[int, QuantumError] | None:
    """The error applied after every 1-, 2- and 3-qubit gate, keyed by gate size (None if noiseless)."""
    if preset.p1 == 0 and preset.p2 == 0 and preset.t1_us is None:
        return None
    one_q = depolarizing_error(preset.p1, 1)
    two_q = depolarizing_error(preset.p2, 2)
    three_q = depolarizing_error(toffoli_error(preset), 3)
    if preset.t1_us is not None and preset.t2_us is not None:
        r1 = thermal_relaxation_error(preset.t1_us, preset.t2_us, preset.gate_1q_us)
        r2 = thermal_relaxation_error(preset.t1_us, preset.t2_us, preset.gate_2q_us)
        r3 = thermal_relaxation_error(preset.t1_us, preset.t2_us, TOFFOLI_CNOTS * preset.gate_2q_us)
        one_q = one_q.compose(r1)
        two_q = two_q.compose(r2.expand(r2))
        three_q = three_q.compose(r3.expand(r3).expand(r3))
    return {1: one_q, 2: two_q, 3: three_q}


def build_gate_noise_model(preset: NoisePreset) -> NoiseModel | None:
    """Gate noise only (depolarizing + thermal relaxation), no readout error.

    The verifier applies readout error separately and exactly.
    """
    errors = gate_errors(preset)
    if errors is None:
        return None
    noise = NoiseModel()
    noise.add_all_qubit_quantum_error(errors[1], ONE_QUBIT_GATES)
    noise.add_all_qubit_quantum_error(errors[2], TWO_QUBIT_GATES)
    noise.add_all_qubit_quantum_error(errors[3], THREE_QUBIT_GATES)
    return noise


def toffoli_error(preset: NoisePreset) -> float:
    """Depolarizing probability of one Toffoli: six CNOTs' worth of two-qubit error."""
    return 1 - (1 - preset.p2) ** TOFFOLI_CNOTS


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
