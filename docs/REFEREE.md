# The AI referee

Muse Spark (`muse-spark-1.3`) made three checkable claims about each of 8 circuits no textbook contains; Muse Wonder (`muse-wonder-1.0`) agreed with or disputed each; Muse Spark then stood by or conceded each disputed claim. Exact simulation graded every position (`scripts/referee_bench.py`).

| Measure | Result |
| --- | --- |
| Muse Spark's claims right as first stated | 17 of 24 |
| Answers right after the debate | 19 of 24 |
| Wrong claims Muse Wonder caught with the right answer | 4 of 7 |
| Right claims Muse Wonder disputed (false alarms) | 5 |
| Right claims Muse Spark was talked out of | 2 |

| Circuit | Claim | Truth | Muse Wonder | Final | Right at first | Right after |
| --- | --- | --- | --- | --- | --- | --- |
| Bigger circuit 1 | most likely: 0100 | most likely: 0001, 0011, 0100, 0110, 1001, 1011, 1100, 1110 (0.0669) | agrees | most likely: 0100 | yes | yes |
| Bigger circuit 1 | P(0100) = 0.098 | P(0100) = 0.0669 | disputes: P(0100) = 0.067 | P(0100) = 0.067 | no | yes |
| Bigger circuit 1 | qubits 1, 2 entangled | qubits 1 and 2 are not entangled (negativity 0.0000) | agrees | qubits 1, 2 entangled | no | no |
| Bigger circuit 2 | most likely: 0111 | most likely: 1000 (0.1942) | disputes: most likely: 1000 | most likely: 0111 | no | no |
| Bigger circuit 2 | P(0111) = 0.132 | P(0111) = 0.1154 | disputes: P(0111) = 0.119 | P(0111) = 0.132 | yes | yes |
| Bigger circuit 2 | qubits 2, 3 entangled | qubits 2 and 3 are not entangled (negativity 0.0000) | agrees | qubits 2, 3 entangled | no | no |
| Bigger circuit 3 | most likely: 0000 | most likely: 0000, 0001, 0010, 0011, 0100, 0101, 0110, 0111, 1000, 1001, 1010, 1011, 1100, 1101, 1110, 1111 (0.0625) | disputes: most likely: 0000 | most likely: 0000 | yes | yes |
| Bigger circuit 3 | P(0010) = 0.0625 | P(0010) = 0.0625 | agrees | P(0010) = 0.0625 | yes | yes |
| Bigger circuit 3 | qubits 0, 3 not entangled | qubits 0 and 3 are not entangled (negativity 0.0000) | agrees | qubits 0, 3 not entangled | yes | yes |
| Bigger circuit 4 | most likely: 1011 | most likely: 0010, 1010 (0.1709) | disputes: most likely: 0010,1010 | most likely: 0010,1010 | no | no |
| Bigger circuit 4 | P(1010) = 0.045 | P(1010) = 0.1709 | disputes: P(1010) = 0.1709 | P(1010) = 0.1709 | no | yes |
| Bigger circuit 4 | qubits 1, 2 entangled | qubits 1 and 2 are entangled (negativity 0.3770) | agrees | qubits 1, 2 entangled | yes | yes |
| Bigger circuit 5 | most likely: 0101 | most likely: 0010, 0011, 0100, 0101, 1010, 1011, 1100, 1101 (0.1205) | agrees | most likely: 0101 | yes | yes |
| Bigger circuit 5 | P(0101) = 0.12 | P(0101) = 0.1205 | agrees | P(0101) = 0.12 | yes | yes |
| Bigger circuit 5 | qubits 0, 2 not entangled | qubits 0 and 2 are not entangled (negativity 0.0000) | agrees | qubits 0, 2 not entangled | yes | yes |
| Bigger circuit 6 | most likely: 0000 | most likely: 0000, 0001, 0010, 0011, 0100, 0101, 0110, 0111, 1000, 1001, 1010, 1011, 1100, 1101, 1110, 1111 (0.0625) | disputes: most likely: 0000 | most likely: 0000 | yes | yes |
| Bigger circuit 6 | P(0100) = 0.065 | P(0100) = 0.0625 | disputes: P(0100) = 0.0625 | P(0100) = 0.065 | yes | yes |
| Bigger circuit 6 | qubits 1, 3 entangled | qubits 1 and 3 are not entangled (negativity 0.0000) | disputes: qubits 1, 3 not entangled | qubits 1, 3 entangled | no | no |
| New circuit 1 | most likely: 000 | most likely: 000, 010 (0.4825) | disputes: most likely: 000 | most likely: 000 | yes | yes |
| New circuit 1 | P(010) = 0.4825 | P(010) = 0.4825 | agrees | P(010) = 0.4825 | yes | yes |
| New circuit 1 | qubits 1, 2 not entangled | qubits 1 and 2 are not entangled (negativity 0.0000) | agrees | qubits 1, 2 not entangled | yes | yes |
| New circuit 2 | most likely: 0001 | most likely: 0001 (0.3320) | agrees | most likely: 0001 | yes | yes |
| New circuit 2 | P(1001) = 0.2591 | P(1001) = 0.2591 | agrees | P(1001) = 0.2591 | yes | yes |
| New circuit 2 | qubits 2, 3 not entangled | qubits 2 and 3 are not entangled (negativity 0.0000) | agrees | qubits 2, 3 not entangled | yes | yes |
