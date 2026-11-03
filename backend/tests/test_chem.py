"""H2 from first principles: integrals against Szabo and Ostlund, energies, the noise map, VQE and the endpoint."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from inkubit.api.app import app
from inkubit.chem import (BOHR, _expect, _simulate, best_theta, chem_lab, energy_exact, energy_hf, integrals,
                          vqe_energy)


def test_integrals_match_szabo_and_ostlund_at_1_4_bohr():
    S, h, g = integrals(1.4)
    assert S[0, 1] == pytest.approx(0.6593, abs=1e-4)
    assert h[0, 0] == pytest.approx(-1.1204, abs=1e-4) and h[0, 1] == pytest.approx(-0.9584, abs=1e-4)
    assert g[0, 0, 0, 0] == pytest.approx(0.7746, abs=1e-4) and g[0, 0, 1, 1] == pytest.approx(0.5697, abs=1e-4)
    assert g[1, 0, 1, 0] == pytest.approx(0.2970, abs=1e-4) and g[1, 0, 0, 0] == pytest.approx(0.4441, abs=1e-4)


def test_energies():
    assert energy_hf(1.4) == pytest.approx(-1.1167, abs=1e-4)
    assert energy_exact(1.4) == pytest.approx(-1.1373, abs=1e-4)
    assert energy_exact(40.0) == pytest.approx(2 * -0.46658, abs=1e-4)  # two STO-3G hydrogen atoms
    best = min((a / 100 for a in range(60, 90)), key=lambda a: energy_exact(a / BOHR))
    assert best == pytest.approx(0.73, abs=0.015)
    assert energy_hf(3.0 / BOHR) - energy_exact(3.0 / BOHR) > 0.2  # Hartree-Fock fails as the bond breaks


def test_vqe_minimum_is_the_exact_energy():
    for r in (1.0, 1.4, 3.0, 5.0):
        e, _ = vqe_energy(r, best_theta(r), "ideal", None)
        assert e == pytest.approx(energy_exact(r), abs=1e-10)


def test_noise_map_matches_direct_simulation():
    for t in (0.37, -2.2, 1.9):
        for basis in ("Z", "X"):
            assert _expect(t, basis, "realistic") == pytest.approx(_simulate(t, basis, "realistic"), abs=1e-5)


def test_mitigation_recovers_the_exact_curve_within_shot_noise():
    lab = chem_lab(0.74)
    assert lab.vqe > lab.hf  # raw VQE under realistic noise does worse than Hartree-Fock here
    for p in lab.curve:
        assert abs(p.mitigated - p.exact) < 4 * p.mitigated_err + 1e-4
    assert lab.curve[0].r == pytest.approx(0.3) and lab.curve[-1].r == pytest.approx(3.0)
    assert 0 <= lab.weight_u < 0.1 and chem_lab(3.0).weight_u > 0.4
    assert "not" in lab.summary or "laptop" in lab.summary


def test_endpoint():
    c = TestClient(app)
    d = c.get("/api/lab/chem", params={"r": 1.2}).json()
    assert d["exact"] < d["hf"] and d["spec"]["num_qubits"] == 1
    assert c.get("/api/lab/chem", params={"r": 9}).status_code == 422
