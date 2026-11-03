# Real hardware check

4 circuits run on **ibm_fez** (IBM Quantum, job `dbjkc0pkdqps7390opdg`, 4096 shots, 2026-11-01T14:01:15+00:00) with `scripts/hardware_check.py`, compared with the ideal odds, Q-Canvas's generic realistic preset and a digital twin built from the device's own calibration (Qiskit Aer, NoiseModel.from_backend). Lower total variation distance (TVD) is closer to what the chip did.

| Circuit | Two-qubit gates on the chip | TVD to ideal | TVD to generic preset | TVD to digital twin | TVD to calibrated preset | Shot noise alone |
| --- | --- | --- | --- | --- | --- | --- |
| Bell pair | 1 | 0.027 | 0.046 | 0.021 | 0.013 | 0.008 |
| GHZ-3 | 2 | 0.041 | 0.079 | 0.031 | 0.027 | 0.009 |
| Bernstein-Vazirani (secret 101) | 2 | 0.048 | 0.079 | 0.038 | 0.018 | 0.004 |
| Grover search (2 qubits) | 2 | 0.051 | 0.067 | 0.037 | 0.013 | 0.003 |

The calibrated preset is Q-Canvas's own noise model with the medians of ibm_fez's calibration (snapshot 2026-11-01T18:34:00+00:00, calibrated 2026-11-01T23:46:12+05:30; scripts/calibration_snapshot.py), taken after the run, so it describes the device a few hours later; the stored counts were rescored with `--rescore`. "Shot noise alone" is the distance a perfect prediction would still show at this many shots.
