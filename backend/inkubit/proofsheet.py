"""The proof sheet: every independent check Inkubit has, run on one circuit, grouped by the kind of mistake it catches.

A run is verified by one comparison (D8). The proof sheet asks more of a circuit and of Inkubit itself:

  Specification          the circuit is well formed (the spec validator)
  Independent engines    two ideal simulators (Qiskit's quantum_info and the Aer C++ statevector) agree; two noisy ones
                         (Inkubit's closed-form channels and Aer's density matrix) agree
  Physics                the noisy state is a valid density matrix: Hermitian, trace 1, no negative eigenvalue
  Compilation            the circuit compiled for three chip wirings is proven to be the same unitary (translation
                         validation of Qiskit's compiler, ancilla qubits included)
  Languages              exported to OpenQASM 2 and 3 and read back, it is still the same circuit
  Statistics             4,096 sampled shots pass the verifier's shot-noise bound and a G-test against the exact odds
  Generated code         Inkubit's own Qiskit script, run in the sandbox, verifies
  Metamorphic tests      relabelling the qubits, or inserting gate pairs that cancel, must not change the answer
  Learned screen         the ML verifier's interval holds the exact fidelity (a miss is a note about the model)

Thresholds are floating-point tolerances (1e-9 for exact quantities, 1e-6 between the two noisy engines), not physics.
Checks that would be too costly are skipped with the reason; nothing is skipped silently.
"""

from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel

from inkubit.spec import CircuitSpec

Status = Literal["pass", "fail", "skipped", "note"]
MAX_UNITARY_QUBITS = 9  # 512 x 512 operators
MAX_DENSITY_QUBITS = 10
SHOTS = 4096


class Check(BaseModel):
    id: str
    category: str
    title: str
    guards: str  # the mistake this check would catch
    status: Status
    detail: str
    ms: float = 0.0


class ProofSheet(BaseModel):
    title: str
    num_qubits: int
    gates: int
    noise: str
    checks: list[Check]
    passed: int
    failed: int
    skipped: int
    notes: int
    seconds: float
    summary: str


def _gap(a: dict[str, float], b: dict[str, float]) -> float:
    return max((abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in set(a) | set(b)), default=0.0)


def _padded(qc: Any, n: int) -> Any:
    from qiskit import QuantumCircuit

    full = QuantumCircuit(n)
    full.compose(qc, range(qc.num_qubits), inplace=True)
    return full


def _measured(spec: CircuitSpec) -> Any:
    from qiskit import QuantumCircuit

    from inkubit.verify.expected import build_reference_circuit

    qc = QuantumCircuit(spec.num_qubits, spec.num_clbits)
    qc.compose(build_reference_circuit(spec), inplace=True)
    for q, c in spec.measured_pairs():
        qc.measure(q, c)
    return qc


def _permuted(spec: CircuitSpec) -> CircuitSpec:
    """The same circuit with qubit q renamed n - 1 - q everywhere (gates and measurements); clbits unchanged."""
    from inkubit.spec import parse_spec

    n = spec.num_qubits
    raw = spec.model_dump(mode="json", by_alias=True, exclude_none=True)
    for op in raw["operations"]:
        op.pop("source", None)
        for key in ("targets", "controls"):
            if op.get(key):
                op[key] = [n - 1 - q for q in op[key]]
    for m in raw["measurements"]:
        m["qubit"] = n - 1 - m["qubit"]
    return parse_spec(raw)


def _padded_with_identities(spec: CircuitSpec) -> CircuitSpec:
    """Insert H·H on every qubit and X·X (and CX·CX on the first two qubits) before the circuit."""
    from inkubit.spec import parse_spec

    raw = spec.model_dump(mode="json", by_alias=True, exclude_none=True)
    extra: list[dict[str, Any]] = []
    for q in range(spec.num_qubits):
        extra += [{"gate": "H", "targets": [q]}, {"gate": "H", "targets": [q]}, {"gate": "X", "targets": [q]},
                  {"gate": "X", "targets": [q]}]
    if spec.num_qubits >= 2:
        extra += [{"gate": "CX", "controls": [0], "targets": [1]}] * 2
    raw["operations"] = extra + [{k: v for k, v in op.items() if k != "source"} for op in raw["operations"]]
    return parse_spec(raw)


