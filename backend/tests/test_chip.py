"""IBM chips from their calibration snapshots: the map, the placement advisor and the IBM endpoints (all offline)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from qcanvas import EXAMPLES_DIR
from qcanvas.chip import UNUSABLE, advise, coordinates, device_names, load, summary
from qcanvas.spec import parse_spec


def _spec(name: str):
    return parse_spec(json.loads((EXAMPLES_DIR / "specs" / f"{name}.json").read_text(encoding="utf-8")))


DEVICE = device_names()[0]


def test_every_snapshot_draws_as_a_heavy_hex_lattice():
    for name in device_names():
        d = load(name)
        coords = d["coords"]
        assert len(coords) == d["num_qubits"] == len(d["qubits"])
        assert len(set(coords)) == len(coords)  # no two qubits on one spot
        for key in d["edges"]:  # every coupler joins neighbours on the drawing
            a, b = map(int, key.split("-"))
            (xa, ya), (xb, yb) = coords[a], coords[b]
            assert abs(xa - xb) + abs(ya - yb) <= 1.0 + 1e-9


def test_coordinates_of_a_small_heavy_hex():
    # two rows of three joined by a bridge (qubit 3) under the middle qubits
    pos = coordinates(7, [(0, 1), (1, 2), (1, 3), (3, 5), (4, 5), (5, 6)])
    assert pos[0] == (0.0, 0.0) and pos[4] == (0.0, 2.0) and pos[3] == (1.0, 1.0)


def test_the_advisor_ranks_every_placement_of_a_bell_pair():
    a = advise(_spec("bell"), DEVICE)
    d = load(DEVICE)
    usable = [k for k, e in d["edges"].items() if e < UNUSABLE]
    assert a.ok and a.candidates <= 2 * len(usable)
    assert a.best.success >= a.median.success >= a.worst.success
    p, q = a.best.qubits
    assert f"{min(p, q)}-{max(p, q)}" in usable
    # the score is the product of (1 - error) over the gates and readouts it uses
    qi, qj = d["qubits"][p], d["qubits"][q]
    ro = lambda x: (x["p01"] + x["p10"]) / 2  # noqa: E731
    want = (1 - d["edges"][f"{min(p, q)}-{max(p, q)}"]) * (1 - qi["sx_error"]) * (1 - ro(qi)) * (1 - ro(qj))
    assert a.best.success == pytest.approx(want, rel=1e-5)


def test_a_toffoli_needs_routing_and_the_advisor_says_so():
    a = advise(_spec("toffoli_and"), DEVICE)
    assert not a.ok and "triangle" in a.note


def test_one_qubit_circuits_take_the_best_single_qubit():
    one = parse_spec({"kind": "circuit", "num_qubits": 1, "num_clbits": 1, "operations": [{"gate": "H", "targets": [0]}],
                      "measurements": [{"qubit": 0, "clbit": 0}]})
    a = advise(one, DEVICE)
    d = load(DEVICE)
    cost = lambda q: (1 - q["sx_error"]) * (1 - (q["p01"] + q["p10"]) / 2) if q["sx_error"] is not None and q["p01"] is not None else 0  # noqa: E731
    assert a.ok and len(a.best.qubits) == 1
    assert a.best.success == pytest.approx(max(cost(q) for q in d["qubits"]), rel=1e-6)


def test_summaries_are_medians_of_working_parts():
    s = summary(load(DEVICE))
    assert 0 < s["two_qubit_error"] < 0.05 and 0 < s["readout_error"] < 0.1 and s["t1_us"] > 10


def test_ibm_endpoints_offline(monkeypatch):
    import qcanvas.api.app as appmod

    monkeypatch.setenv("QCANVAS_PUBLIC", "1")  # a shared host: never run on hardware, never call IBM
    client = TestClient(appmod.app)
    st = client.get("/api/ibm/status").json()
    assert not st["can_run"] and "public mode" in st["reason"] and st["live"] is None
    assert {d["device"] for d in st["devices"]} == set(device_names())
    dev = client.get(f"/api/ibm/device/{DEVICE}").json()
    assert len(dev["coords"]) == dev["num_qubits"]
    assert client.get("/api/ibm/device/..%2Fsecrets").status_code == 404
    adv = client.post("/api/ibm/advise", json={"spec": _spec("bell").model_dump(mode="json", by_alias=True)}).json()
    assert len(adv["advice"]) == len(device_names()) and all(a["ok"] for a in adv["advice"])
    run = client.post("/api/ibm/run", json={"spec": _spec("bell").model_dump(mode="json", by_alias=True)})
    assert run.status_code == 403 and "public mode" in run.json()["detail"]


def test_ibm_experiments_endpoint_refuses_a_rehearsal(monkeypatch, tmp_path):
    import qcanvas.api.app as appmod

    monkeypatch.setattr(appmod, "EXAMPLES_DIR", tmp_path)
    client = TestClient(appmod.app)
    assert client.get("/api/ibm/experiments").status_code == 404
    (tmp_path / "ibm_experiments.json").write_text(json.dumps({"rehearsal": True}), encoding="utf-8")
    assert client.get("/api/ibm/experiments").status_code == 404
