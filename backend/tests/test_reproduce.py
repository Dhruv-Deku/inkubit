"""Paper reproducibility checker: QASM from pasted text, claims by rules, error bars, bit order, the endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from qcanvas.api.app import app
from qcanvas.reproduce import claims_from_text, extract_qasm, reproduce, shots_from_text

GHZ = 'OPENQASM 2.0; include "qelib1.inc"; qreg q[3]; creg c[3]; h q[0]; cx q[0],q[1]; cx q[1],q[2]; measure q -> c;'


def test_qasm_is_cut_out_of_a_caption():
    q = extract_qasm("Appendix B. " + GHZ + " Fig. 2 shows the measured counts.")
    assert q.startswith("OPENQASM 2.0;") and q.endswith("measure q -> c;") and "Fig" not in q


def test_claims_and_shots_are_read_by_rules():
    c = claims_from_text("Measured over 8,192 shots: P(000) = 0.47, |111⟩: 45%, 001 -> 0.021")
    assert [(x.outcome, x.probability) for x in c] == [("000", 0.47), ("111", 0.45), ("001", 0.021)]
    assert shots_from_text("8,192 shots") == 8192


def test_hardware_data_reproduces_and_a_wrong_ideal_claim_does_not():
    ok = reproduce(None, GHZ + " measured on hardware, 8192 shots: P(000)=0.47, P(111)=0.45")
    assert ok.verdict == "reproduced" and ok.read_from == "text"
    bad = reproduce(None, GHZ + " ideal simulation: 000: 70%, 111: 30%")
    assert bad.verdict == "not reproduced"
    assert all("off by 0.200" in c.verdict for c in bad.claims)


def test_bit_order_is_inferred_when_the_paper_writes_q0_on_the_left():
    q2 = 'OPENQASM 2.0; include "qelib1.inc"; qreg q[2]; creg c[2]; x q[0]; measure q -> c;'
    r = reproduce(None, q2 + " ideal: 10: 1.0")
    assert r.bit_order == "q0_leftmost" and r.bit_order_inferred and r.verdict == "reproduced"


def test_a_figure_needs_the_live_model_and_the_endpoint_validates():
    with pytest.raises(ValueError):
        reproduce(b"not an image", "", None)
    client = TestClient(app)
    assert client.post("/api/reproduce", data={"text": ""}).status_code == 422
    body = client.post("/api/reproduce", data={"text": GHZ + " P(000)=0.5, P(111)=0.5 ideal"}).json()
    assert body["verdict"] == "reproduced" and body["spec"]["num_qubits"] == 3