def proof_sheet(spec: CircuitSpec, noise: str = "realistic", run_code: bool = True) -> ProofSheet:
    from qiskit.quantum_info import DensityMatrix, Operator, Statevector

    from inkubit.sim.noise import get_preset
    from inkubit.verify.expected import build_reference_circuit, ideal_distribution, noisy_distribution, noisy_state

    t_start = time.perf_counter()
    preset = get_preset(noise)
    n = spec.num_qubits
    checks: list[Check] = []
    pending: list[tuple[int, Any]] = []
    pool = ThreadPoolExecutor(max_workers=1)

    def timed(fn) -> tuple[str, str, float]:
        t0 = time.perf_counter()
        try:
            status, detail = fn()
        except Exception as err:  # noqa: BLE001 - a crash in a check is a failed check, shown as such
            status, detail = "fail", f"the check itself raised: {str(err)[:160]}"
        return status, detail, round((time.perf_counter() - t0) * 1e3, 1)

    def run(cid: str, category: str, title: str, guards: str, fn, background: bool = False) -> None:
        """Run a check now, or (background) in a thread while the others run: the sandbox mostly waits."""
        if background:
            pending.append((len(checks), pool.submit(timed, fn)))
            checks.append(Check(id=cid, category=category, title=title, guards=guards, status="skipped", detail=""))
            return
        status, detail, ms = timed(fn)
        checks.append(Check(id=cid, category=category, title=title, guards=guards, status=status, detail=detail, ms=ms))

    ideal = ideal_distribution(spec)
    ref = build_reference_circuit(spec)

    run("spec", "Specification", "The circuit is well formed",
        "a gate on a qubit that does not exist, a measurement in the middle, a typo in a gate name",
        lambda: ("pass", f"{n} qubits, {len(spec.operations)} gates, {len(spec.measured_pairs())} measured; "
                         "every field validated"))

    def generated_code():
        if not run_code:
            return "skipped", "not requested"
        from inkubit.codegen.template import generate_code
        from inkubit.sim.runner import run_code as run_script
        from inkubit.verify import verify_counts

        res = run_script(generate_code(spec, noise=noise))
        if not res.ok:
            return "fail", f"the script did not run: {res.stderr[-160:]}"
        v = verify_counts(spec, res.counts, noise)
        return ("pass" if v.passed else "fail"), (f"Inkubit's own Qiskit script ran in the sandbox and "
                                                  f"{'verified' if v.passed else 'failed'}: distance {v.metrics.tvd:.3f}")

    run("code", "Generated code", "The generated script runs and verifies",
        "a code generator that writes a different circuit than the spec", generated_code, background=True)

    def ideal_engines():
        from qiskit_aer import AerSimulator

        from inkubit.verify.expected import _to_clbit_keys

        qc = ref.copy()
        qc.save_statevector()
        sv = Statevector(AerSimulator(method="statevector").run(qc, shots=1).result().get_statevector())
        pairs = spec.measured_pairs()
        aer = _to_clbit_keys(sv.probabilities_dict(qargs=[q for q, _ in pairs]), spec, pairs)
        gap = _gap(ideal, aer)
        return ("pass" if gap < 1e-9 else "fail"), f"Qiskit quantum_info and Aer's C++ statevector agree to {gap:.1e}"

    run("ideal-engines", "Independent engines", "Two ideal simulators agree",
        "a bug in one simulator", ideal_engines)

    def noisy_engines():
        if preset.is_ideal:
            return "skipped", "the ideal preset has no noise to compare"
        if n > 8:
            return "skipped", "the closed-form channels are limited to 8 qubits"
        from inkubit.insights.circuit import noisy_distribution as channels

        gap = _gap(channels(spec, preset), noisy_distribution(spec, preset))
        return ("pass" if gap < 1e-6 else "fail"), f"closed-form channels and Aer's density matrix agree to {gap:.1e}"

    run("noisy-engines", "Independent engines", "Two noisy simulators agree",
        "a noise model built differently in two places", noisy_engines)

    def physical():
        if n > MAX_DENSITY_QUBITS:
            return "skipped", f"above {MAX_DENSITY_QUBITS} qubits"
        rho = noisy_state(spec, preset).data if not preset.is_ideal else DensityMatrix(Statevector(ref)).data
        trace = float(np.real(np.trace(rho)))
        herm = float(np.max(np.abs(rho - rho.conj().T)))
        low = float(np.min(np.linalg.eigvalsh((rho + rho.conj().T) / 2)))
        purity = float(np.real(np.trace(rho @ rho)))
        ok = abs(trace - 1) < 1e-6 and herm < 1e-9 and low > -1e-9 and purity <= 1 + 1e-6  # Aer sums in float64
        return ("pass" if ok else "fail"), (f"trace {trace:.12f}, Hermitian to {herm:.0e}, smallest eigenvalue "
                                            f"{low:.1e}, purity {purity:.4f}")

    run("physical", "Physics", "The noisy state is a physical state",
        "a noise channel that is not trace-preserving or not completely positive", physical)

    def compilation():
        if n > MAX_UNITARY_QUBITS:
            return "skipped", f"unitaries above {MAX_UNITARY_QUBITS} qubits are too large to compare"
        from qiskit import transpile
        from qiskit.transpiler import CouplingMap

        from inkubit.insights.circuit import BASIS, FALCON_7Q

        wirings = [("all-to-all", None), ("line", CouplingMap.from_line(n) if n > 1 else None)]
        if n <= 7:
            hexmap = CouplingMap(FALCON_7Q)
            hexmap.make_symmetric()
            wirings.append(("heavy-hex (7 qubits)", hexmap))
        proven = []
        for name, cmap in wirings:
            t = transpile(ref, coupling_map=cmap, basis_gates=BASIS, optimization_level=1, seed_transpiler=1234)
            if not Operator.from_circuit(t).equiv(Operator(_padded(ref, t.num_qubits))):
                return "fail", f"the circuit compiled for {name} wiring is a different unitary"
            proven.append(f"{name} ({t.count_ops().get('cx', 0)} CNOTs)")
        return "pass", "same unitary up to global phase, routing and spare qubits included: " + ", ".join(proven)

    run("compilation", "Compilation", "Qiskit's compiled circuits are proven equal",
        "a compiler bug, or a routing permutation applied the wrong way round", compilation)

    def languages():
        from qiskit import qasm2, qasm3

        from inkubit.insights.circuit import exports

        ex = exports(spec)
        back2, back3 = qasm2.loads(ex.qasm2), qasm3.loads(ex.qasm3)
        for name, qc in (("OpenQASM 2", back2), ("OpenQASM 3", back3)):
            qc = qc.remove_final_measurements(inplace=False)
            if n <= MAX_UNITARY_QUBITS:
                same = Operator(qc).equiv(Operator(ref))
            else:
                same = abs(abs(Statevector(qc).inner(Statevector(ref))) - 1) < 1e-9
            if not same:
                return "fail", f"{name} read back is a different circuit"
        how = "same unitary" if n <= MAX_UNITARY_QUBITS else "same state"
        return "pass", (f"exported to OpenQASM 2 and 3 and read back by Qiskit's strict parsers (the standard "
                        f"qelib1.inc and stdgates.inc only): {how} both times")

    run("languages", "Languages", "Exports read back to the same circuit",
        "an export that drops a gate, flips a control or loses an angle", languages)

    def statistics():
        from qiskit_aer import AerSimulator
        from scipy.stats import chi2

        from inkubit.sim.noise import build_noise_model
        from inkubit.verify import verify_counts

        sim = AerSimulator(noise_model=build_noise_model(preset)) if not preset.is_ideal else AerSimulator()
        counts = sim.run(_measured(spec), shots=SHOTS, seed_simulator=2026).result().get_counts()
        counts = {k.replace(" ", ""): v for k, v in counts.items()}
        verdict = verify_counts(spec, counts, noise)
        exp = verdict.expected
        support = [k for k in exp if exp[k] > 1e-12]
        g = 2 * sum(c * math.log(c / (SHOTS * exp[k])) for k, c in counts.items() if c and exp.get(k, 0) > 1e-12)
        df = max(len(support) - 1, 1)
        pval = float(chi2.sf(g, df))
        impossible = sum(c for k, c in counts.items() if exp.get(k, 0) <= 1e-12)
        ok = verdict.passed and pval > 1e-3 and impossible == 0
        return ("pass" if ok else "fail"), (f"{SHOTS:,} sampled shots: distance {verdict.metrics.tvd:.3f} within the "
                                            f"shot-noise bound {verdict.metrics.tvd_threshold:.3f}; G-test p = {pval:.2f} "
                                            f"over {len(support)} outcomes; no impossible outcome")

    run("statistics", "Statistics", "Sampled shots match the exact odds",
        "a sampler or a readout model that is subtly biased", statistics)

    def relabel():
        gap = _gap(ideal, ideal_distribution(_permuted(spec)))
        return ("pass" if gap < 1e-9 else "fail"), f"qubits renamed n−1−q throughout: the odds move by {gap:.1e}"

    run("relabel", "Metamorphic tests", "Renaming the qubits changes nothing",
        "a simulator or spec reader that depends on qubit order", relabel)

    def cancel():
        gap = _gap(ideal, ideal_distribution(_padded_with_identities(spec)))
        return ("pass" if gap < 1e-9 else "fail"), (f"H·H and X·X on every qubit{' and CX·CX' if n >= 2 else ''} "
                                                    f"inserted: the odds move by {gap:.1e}")

    run("cancel", "Metamorphic tests", "Gates that cancel change nothing",
        "a gate implemented with the wrong matrix or the wrong convention", cancel)

    def learned():
        if n > 10:
            return "skipped", "the ML verifier is checked up to 10 qubits"
        from inkubit.mlverify import predict
        from inkubit.verify.metrics import hellinger_fidelity

        p = predict(spec, 1.0, ideal)
        exact = hellinger_fidelity(ideal, noisy_distribution(spec, "realistic"))
        inside = p.low <= exact <= p.high
        return ("pass" if inside else "note"), (f"predicted {p.fidelity:.3f} ({p.low:.3f}–{p.high:.3f}) in "
                                                f"{p.microseconds:.0f} µs; exact {exact:.3f}"
                                                + ("" if inside else ": outside the interval, a note about the model, "
                                                   "not the circuit"))

    run("learned", "Learned screen", "The ML verifier's interval holds the exact value",
        "nothing about the circuit: it grades the fast model against the exact one", learned)

    for i, fut in pending:
        status, detail, ms = fut.result()
        checks[i] = checks[i].model_copy(update={"status": status, "detail": detail, "ms": ms})
    pool.shutdown()
    count = {s: sum(c.status == s for c in checks) for s in ("pass", "fail", "skipped", "note")}
    secs = time.perf_counter() - t_start
    ran = len(checks) - count["skipped"]
    summary = (f"{count['pass']} of {ran} checks passed" + (f", {count['fail']} failed" if count["fail"] else "")
               + (f", {count['note']} note" if count["note"] else "")
               + (f"; {count['skipped']} skipped with the reason" if count["skipped"] else "")
               + f", in {secs:.1f} s, across {len({c.category for c in checks})} kinds of check.")
    return ProofSheet(title=spec.metadata.title or "circuit", num_qubits=n, gates=len(spec.operations), noise=noise,
                      checks=checks, passed=count["pass"], failed=count["fail"], skipped=count["skipped"],
                      notes=count["note"], seconds=round(secs, 2), summary=summary)
