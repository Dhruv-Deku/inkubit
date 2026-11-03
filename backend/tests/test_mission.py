"""Mission control: plan cleaning, circuits passed between steps, repair, verification that flags, the endpoint."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from inkubit.adapters.base import ModelCall
from inkubit.api.app import app
from inkubit.copilot import ToolRun
from inkubit.mission import Ctx, Mission, clean_plan, offline_plan, run_mission, verify

BELL = {"kind": "circuit", "version": "1.0", "num_qubits": 2, "num_clbits": 2,
        "operations": [{"gate": "H", "targets": [0]}, {"gate": "H", "targets": [0]}, {"gate": "H", "targets": [0]},
                       {"gate": "CX", "controls": [0], "targets": [1]}],
        "measurements": [{"qubit": 0, "clbit": 0}, {"qubit": 1, "clbit": 1}]}


def test_clean_plan_drops_unknown_tools_and_forward_dependencies():
    steps, notes = clean_plan([
        {"id": "s1", "tool": "molecule_h2", "arguments": '{"bond_length_angstrom": 0.74}', "after": ["s2"],
         "purpose": ""},
        {"id": "s2", "tool": "teleport_me", "arguments": "{}", "after": [], "purpose": ""},
        {"id": "s3", "tool": "ml_verify", "arguments": '{"circuit_from": "s1"}', "after": [], "purpose": ""},
    ])
    assert [s.id for s in steps] == ["s1", "s3"]
    assert steps[0].after == [] and steps[1].after == ["s1"]  # circuit_from adds the dependency
    assert any("unknown tool" in n for n in notes) and any("ignored dependencies" in n for n in notes)


def test_offline_plan_covers_a_link_and_a_spy():
    steps = offline_plan("Connect two cities 1,200 km apart: compare a satellite with fiber, and check that a spy "
                         "listening to 25% of the photons gets caught.", None)
    assert [s["tool"] for s in steps] == ["plan_quantum_link", "plan_quantum_link", "quantum_key_distribution"]
    assert steps[2]["arguments"]["eavesdrop_share"] == 0.25


def test_photo_circuit_flows_through_optimize_into_the_ml_verifier():
    m = Mission("Read this circuit, shorten it and check it against noise")
    run_mission(m, Ctx(live=False), photo=BELL)
    assert m.status == "done", m.error
    nodes = m.nodes
    assert nodes["s1"].tool == "simulate_circuit" and nodes["s3"].tool == "ml_verify"
    assert nodes["s3"].after == ["s2"]
    assert len(nodes["s3"].args["operations"]) < len(BELL["operations"])  # the proven shorter circuit was used
    names = {c.name for c in nodes["s1"].checks}
    assert {"two simulators", "ML verifier"} <= names
    assert all(c.ok for n in nodes.values() for c in n.checks if c.affects)
    assert not any(c.affects for c in nodes["s1"].checks if c.name == "ML verifier")
    assert m.report and m.report.router == "offline" and m.report.trace["untraced"] == []


class FakeReasoning:
    """Plans one good step and one with broken arguments, repairs it, writes a report."""

    def __init__(self):
        self.calls: list[str] = []

    def structured(self, system, user, schema, name, effort="low", max_tokens=8000, model=None):
        self.calls.append(name)
        call = ModelCall(provider="meta", model="fake", role=name, cached=False, latency_s=0.0)
        if name == "mission_plan":
            return {"goal": "g", "steps": [
                {"id": "s1", "tool": "factor_with_shor", "arguments": json.dumps({"a": 7}), "after": [], "purpose": "a"},
                {"id": "s2", "tool": "molecule_h2", "arguments": json.dumps({"bond": 0.74}), "after": [],
                 "purpose": "b"}]}, call
        if name == "step_repair":
            return {"arguments": json.dumps({"bond_length_angstrom": 0.74}), "change": "renamed the argument"}, call
        facts = json.loads(user)["steps"]
        energy = facts["s2"]["facts"]["exact_energy_hartree"]
        return {"headline": f"The period is 4 and H2 sits at {energy} Ha.",
                "findings": ["Shor found the factors of 15.", "The made-up number 12.345 is not from a tool."],
                "next": "Bigger numbers need error correction."}, call


def test_live_path_repairs_a_step_and_traces_the_report():
    fake = FakeReasoning()
    m = Mission("Factor 15 and find the H2 energy")
    run_mission(m, Ctx(live=True, reasoning=fake))
    assert m.status == "done", m.error
    assert fake.calls == ["mission_plan", "step_repair", "mission_report"]
    assert m.nodes["s2"].status == "repaired" and "renamed" in m.nodes["s2"].detail
    assert m.report.router == "muse"
    assert m.report.trace["untraced"] == ["12.345"]  # the invented number is caught


def test_verification_flags_a_result_that_breaks_physics():
    bad = ToolRun(name="molecule_h2", args={}, facts={"exact_energy_hartree": -1.0, "hartree_fock_hartree": -1.1})
    assert [c.ok for c in verify(bad)] == [False]
    bad_cut = ToolRun(name="max_cut", args={}, facts={"qaoa_most_likely_split": {"separated": 7},
                                                      "best_possible_separated": 6})
    assert [c.ok for c in verify(bad_cut)] == [False]


def test_endpoint_runs_a_mission_and_streams_it():
    client = TestClient(app)
    started = client.post("/api/missions", data={"goal": "Factor 15 with Shor's algorithm", "transcript": "factor fifteen"})
    assert started.status_code == 200
    mid = started.json()["mission_id"]
    for _ in range(120):
        body = client.get(f"/api/missions/{mid}").json()
        if body["status"] != "running":
            break
        time.sleep(0.25)
    assert body["status"] == "done", body
    assert {n["id"] for n in body["nodes"]} >= {"voice", "plan", "s1", "report"}
    events = client.get(f"/api/missions/{mid}/events").text
    assert "event: mission" in events and "event: end" in events


def test_an_ml_miss_is_a_note_not_a_flag():
    from inkubit.mission import run_step

    run = run_step("run_algorithm", {"name": "grover3"})
    checks = verify(run)
    assert all(c.ok for c in checks if c.affects)
    ml = next(c for c in checks if c.name == "ML verifier")
    assert ml.affects is False


def test_a_finished_mission_downloads_as_one_page_with_its_numbers_marked():
    from inkubit.mission_report import marked, render

    m = Mission("Teleport a qubit and check how it survives noise")
    run_mission(m, Ctx(live=False), photo=BELL)
    page = render(m)
    assert page.startswith("<!doctype html>") and m.goal in page and "Plan" in page and "Checks" in page
    assert "from qiskit import QuantumCircuit" in page  # standalone code for the photographed circuit
    assert all(n.id in page for n in m.nodes.values() if n.lane == "step")
    text = marked("Fidelity 0.912 over 1,200 km; 3 layers; outcome 0110; 47%", untraced=["47%"])
    assert '<span class="ok"' in text and text.count('class="ok"') == 2  # 0.912 and 1,200
    assert '<mark class="no"' in text and "47%" in text.split('<mark class="no"')[1]
    assert "3 layers" in text and "0110" in text  # small counts and bitstrings stay plain


def test_report_endpoint_waits_for_the_mission_to_finish():
    client = TestClient(app)
    assert client.get("/api/missions/nope/report").status_code == 404
    mid = client.post("/api/missions", data={"goal": "Run Grover search on 2 qubits"}).json()["mission_id"]
    for _ in range(120):
        r = client.get(f"/api/missions/{mid}/report")
        if r.status_code != 409:
            break
        time.sleep(0.25)
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"] and "Grover" in r.text

