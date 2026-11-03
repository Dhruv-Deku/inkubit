"""Exact outcome distributions for circuits with mid-circuit measurement and feed-forward.

The deferred-measurement principle makes them exact without sampling. Each mid-circuit measurement copies the
measured qubit's Z value onto a fresh record qubit (the classical bit), a gate conditioned on bits becomes the
same gate controlled by their records, a reset swaps the qubit's state onto a fresh qubit that is never read again
(exactly "forget it and start from 0"), and the records are read at the end along with the terminal measurements. Under
noise the record passes through the readout channel, because the chip acts on the bit it read, flips included, and a
conditioned gate's error channel acts only in the branch where the gate fires. The channels are the verifier's own
(``insights.circuit.gate_channels``, checked against Aer in a test), so a sampled run of the generated ``if_test`` code
and this prediction answer the same question independently.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import CXGate, SwapGate
from qiskit.quantum_info import DensityMatrix, Kraus, SuperOp, Statevector

from inkubit.sim.noise import NoisePreset
from inkubit.spec.models import CircuitSpec

_PROJ = (np.diag([1.0, 0.0]), np.diag([0.0, 1.0]))


def record_count(spec: CircuitSpec) -> int:
    """Qubits the model adds: a record per qubit measured mid-circuit, a fresh qubit per reset."""
    return sum(len(op.targets) for op in spec.operations if op.gate in ("MEASURE", "RESET"))


@lru_cache(maxsize=16)
def _readout(p01: float, p10: float) -> Kraus:
    """The bit the chip reads: 0 becomes 1 with p01, 1 becomes 0 with p10."""
    return Kraus([
        np.sqrt(1 - p01) * np.array([[1, 0], [0, 0]]), np.sqrt(p01) * np.array([[0, 0], [1, 0]]),
        np.sqrt(1 - p10) * np.array([[0, 0], [0, 1]]), np.sqrt(p10) * np.array([[0, 1], [0, 0]]),
    ])


def _branch(channel: SuperOp, values: list[int]) -> Kraus:
    """A gate's error channel on its qubits, applied only where the records (the qubits after them, first listed
    lowest) read ``values``; elsewhere nothing happens."""
    ks = Kraus(channel).data
    fire = np.array([[1.0]])
    for v in values:  # the first record is the lowest of the record qubits, so it is the rightmost factor
        fire = np.kron(_PROJ[v], fire)
    idle = np.eye(fire.shape[0]) - fire
    return Kraus([np.kron(fire, k) for k in ks] + [np.kron(idle, np.eye(ks[0].shape[0]))])


def distribution(spec: CircuitSpec, preset: NoisePreset | None) -> dict[str, float]:
    """Exact outcome probabilities of a feed-forward circuit, keyed like Qiskit counts (None or ideal: no noise)."""
    from inkubit.verify.expected import _to_clbit_keys, append_operation, apply_readout_error

    n = spec.num_qubits
    total = n + record_count(spec)
    noisy = preset is not None and not preset.is_ideal
    channels: dict[int, SuperOp] = {}
    if noisy:
        from inkubit.insights.circuit import gate_channels

        channels = gate_channels(preset)
    state: DensityMatrix | Statevector = DensityMatrix.from_label("0" * total) if noisy else Statevector.from_label("0" * total)
    record: dict[int, int] = {}  # classical bit -> its record qubit
    pairs: list[tuple[int, int]] = []
    nxt = n
    for op in spec.operations:
        if op.gate == "BARRIER":
            continue
        if op.gate == "RESET":  # the state leaves on a fresh qubit nobody reads; the qubit starts again from 0
            for q in op.targets:
                state = state.evolve(SwapGate(), qargs=[q, nxt])
                nxt += 1
            continue
        if op.gate == "MEASURE":
            for q, c in zip(op.targets, op.clbits):
                state = state.evolve(CXGate(), qargs=[q, nxt])
                if noisy and (preset.readout_p01 or preset.readout_p10):
                    state = state.evolve(_readout(preset.readout_p01, preset.readout_p10), qargs=[nxt])
                record[c] = nxt
                pairs.append((nxt, c))
                nxt += 1
            continue
        qc = QuantumCircuit(total)
        cond = op.conditional
        append_operation(qc, op.model_copy(update={"conditional": None}))
        for inst in qc.data:
            qargs = [qc.find_bit(b).index for b in inst.qubits]
            k = len(qargs)
            if cond is None:
                state = state.evolve(inst.operation, qargs=qargs)
                if k in channels:
                    state = state.evolve(channels[k], qargs=qargs)
            else:
                pairs_cv = cond.pairs()
                recs = [record[c] for c, _ in pairs_cv]
                state = state.evolve(inst.operation.control(len(recs), ctrl_state=cond.value), qargs=[*recs, *qargs])
                if k in channels:
                    state = state.evolve(_branch(channels[k], [v for _, v in pairs_cv]), qargs=[*qargs, *recs])
    pairs += [(m.qubit, m.clbit) for m in spec.measurements]
    dist = _to_clbit_keys(state.probabilities_dict(qargs=[q for q, _ in pairs]), spec, pairs)
    if noisy:  # records already carry their readout flips; the terminal measurements get theirs here
        dist = apply_readout_error(dist, spec, preset.readout_p01, preset.readout_p10,
                                   clbits=[m.clbit for m in spec.measurements])
    return dist
