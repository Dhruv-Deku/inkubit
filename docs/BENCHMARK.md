# Planted-fault benchmark

Every example circuit, run under the `realistic` noise preset, once clean and once with each fault that can be planted in it. Offline: template code and the rule-based repairer, so this measures the agent loop and the independent verifier, not a language model. Regenerate with `scripts/benchmark.py`.

**55 of 55 runs ended correctly**: clean runs and repairable faults verified, fake results caught. Repairable faults fixed: 37 of 37. Fake results caught: 9 of 9. Wall time 92 s.

| Circuit | clean | wrong_import | missing_measurement | wrong_qubit_index | swapped_control_target | missing_cnot | fake_result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Bell pair | ✓ (1) | ✓ (2) | ✓ (2) | ✓ (2) | ✓ (2) | ✓ (2) | caught |
| Bernstein-Vazirani (secret 101) | ✓ (1) | ✓ (2) | ✓ (2) | ✓ (2) | ✓ (2) | ✓ (2) | caught |
| Deutsch-Jozsa (balanced) | ✓ (1) | ✓ (2) | ✓ (2) | ✓ (2) | ✓ (2) | ✓ (2) | caught |
| GHZ-3 | ✓ (1) | ✓ (2) | ✓ (2) | ✓ (2) | ✓ (2) | ✓ (2) | caught |
| Grover search (2 qubits) | ✓ (1) | ✓ (2) | ✓ (2) | ✓ (2) | – | – | caught |
| Phase estimation of T | ✓ (1) | ✓ (2) | ✓ (2) | ✓ (2) | – | – | caught |
| Superdense coding (sends 11) | ✓ (1) | ✓ (2) | ✓ (2) | ✓ (2) | ✓ (2) | ✓ (2) | caught |
| Superposition with a tilt | ✓ (1) | ✓ (2) | ✓ (2) | ✓ (2) | – | – | caught |
| Quantum AND (Toffoli) | ✓ (1) | ✓ (2) | ✓ (2) | ✓ (2) | – | – | caught |

✓ (n) = verified after n attempts; caught = the verifier refused a faked result; – = the fault cannot be planted in this circuit.
