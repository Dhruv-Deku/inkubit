# The proof sheet over the gallery

`scripts/proofsheet_bench.py` ran the proof sheet (11 checks of 9 kinds, `backend/qcanvas/proofsheet.py`) on all 28 gallery circuits in 9 categories, 2026-11-02: **299 passed, 0 failed**, 1 skipped with the reason, 8 notes (the ML verifier's interval missing the exact value: a note about the model, not the circuit).

| Check | Kind | Guards against | Passed | Failed | Skipped | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| The circuit is well formed | Specification | a gate on a qubit that does not exist, a measurement in the middle, a typo in a gate name | 28 | 0 | 0 | 0 |
| The generated script runs and verifies | Generated code | a code generator that writes a different circuit than the spec | 28 | 0 | 0 | 0 |
| Two ideal simulators agree | Independent engines | a bug in one simulator | 28 | 0 | 0 | 0 |
| Two noisy simulators agree | Independent engines | a noise model built differently in two places | 27 | 0 | 1 | 0 |
| The noisy state is a physical state | Physics | a noise channel that is not trace-preserving or not completely positive | 28 | 0 | 0 | 0 |
| Qiskit's compiled circuits are proven equal | Compilation | a compiler bug, or a routing permutation applied the wrong way round | 28 | 0 | 0 | 0 |
| Exports read back to the same circuit | Languages | an export that drops a gate, flips a control or loses an angle | 28 | 0 | 0 | 0 |
| Sampled shots match the exact odds | Statistics | a sampler or a readout model that is subtly biased | 28 | 0 | 0 | 0 |
| Renaming the qubits changes nothing | Metamorphic tests | a simulator or spec reader that depends on qubit order | 28 | 0 | 0 | 0 |
| Gates that cancel change nothing | Metamorphic tests | a gate implemented with the wrong matrix or the wrong convention | 28 | 0 | 0 | 0 |
| The ML verifier's interval holds the exact value | Learned screen | nothing about the circuit: it grades the fast model against the exact one | 20 | 0 | 0 | 8 |

| Circuit | Category | Qubits | Gates | Passed | Failed | Skipped | Notes | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Superposition with a tilt | Basics | 2 | 2 | 11 | 0 | 0 | 0 | 9.5 |
| Bell pair | Basics | 2 | 2 | 11 | 0 | 0 | 0 | 9.0 |
| GHZ-3 | Basics | 3 | 3 | 11 | 0 | 0 | 0 | 8.5 |
| W state (one of three) | Entanglement & communication | 3 | 7 | 11 | 0 | 0 | 0 | 7.9 |
| Superdense coding (sends 11) | Entanglement & communication | 2 | 6 | 11 | 0 | 0 | 0 | 7.5 |
| Teleportation (deferred measurement) | Entanglement & communication | 3 | 7 | 11 | 0 | 0 | 0 | 8.8 |
| Entanglement swapping | Entanglement & communication | 4 | 10 | 10 | 0 | 0 | 1 | 7.7 |
| Swap test: how alike are two states? | Entanglement & communication | 3 | 6 | 11 | 0 | 0 | 0 | 7.9 |
| The CHSH game | Nonlocal games | 4 | 11 | 11 | 0 | 0 | 0 | 7.8 |
| The GHZ game (Mermin) | Nonlocal games | 6 | 10 | 11 | 0 | 0 | 0 | 7.9 |
| Deutsch-Jozsa (balanced) | Oracles & hidden structure | 3 | 5 | 11 | 0 | 0 | 0 | 7.7 |
| Bernstein-Vazirani (secret 101) | Oracles & hidden structure | 4 | 5 | 11 | 0 | 0 | 0 | 7.5 |
| Simon's algorithm (secret 11) | Oracles & hidden structure | 3 | 4 | 11 | 0 | 0 | 0 | 7.6 |
| Hidden shift (bent function, s = 1011) | Oracles & hidden structure | 4 | 13 | 11 | 0 | 0 | 0 | 7.2 |
| Grover search (2 qubits) | Search & counting | 2 | 7 | 11 | 0 | 0 | 0 | 7.5 |
| Grover search (3 qubits, 2 rounds) | Search & counting | 3 | 25 | 10 | 0 | 0 | 1 | 8.7 |
| Grover search with two marked items | Search & counting | 3 | 18 | 10 | 0 | 0 | 1 | 9.2 |
| Quantum counting (2 marked of 4) | Search & counting | 5 | 269 | 11 | 0 | 0 | 0 | 8.6 |
| Phase estimation of T | Fourier & phase | 4 | 12 | 10 | 0 | 0 | 1 | 7.8 |
| Quantum Fourier transform finds a period | Fourier & phase | 3 | 8 | 11 | 0 | 0 | 0 | 7.8 |
| Shor: factor 15 with a = 7 | Fourier & phase | 7 | 28 | 10 | 0 | 0 | 1 | 8.5 |
| Quantum AND (Toffoli) | Arithmetic & logic | 3 | 2 | 10 | 0 | 0 | 1 | 8.3 |
| Quantum half adder | Arithmetic & logic | 4 | 4 | 11 | 0 | 0 | 0 | 7.9 |
| Draper adder: 5 + 6 in Fourier space | Arithmetic & logic | 7 | 33 | 10 | 0 | 0 | 1 | 7.6 |
| HHL: solve a 2x2 linear system | Linear algebra & simulation | 4 | 75 | 11 | 0 | 0 | 0 | 7.5 |
| Simulating a quantum magnet (Trotter) | Linear algebra & simulation | 3 | 14 | 11 | 0 | 0 | 0 | 7.4 |
| Bit-flip code (an error on q1) | Error correction | 3 | 9 | 11 | 0 | 0 | 0 | 8.2 |
| Shor's 9-qubit code corrects a Y error | Error correction | 9 | 26 | 9 | 0 | 1 | 1 | 8.7 |
