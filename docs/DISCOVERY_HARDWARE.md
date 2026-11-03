# AI-discovered circuits on a real quantum computer

The discovery lab's best proven circuit for each goal ran on **ibm_fez** (IBM Quantum, job `dbjpr9pffo6c73ba4adg`, 4096 shots per circuit, 23 circuits, 2026-11-01T20:16:31+00:00) next to the baselines it beat, with `scripts/discovery_hardware.py`. Raw counts, no readout correction. The digital twin is Qiskit Aer's noise model built from the device's calibration.

## GHZ on all 7 qubits of an IBM heavy-hex chip

Target 1/√2 (|0000000⟩ + |1111111⟩). Physical qubits [118, 109, 108, 110, 98, 111, 112], wired like a 7-qubit Falcon chip; every variant compiled onto them.

| Circuit | CNOTs in the lab | Two-qubit gates on the chip | Outcome fidelity (chip) | (twin) | GHZ fidelity (chip) | (twin) |
| --- | --- | --- | --- | --- | --- | --- |
| Muse Spark's layout #4 | 6 | 6 | 0.860 | 0.933 | 0.814 | 0.903 |
| Textbook circuit, compiled onto the wiring | 10 | 10 | 0.841 | 0.926 | 0.795 | 0.895 |
| Qiskit state preparation, optimisation level 3 | 197 | 197 | 0.341 | 0.623 | – | – |

## W state on 4 qubits

Target 1/2 (|0001⟩ + |0010⟩ + |0100⟩ + |1000⟩).

| Circuit | CNOTs in the lab | Two-qubit gates on the chip | Outcome fidelity (chip) | (twin) | GHZ fidelity (chip) | (twin) |
| --- | --- | --- | --- | --- | --- | --- |
| Search #1 | 5 | 8 | 0.903 | 0.958 | – | – |
| Qiskit state preparation, optimisation level 3 | 11 | 17 | 0.911 | 0.953 | – | – |

## Dicke state |D(4,2)⟩

Target 1/√6 (|0011⟩ + |0101⟩ + |0110⟩ + |1001⟩ + |1010⟩ + |1100⟩).

| Circuit | CNOTs in the lab | Two-qubit gates on the chip | Outcome fidelity (chip) | (twin) | GHZ fidelity (chip) | (twin) |
| --- | --- | --- | --- | --- | --- | --- |
| Search #3 | 5 | 8 | 0.902 | 0.962 | – | – |
| Qiskit state preparation, optimisation level 3 | 11 | 17 | 0.904 | 0.953 | – | – |
