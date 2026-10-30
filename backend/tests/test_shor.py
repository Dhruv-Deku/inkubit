"""Shor's algorithm for 15: the multipliers, the period peaks, the classical finish and the lab."""

from __future__ import annotations

import json
from fractions import Fraction

import numpy as np
import pytest
from fastapi.testclient import TestClient
from qiskit.quantum_info import Statevector

from qcanvas import EXAMPLES_DIR
from qcanvas.api.app import app
from qcanvas.shor import (COPRIME, WORK, continued_fraction, finish, match_shor, multiply_ops, order, shor_lab,
                          shor_readout, shor_spec)
from qcanvas.spec import parse_spec
from qcanvas.textspec import parse_description
from qcanvas.verify import ideal_distribution
from qcanvas.verify.expected import build_reference_circuit


def _work_value(a: int, x: int) -> tuple[int, float]:
    ops = [{"gate": "X", "targets": [0]}] + [{"gate": "X", "targets": [WORK[k]]} for k in range(4) if x >> k & 1]
    spec = parse_spec({"kind": "circuit", "version": "1.0", "num_qubits": 7, "num_clbits": 1,
                       "operations": ops + multiply_ops(a, 0), "measurements": [{"qubit": 0, "clbit": 0}]})
    sv = Statevector.from_instruction(build_reference_circuit(spec).remove_final_measurements(inplace=False)).data
    idx = int(np.argmax(np.abs(sv)))
    return sum(((idx >> q) & 1) << k for k, q in enumerate(WORK)), abs(sv[idx])


@pytest.mark.parametrize("a", COPRIME)
def test_controlled_multiplication_is_times_a_mod_15(a):
    for x in range(1, 15):
        value, amp = _work_value(a, x)
        assert value == a * x % 15 and amp == pytest.approx(1, abs=1e-12)


@pytest.mark.parametrize("a", COPRIME)
def test_counting_register_peaks_at_multiples_of_8_over_r(a):
    r = order(a)
    ideal = ideal_distribution(parse_spec(shor_spec(a)))
    peaks = {format(k * 8 // r, "03b"): 1 / r for k in range(r)}
    assert ideal == pytest.approx(peaks, abs=1e-9)


def test_classical_finish():
    assert continued_fraction(Fraction(3, 4)) == [0, 1, 3]
    assert finish(6, 7)[1] == [3, 5] and finish(2, 7)[1] == [3, 5]
    assert finish(4, 7)[1] is None and "not 1" in finish(4, 7)[2][-1]  # r = 2 is not 7's period
    assert finish(0, 7)[0] is None  # phase 0 carries no information
    assert finish(1, 7)[1] is None  # r = 8: a multiple of the period, only trivial factors
    assert finish(4, 14)[1] is None and "−1" in finish(4, 14)[2][-1]  # 14 = -1 mod 15 never splits
    assert finish(4, 4)[1] == [3, 5] and finish(4, 11)[1] == [3, 5]


def test_lab_success_rates_and_shortcuts():
    lab = shor_lab(7)
    assert lab.period == 4 and lab.success_ideal == pytest.approx(0.5)
    assert 0.3 < lab.success_noisy < lab.success_ideal  # noise costs, but the factors still come out often
    assert sum(o.measured or 0 for o in lab.outcomes) == pytest.approx(1)
    assert shor_lab(14).success_ideal == 0 and "pick another a" in shor_lab(14).summary
    lucky = shor_lab(6)
    assert not lucky.coprime and lucky.shortcut == 3 and not lucky.outcomes


def test_runs_of_a_shor_circuit_get_the_factoring_readout():
    spec = parse_spec(shor_spec(11))
    assert match_shor(spec) == 11
    edited = parse_spec({**shor_spec(11), "operations": shor_spec(11)["operations"][:-1]})
    assert match_shor(edited) is None and shor_readout(edited, "realistic", None, None) is None
    out = shor_readout(spec, "realistic", {"100": 0.45, "000": 0.55}, 4096)
    assert out.success_measured == pytest.approx(0.45) and out.shots == 4096


def test_gallery_example_and_words():
    data = json.loads((EXAMPLES_DIR / "specs" / "shor15.json").read_text(encoding="utf-8"))
    assert data == shor_spec(7)
    spec, label = parse_description("Shor's algorithm with a = 2")
    assert match_shor(parse_spec(spec)) == 2 and "a = 2" in label
    assert match_shor(parse_spec(parse_description("factor 15")[0])) == 7


def test_lab_endpoint():
    c = TestClient(app)
    body = c.get("/api/lab/shor", params={"a": 13}).json()
    assert body["a"] == 13 and body["period"] == 4 and len(body["outcomes"]) == 8
    assert c.get("/api/lab/shor", params={"a": 15}).status_code == 422
