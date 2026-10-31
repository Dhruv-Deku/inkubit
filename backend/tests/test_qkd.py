"""BB84: error rates against theory, the per-photon rule against Qiskit, the abort, and the endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from qcanvas.api.app import app
from qcanvas.qkd import ABORT, bb84, photon_spec
from qcanvas.spec import parse_spec
from qcanvas.verify.expected import ideal_distribution


@pytest.mark.parametrize("bit", [0, 1])
@pytest.mark.parametrize("basis", ["+", "x"])
def test_measuring_in_the_wrong_basis_is_a_coin_flip(bit, basis):
    same = ideal_distribution(parse_spec(photon_spec(bit, basis, basis)))
    assert same == pytest.approx({str(bit): 1.0})
    other = ideal_distribution(parse_spec(photon_spec(bit, basis, "x" if basis == "+" else "+")))
    assert other == pytest.approx({"0": 0.5, "1": 0.5})


def test_eve_in_the_wrong_basis_disturbs_bob():
    d = ideal_distribution(parse_spec(photon_spec(0, "+", "+", eve="x")))  # clbit 0 is Bob, clbit 1 is Eve
    bob_one = sum(p for k, p in d.items() if k[-1] == "1")
    assert bob_one == pytest.approx(0.5)  # a quarter error overall once Eve picks + half the time
    assert ideal_distribution(parse_spec(photon_spec(1, "x", "x", eve="x"))) == pytest.approx({"11": 1.0})


def test_error_rate_follows_a_quarter_of_the_spy_share():
    for eve in (0.0, 0.4, 1.0):
        lab = bb84(40000, eve, 0.0, seed=11)
        assert lab.qber == pytest.approx(eve / 4, abs=4 * lab.qber_err + 0.002)
        assert lab.sifted == pytest.approx(20000, rel=0.03)
    full = bb84(40000, 1.0, 0.0, seed=11)
    assert full.caught and full.key_bits == 0 and full.eve_knows == pytest.approx(0.75, abs=0.02)


def test_quiet_channel_keeps_a_key():
    lab = bb84(4000, 0.0, 0.01, seed=5)
    assert not lab.caught and lab.qber < ABORT and 0 < lab.key_bits < lab.sifted
    assert len(lab.shown) == 20 and all(p.eve is None for p in lab.shown)


def test_endpoint():
    c = TestClient(app)
    assert c.get("/api/lab/qkd", params={"eve": 0.8, "photons": 2000}).json()["caught"]
    assert c.get("/api/lab/qkd", params={"photons": 5}).status_code == 422
