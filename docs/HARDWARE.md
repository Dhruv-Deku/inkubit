# Real hardware check

4 circuits run on **ibm_fez** (IBM Quantum, job `dbjkc0pkdqps7390opdg`, 4096 shots, 2026-11-01T14:01:15+00:00) with `scripts/hardware_check.py`, compared with the ideal odds, Q-Canvas's generic realistic preset and a digital twin built from the device's own calibration (Qiskit Aer, NoiseModel.from_backend). Lower total variation distance (TVD) is closer to what the chip did.

| Circuit | Two-qubit gates on the chip | TVD to ideal | TVD to generic preset | TVD to digital twin |
| --- | --- | --- | --- | --- |
| Bell pair | 1 | 0.027 | 0.046 | 0.021 |
| GHZ-3 | 2 | 0.041 | 0.079 | 0.031 |
| Bernstein-Vazirani (secret 101) | 2 | 0.048 | 0.079 | 0.038 |
| Grover search (2 qubits) | 2 | 0.051 | 0.067 | 0.037 |
