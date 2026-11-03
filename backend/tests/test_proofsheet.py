"""The proof sheet: every check passes on a correct circuit, and each kind of check catches the mistake it guards."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from inkubit import EXAMPLES_DIR
from inkubit.proofsheet import _padded_with_identities, _permuted, proof_sheet
from inkubit.spec import parse_spec
from inkubit.verify.expected import ideal_distribution


def _spec(name: str):
    return parse_spec(json.loads((EXAMPLES_DIR / "specs" / f"{name}.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def bell_sheet():
    return proof_sheet(_spec("bell"))


def test_a_correct_circuit_passes_every_kind_of_check(bell_sheet):
    assert bell_sheet.failed == 0 and bell_sheet.skipped == 0
    assert bell_sheet.passed + bell_sheet.notes == len(bell_sheet.checks) == 11
    assert len({c.category for c in bell_sheet.checks}) == 9
    assert all(c.detail for c in bell_sheet.checks)


def test_the_metamorphic_transforms_keep_the_answer_but_not_the_circuit():
    spec = _spec("hhl_2x2")
    perm = _permuted(spec)
    assert perm.operations != spec.operations
    assert _permuted(perm).operations == spec.operations  # renaming twice is the identity
    padded = _padded_with_identities(spec)
    assert len(padded.operations) > len(spec.operations)
    for other in (perm, padded):
        got, want = ideal_distribution(other), ideal_distribution(spec)
        assert max(abs(got.get(k, 0) - want.get(k, 0)) for k in set(got) | set(want)) < 1e-9


def test_a_compiler_that_drops_a_gate_is_caught(monkeypatch):
    """Translation validation: break Qiskit's transpile and the compilation check must fail."""
    import qiskit

    real = qiskit.transpile

    def broken(circuit, *args, **kwargs):
        out = real(circuit, *args, **kwargs)
        for i in range(len(out.data) - 1, -1, -1):
            if out.data[i].operation.name == "cx":
                del out.data[i]
                break
        return out

    monkeypatch.setattr(qiskit, "transpile", broken)
    sheet = proof_sheet(_spec("ghz3"), run_code=False)
    check = next(c for c in sheet.checks if c.id == "compilation")
    assert check.status == "fail" and "different unitary" in check.detail


def test_the_openqasm2_export_reads_in_a_strict_reader():
    """SX, CP and SWAP are not in the standard qelib1.inc; the export defines them (found by the proof sheet)."""
    from qiskit import qasm2
    from qiskit.quantum_info import Operator

    from inkubit.insights.circuit import exports
    from inkubit.verify.expected import build_reference_circuit

    spec = parse_spec({"kind": "circuit", "num_qubits": 3, "num_clbits": 3, "operations": [
        {"gate": "SX", "targets": [0]}, {"gate": "CP", "controls": [0], "targets": [1], "params": [0.7]},
        {"gate": "SWAP", "targets": [1, 2]}, {"gate": "CCX", "controls": [0, 1], "targets": [2]}],
        "measurements": [{"qubit": q, "clbit": q} for q in range(3)]})
    back = qasm2.loads(exports(spec).qasm2).remove_final_measurements(inplace=False)
    assert Operator(back).equiv(Operator(build_reference_circuit(spec)))


def test_the_endpoint_runs_the_sheet_and_rejects_networks():
    from inkubit.api.app import app

    client = TestClient(app)
    ok = client.post("/api/proofsheet", json={"spec": json.loads((EXAMPLES_DIR / "specs" / "bell.json").read_text())})
    assert ok.status_code == 200 and ok.json()["failed"] == 0
    net = json.loads((EXAMPLES_DIR / "specs" / "network_fiber_chain.json").read_text())
    assert client.post("/api/proofsheet", json={"spec": net}).status_code == 422
