# AI alone vs Q-Canvas

Muse Spark (`muse-spark-1.3`) was asked to predict each circuit's measured outcome odds on its own, the way a chat assistant answers: the circuit as data (no title or notes), no simulator, medium reasoning effort. Answers are scored against exact simulation by total variation distance (the share of probability in the wrong place): exact below 1%, close below 5%, wrong from 5%. Two sets: the textbook examples, which a model has seen many times, and new circuits no textbook contains (seeded random circuits of 3 to 5 qubits and the six-guest QAOA circuit), which is what a student's own sketch looks like to a model, and bigger new circuits of 6 to 8 qubits (all in superposition first, 4 qubits measured). Regenerate with `scripts/arena_bench.py`; run on 2026-10-31.

- **Textbook circuits**: exact on 13 of 13, close on 0, wrong on 0; on average 0.0% of the probability in the wrong place (over the answers given).
- **New circuits**: exact on 10 of 11, close on 0, wrong on 0, no usable answer on 1; on average 0.0% of the probability in the wrong place (over the answers given).
- **Bigger new circuits (6 to 8 qubits, 4 measured)**: exact on 3 of 6, close on 1, wrong on 1, no usable answer on 1; on average 8.9% of the probability in the wrong place (over the answers given).

| Set | Circuit | Qubits | Gates | Model alone | Off by | Impossible outcomes given | Real outcomes missed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| textbook | Bell pair | 2 | 2 | matched | 0.0% | 0 | 0 |
| textbook | GHZ-3 | 3 | 3 | matched | 0.0% | 0 | 0 |
| textbook | Superposition with a tilt | 2 | 2 | matched | 0.0% | 0 | 0 |
| textbook | Superdense coding (sends 11) | 2 | 6 | matched | 0.0% | 0 | 0 |
| textbook | Quantum AND (Toffoli) | 3 | 2 | matched | 0.0% | 0 | 0 |
| textbook | Deutsch-Jozsa (balanced) | 3 | 5 | matched | 0.0% | 0 | 0 |
| textbook | Bernstein-Vazirani (secret 101) | 4 | 5 | matched | 0.0% | 0 | 0 |
| textbook | Grover search (2 qubits) | 2 | 7 | matched | 0.0% | 0 | 0 |
| textbook | W state (one of three) | 3 | 7 | matched | 0.0% | 0 | 0 |
| textbook | Teleportation (deferred measurement) | 3 | 7 | matched | 0.0% | 0 | 0 |
| textbook | Bit-flip code (an error on q1) | 3 | 9 | matched | 0.0% | 0 | 0 |
| textbook | Phase estimation of T | 4 | 12 | matched | 0.0% | 0 | 0 |
| textbook | Shor: factor 15 with a = 7 | 7 | 28 | matched | 0.0% | 0 | 0 |
| new | New circuit 1 (3 qubits, 8 gates) | 3 | 8 | matched | 0.0% | 0 | 0 |
| new | New circuit 2 (4 qubits, 8 gates) | 4 | 8 | matched | 0.0% | 0 | 0 |
| new | New circuit 3 (5 qubits, 11 gates) | 5 | 11 | matched | 0.0% | 0 | 0 |
| new | New circuit 4 (3 qubits, 10 gates) | 3 | 10 | matched | 0.0% | 0 | 0 |
| new | New circuit 5 (4 qubits, 11 gates) | 4 | 11 | matched | 0.0% | 0 | 0 |
| new | New circuit 6 (5 qubits, 9 gates) | 5 | 9 | matched | 0.0% | 0 | 0 |
| new | New circuit 7 (3 qubits, 11 gates) | 3 | 11 | matched | 0.0% | 0 | 0 |
| new | New circuit 8 (4 qubits, 8 gates) | 4 | 8 | matched | 0.0% | 0 | 0 |
| new | New circuit 9 (5 qubits, 10 gates) | 5 | 10 | matched | 0.0% | 0 | 0 |
| new | New circuit 10 (3 qubits, 10 gates) | 3 | 10 | matched | 0.0% | 0 | 0 |
| new | QAOA: split the party (1 layer) | 6 | 31 | no answer | – | 0 | 0 |
| bigger | Bigger circuit 1 (6 qubits, 25 gates) | 6 | 25 | no answer | – | 0 | 0 |
| bigger | Bigger circuit 2 (6 qubits, 25 gates) | 6 | 25 | close | 1.4% | 0 | 0 |
| bigger | Bigger circuit 3 (7 qubits, 22 gates) | 7 | 22 | matched | 0.0% | 0 | 0 |
| bigger | Bigger circuit 4 (7 qubits, 20 gates) | 7 | 20 | wrong | 43.2% | 0 | 0 |
| bigger | Bigger circuit 5 (8 qubits, 26 gates) | 8 | 26 | matched | 0.0% | 0 | 0 |
| bigger | Bigger circuit 6 (8 qubits, 22 gates) | 8 | 22 | matched | 0.0% | 0 | 0 |

Q-Canvas never shows a model's answer unchecked: every run is compared with exact simulation, and in the planted-fault benchmark (docs/BENCHMARK.md) 55 of 55 runs ended correctly, including 9 of 9 faked results caught.
