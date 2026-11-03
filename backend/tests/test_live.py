"""Live board: wire positions from the overlay, marginals, and the endpoint on a sample sketch (offline models)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from inkubit import EXAMPLES_DIR
from inkubit.api.app import app
from inkubit.live import marginals, wires
from inkubit.sketch import OverlayBox, SketchAnalysis


def test_marginals_follow_qiskit_bit_order():
    p1 = marginals({"01": 0.25, "11": 0.5, "00": 0.25}, [(0, 0), (1, 1)])
    assert p1[0] == pytest.approx(0.75) and p1[1] == pytest.approx(0.5)


def test_wires_sit_at_the_median_height_of_their_boxes():
    spec = {"kind": "circuit", "num_qubits": 2, "operations": [
        {"gate": "H", "targets": [0]}, {"gate": "X", "targets": [1]}, {"gate": "CX", "controls": [0], "targets": [1]}]}
    boxes = [OverlayBox(segment_id="a", concept="box", bbox=(10, 90, 30, 110), confidence=1, linked_to="operations[0]"),
             OverlayBox(segment_id="b", concept="box", bbox=(10, 190, 30, 210), confidence=1, linked_to="operations[1]"),
             OverlayBox(segment_id="c", concept="circle", bbox=(60, 195, 70, 205), confidence=1, linked_to="operations[2]")]
    a = SketchAnalysis(image_sha256="x", mime="image/png", width=200, height=300, kind="circuit", concepts=[],
                       segments=[], spec=spec, valid=True, overlay=boxes)
    w = {r["qubit"]: r for r in wires(a)}
    assert w[0]["y"] == pytest.approx(100) and w[1]["y"] == pytest.approx(200)
    assert w[0]["x_end"] == 30 and w[0]["x_right"] == 70
    assert w[1]["x_end"] == 70  # a CNOT with only one box found: it is the target's symbol


def test_a_two_qubit_gates_boxes_go_to_its_qubits_top_to_bottom():
    spec = {"kind": "circuit", "num_qubits": 2, "operations": [{"gate": "CX", "controls": [0], "targets": [1]}]}
    boxes = [OverlayBox(segment_id="t", concept="circle", bbox=(50, 190, 70, 210), confidence=1, linked_to="operations[0]"),
             OverlayBox(segment_id="c", concept="dot", bbox=(55, 95, 65, 105), confidence=1, linked_to="operations[0]")]
    a = SketchAnalysis(image_sha256="x", mime="image/png", width=200, height=300, kind="circuit", concepts=[],
                       segments=[], spec=spec, valid=True, overlay=boxes)
    w = {r["qubit"]: r["y"] for r in wires(a)}
    assert w == {0: 100, 1: 200}


def test_endpoint_reads_a_sample_sketch():
    fx = sorted((EXAMPLES_DIR / "images").glob("*.json"))[0]
    name = json.loads(fx.read_text(encoding="utf-8"))["name"]
    png = (EXAMPLES_DIR / "images" / f"{name}.png").read_bytes()
    body = TestClient(app).post("/api/live/read", files={"file": ("frame.png", png, "image/png")}).json()
    assert body["analysis"]["valid"] and body["result"]["kind"] in ("circuit", "network")
    if body["result"]["kind"] == "circuit":
        assert sum(body["result"]["ideal"].values()) == pytest.approx(1.0, abs=1e-6)
        assert body["result"]["wires"]


def test_duplicate_detections_of_one_symbol_count_once():
    spec = {"kind": "circuit", "num_qubits": 2, "operations": [{"gate": "CX", "controls": [0], "targets": [1]}]}
    same = (50, 190, 70, 210)
    boxes = [OverlayBox(segment_id="a", concept="dot", bbox=same, confidence=1, linked_to="operations[0]"),
             OverlayBox(segment_id="b", concept="circle", bbox=same, confidence=1, linked_to="operations[0]")]
    a = SketchAnalysis(image_sha256="x", mime="image/png", width=200, height=300, kind="circuit", concepts=[],
                       segments=[], spec=spec, valid=True, overlay=boxes)
    assert {r["qubit"]: r["y"] for r in wires(a)} == {1: 200}
