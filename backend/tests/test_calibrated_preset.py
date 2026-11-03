"""The calibrated noise preset (a real device's calibration snapshot) and the hardware results built on it."""

from __future__ import annotations

import json

import pytest
from qiskit.quantum_info import average_gate_fidelity

from inkubit import EXAMPLES_DIR
from inkubit.hardware import tvd
from inkubit.sim.noise import CALIBRATION, PRESETS, build_noise_model, calibrated_preset, gate_errors
from inkubit.spec import parse_spec
from inkubit.verify.expected import noisy_distribution
from inkubit.verify.verdict import THRESHOLDS

CAL = json.loads(CALIBRATION.read_text(encoding="utf-8"))


def test_the_preset_is_built_from_the_snapshot():
    p = PRESETS["calibrated"]
    assert CAL["device"] in p.label and p.readout_p01 == pytest.approx(CAL["readout_p01"], abs=1e-6)
    assert p.t1_us == pytest.approx(CAL["t1_us"], abs=0.01)
    assert "calibrated" in THRESHOLDS and build_noise_model(p) is not None


def test_each_gate_keeps_the_error_the_device_reported():
    """Depolarizing plus thermal relaxation over the gate time must add up to the reported average gate error."""
    errs = gate_errors(PRESETS["calibrated"])
    assert 1 - average_gate_fidelity(errs[1].to_quantumchannel()) == pytest.approx(CAL["sx_error"], rel=0.01)
    assert 1 - average_gate_fidelity(errs[2].to_quantumchannel()) == pytest.approx(CAL["two_qubit_error"], rel=0.01)


def test_today_s_chip_is_quieter_than_the_generic_preset():
    cal, gen = PRESETS["calibrated"], PRESETS["realistic"]
    assert cal.p2 < gen.p2 and cal.readout_p10 < gen.readout_p10


def test_no_snapshot_no_preset(tmp_path):
    assert calibrated_preset(tmp_path / "missing.json") is None


def test_the_stored_hardware_comparison_matches_the_preset():
    """hardware_runs.json's calibrated distances are recomputed from its complete counts: no stale number survives."""
    hw = json.loads((EXAMPLES_DIR / "hardware_runs.json").read_text(encoding="utf-8"))
    assert not hw["rehearsal"] and hw["calibration"]["device"] == CAL["device"]
    for r in hw["runs"]:
        spec = parse_spec(json.loads((EXAMPLES_DIR / "specs" / f"{r['id']}.json").read_text(encoding="utf-8")))
        assert tvd(noisy_distribution(spec, "calibrated"), r["measured"]) == pytest.approx(r["tvd_calibrated"], abs=1e-9)


def test_discovery_hardware_endpoint_refuses_a_rehearsal(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import inkubit.api.app as appmod

    monkeypatch.setattr(appmod, "EXAMPLES_DIR", tmp_path)
    client = TestClient(appmod.app)
    assert client.get("/api/hardware/discovery").status_code == 404
    (tmp_path / "discovery_hardware.json").write_text(json.dumps({"rehearsal": True, "goals": []}), encoding="utf-8")
    assert client.get("/api/hardware/discovery").status_code == 404
