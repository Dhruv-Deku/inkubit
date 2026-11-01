# Mission control benchmark

30 varied problems run live with Muse Spark planning and reporting (`scripts/mission_bench.py`). Three are hard on purpose: a number the Shor tool cannot factor (21), a problem with no quantum angle (sorting), and an ambiguous one.

| Measure | Result |
| --- | --- |
| Missions that finished with a report | 30 of 30 |
| Plans written by Muse Spark (not the offline stand-in) | 30 of 30 |
| Steps run | 68 |
| Steps verified (including repaired ones) | 68 of 68 |
| Steps repaired by the model after an error | 1 |
| Steps flagged by a physics check | 0 |
| Steps that failed or were skipped | 0 |
| Numbers in the reports traced to a tool result | 204 of 209 |
| Time per mission | median 15 s, slowest 26 s |

The five untraced numbers are the model rounding a tool's value (2,089 written as 2,090, twice in two missions) or
writing 6.4e-18 as "6.4 × 10^-18"; the tracer flags a number unless it matches a tool result at the precision
written, rather than guess. The hard cases were answered honestly: "Factor 21" ran the Shor tool and reported that
it factored 15, not 21; "sort a million numbers" reported that quantum search does not sort.

## Every mission

| # | Mission | Steps | Verified | Repaired | Flagged | Failed | Traced | Seconds | Headline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Compare the hydrogen molecule at 0.6, 1.0 and 2.0 angstrom and say where the classical shortcut fails. | 3 | 3 | 0 | 0 | 0 | 9/9 | 24.9 | The classical shortcut fails at 2.0 angstrom where stretching breaks the single-reference picture. |
| 2 | Is a spy listening to 40% of the photons caught? And one listening to 10%? | 2 | 2 | 0 | 0 | 0 | 8/10 | 15.1 | Neither the 40% listener nor the 10% listener was caught. |
| 3 | Factor 15 with Shor's algorithm using the bases 2, 7 and 13 and compare how often each run succeeds on noisy hardware. | 3 | 3 | 0 | 0 | 0 | 6/6 | 20.7 | Bases 2, 7 and 13 all broke 15 into 3 and 5. |
| 4 | Plan a 300 km fiber link and a 1,500 km satellite link; which gives more secret key per second? | 2 | 2 | 0 | 0 | 0 | 7/7 | 10.5 | The 300 km fiber link delivers more secret key per second than the satellite link. |
| 5 | Make a 5-qubit GHZ state, find a shorter equivalent if there is one, and check how well it survives realistic noise. | 4 | 4 | 0 | 0 | 0 | 8/8 | 15.8 | Made a 5-qubit GHZ state that keeps about 0.813 fidelity under realistic noise with no shorter equivalent. |
| 6 | Run 3-qubit Grover search and the swap test; which one is more fragile under realistic noise? | 4 | 4 | 0 | 0 | 0 | 6/6 | 16.2 | Grover search is more fragile under realistic noise than the swap test. |
| 7 | Seven friends with feuds Ann-Ben, Ben-Cat, Cat-Dan, Dan-Eve, Eve-Fay, Fay-Gus, Gus-Ann: split them over two tables and say how well QAOA does. | 1 | 1 | 0 | 0 | 0 | 7/7 | 20.3 | QAOA finds the ideal two-table seating that separates 6 of the 7 feuds. |
| 8 | When does error correction start to help, for today's gates and for gates ten times better? | 2 | 2 | 0 | 0 | 0 | 4/4 | 9.1 | Error correction helps above about 10.8% error with today's gates and above about 0.871% with ten times better gates. |
| 9 | Turn the state (/00⟩ + /11⟩)/√2 into a circuit and check how it survives noise with the ML verifier. | 2 | 2 | 0 | 0 | 0 | 5/5 | 13.2 | The Bell state was turned into a short circuit and survived noise near predicted fidelity. |
| 10 | Run Simon's algorithm and Bernstein-Vazirani and tell me whether their answers survive realistic noise. | 4 | 4 | 0 | 0 | 0 | 9/9 | 16.0 | Both Simon's and Bernstein-Vazirani still give the right answer under realistic noise. |
| 11 | How does the energy of H2 at its equilibrium bond length compare between Hartree-Fock, the exact answer and noisy VQE with mitigation? | 1 | 1 | 0 | 0 | 0 | 10/10 | 13.9 | Mitigated noisy VQE recovers near-exact H2 energy while Hartree-Fock and raw VQE sit too high. |
| 12 | A bank wants to link two data centres 80 km apart with quantum keys. Plan the link and check an eavesdropper on 25% of photons. | 2 | 2 | 0 | 0 | 0 | 10/10 | 12.4 | An 80-km fiber link can supply quantum keys and tolerate 25% eavesdropping. |
| 13 | Run the quantum Fourier transform period-finding example and the phase estimation example; do they still give the right answer with noise? | 2 | 2 | 0 | 0 | 0 | 5/5 | 14.5 | Yes, both the period-finding and phase-estimation examples still give the right answer under realistic noise. |
| 14 | Build a W state on 3 qubits, then check whether a shorter circuit exists and how robust it is. | 3 | 3 | 0 | 0 | 0 | 5/5 | 19.2 | Built a 3-qubit W state that is already minimal and retains about 0.898 fidelity under realistic noise. |
| 15 | Teleport a qubit and swap entanglement between two pairs; which protocol loses more to noise? | 2 | 2 | 0 | 0 | 0 | 6/6 | 16.8 | Entanglement swapping loses more to noise than teleportation. |
| 16 | Schedule four exams, Maths, Art, Music and Biology, with clashes Maths-Art, Art-Music, Music-Biology, Biology-Maths, over two days. | 1 | 1 | 0 | 0 | 0 | 5/5 | 15.3 | Schedule Maths and Music on one day and Art and Biology on the other to avoid all clashes. |
| 17 | What does the circuit h q[0]; cx q[0],q[1]; cx q[1],q[2]; measure all produce, and how entangled is it? | 1 | 1 | 0 | 0 | 0 | 8/8 | 25.3 | The 3-operation circuit creates a GHZ state on qubits 0, 1 and 2 that yields only 000 or 111. |
| 18 | Plan a quantum network link of 2,000 km by satellite and of 2,000 km of fiber with 3 repeaters. | 2 | 2 | 0 | 0 | 0 | 9/9 | 15.0 | For 2,000 km, the satellite design delivers usable keys after upgrades while the fiber design with 3 repeaters delivers none. |
| 19 | Compare a half adder circuit and a Toffoli AND circuit under realistic noise. | 4 | 4 | 0 | 0 | 0 | 6/6 | 13.9 | The Toffoli AND held up better than the larger half adder under the same realistic noise. |
| 20 | Simulate the 3-spin quantum magnet example and tell me how much the noise changes its outcome odds. | 2 | 2 | 0 | 0 | 0 | 9/9 | 15.3 | Noise only modestly shifts the 3-spin magnet odds, keeping overlap near 97.3%. |
| 21 | Is the Deutsch-Jozsa example still decisive on realistic hardware? Check it with the ML verifier too. | 2 | 2 | 0 | 0 | 0 | 6/6 | 16.3 | Yes, the Deutsch-Jozsa balanced example stays decisive on realistic hardware and the ML verifier agrees. |
| 22 | Which is worse for H2 at 2.5 angstrom: the Hartree-Fock error or the raw noisy VQE error? | 1 | 1 | 0 | 0 | 0 | 11/11 | 14.8 | For H2 at 2.5 angstrom, the Hartree-Fock error is worse than the raw noisy VQE error. |
| 23 | Check BB84 with no eavesdropper and with one on every photon; what happens to the key? | 2 | 2 | 0 | 0 | 0 | 6/8 | 13.9 | Without eavesdropping a usable secret key was produced, while eavesdropping every photon caused the key to be aborted. |
| 24 | For a 600 km fiber link, what is the weakest part and the best fix? | 1 | 1 | 0 | 0 | 0 | 4/5 | 13.5 | The 600 km fiber link produces no usable key and no fix beats the current design. |
| 25 | Run Grover on 2 qubits and on 3 qubits and compare their success under noise. | 2 | 2 | 0 | 0 | 0 | 5/5 | 15.0 | The 2-qubit Grover resisted noise far better than the 3-qubit Grover. |
| 26 | Explain how the bit-flip code example corrects an error and whether it survives noise. | 3 | 3 | 0 | 0 | 0 | 8/8 | 18.0 | The bit-flip code fixes a flipped qubit and survives realistic noise with high fidelity. |
| 27 | Translate the Quil program H 0; CNOT 0 1 into a circuit and simulate it. | 2 | 2 | 1 | 0 | 0 | 8/8 | 26.4 | The 2-operation Quil program entangles qubits 0 and 1 into equal 00 and 11 outcomes. |
| 28 | Factor 21 with Shor's algorithm. | 2 | 2 | 0 | 0 | 0 | 6/6 | 15.0 | The demonstration factored 15 into 3 and 5, not 21. |
| 29 | Use a quantum computer to sort a list of a million numbers faster. | 2 | 2 | 0 | 0 | 0 | 3/3 | 22.4 | Quantum search finds a marked item in fewer queries, but it does not sort a list. |
| 30 | Do something interesting with entanglement. | 4 | 4 | 0 | 0 | 0 | 5/5 | 24.0 | We created entanglement and used it to send messages, teleport a state, and link distant qubits. |
