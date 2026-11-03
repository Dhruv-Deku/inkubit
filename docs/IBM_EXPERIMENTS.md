# Experiments on a real IBM quantum computer

`scripts/ibm_experiments.py` on **ibm_fez** (job `dbk6mf1kdqps7391s3q0`, 63 circuits, 2026-11-02T10:57:31+00:00; calibration snapshot 2026-11-02T10:51:18+00:00). Raw counts, no readout correction.

## Placement: GHZ-5 on the advisor's best, median and worst qubits

The advisor scored 804 placements from the calibration snapshot.

| Placement | Physical qubits | Advisor score | Measured GHZ fidelity | Twin |
| --- | --- | --- | --- | --- |
| best | 137, 147, 146, 145, 144 | 0.965 | 0.894 ± 0.003 | 0.948 |
| median | 37, 25, 26, 27, 17 | 0.899 | 0.814 ± 0.004 | 0.851 |
| worst | 147, 148, 149, 150, 151 | 0.567 | 0.285 ± 0.006 | 0.432 |

## Teleportation with mid-circuit measurement and feed-forward (qubits 110, 109, 118)

| State | Fidelity with feed-forward | Without corrections |
| --- | --- | --- |
| |0⟩ | 0.921 ± 0.006 | 0.502 ± 0.011 |
| |1⟩ | 0.933 ± 0.006 | 0.499 ± 0.011 |
| |+⟩ | 0.938 ± 0.005 | 0.502 ± 0.011 |
| |−⟩ | 0.947 ± 0.005 | 0.503 ± 0.011 |
| |+i⟩ | 0.906 ± 0.006 | 0.487 ± 0.011 |
| |−i⟩ | 0.902 ± 0.007 | 0.500 ± 0.011 |

Average over the six axis states (equal to the average over all states): **0.924 ± 0.002** with feed-forward, 0.499 ± 0.005 without; the best classical scheme reaches 0.667.
