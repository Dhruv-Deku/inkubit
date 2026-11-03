# An AI scientist that learns under proof

Muse Spark (`muse-spark-1.3`) proposed CNOT layouts for three target states over 5 rounds of up to four layouts each (`scripts/learning_bench.py`, `backend/inkubit/learning.py`). The exact optimiser judged every layout and Qiskit proved every one that reached the target. With feedback, each round's prompt listed every earlier layout and its verdict; without feedback, the same model was asked afresh; random wiring used the same lengths as the feedback run with random allowed pairs.

Fewest proven CNOTs after each round (– means none proven yet):

## W state on 4 qubits

Lower bound from the state's structure: 3 CNOTs.

| Condition | Round 1 | Round 2 | Round 3 | Round 4 | Round 5 | Layouts that reached the target |
| --- | --- | --- | --- | --- | --- | --- |
| With feedback | 6 | 5 | 5 | 5 | 5 | 10% |
| No feedback | 6 | 6 | 6 | 6 | 6 | 10% |
| Random wiring | – | – | – | – | – | 0% |

## Dicke state |D(4,2)⟩

Lower bound from the state's structure: 3 CNOTs.

| Condition | Round 1 | Round 2 | Round 3 | Round 4 | Round 5 | Layouts that reached the target |
| --- | --- | --- | --- | --- | --- | --- |
| With feedback | 6 | 6 | 5 | 5 | 5 | 10% |
| No feedback | 6 | 6 | 6 | 6 | 6 | 25% |
| Random wiring | – | – | – | – | – | 0% |

## W state on 5 qubits in a line

Lower bound from the state's structure: 4 CNOTs.

| Condition | Round 1 | Round 2 | Round 3 | Round 4 | Round 5 | Layouts that reached the target |
| --- | --- | --- | --- | --- | --- | --- |
| With feedback | 8 | 7 | 7 | 7 | 7 | 15% |
| No feedback | 7 | 7 | 7 | 7 | 7 | 35% |
| Random wiring | – | – | – | – | – | 0% |
