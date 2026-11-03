"""Proven illustrations: the exact comparison, and the read-back / correct / fall-back loop with stand-in models."""

import base64
import json
from types import SimpleNamespace

import pytest

from inkubit import figproof
from inkubit.adapters.base import DiagramResult, ModelCall

BASE = {"kind": "circuit", "version": "1.0", "num_qubits": 3, "num_clbits": 3,
        "measurements": [{"qubit": q, "clbit": q} for q in range(3)], "metadata": {"title": "t"}}


def circuit(*ops, n=3):
    return {**BASE, "num_qubits": n, "num_clbits": n, "measurements": [{"qubit": q, "clbit": q} for q in range(n)],
            "operations": list(ops)}


H0 = {"gate": "H", "targets": [0]}
CX01 = {"gate": "CX", "controls": [0], "targets": [1]}
CX12 = {"gate": "CX", "controls": [1], "targets": [2]}
GHZ = circuit(H0, CX01, CX12)


def test_same_circuit_is_exact_and_ignores_the_order_of_commuting_gates():
    assert figproof.same_circuit(GHZ, GHZ)[0]
    a = circuit({"gate": "X", "targets": [0]}, {"gate": "Z", "targets": [2]})
    b = circuit({"gate": "Z", "targets": [2]}, {"gate": "X", "targets": [0]})
    assert figproof.same_circuit(a, b)[0]
    ok, why = figproof.same_circuit(GHZ, circuit(H0, CX12))
    assert not ok and "CX q0→q1" in why
    ok, why = figproof.same_circuit(GHZ, circuit(H0, CX01, n=2))
    assert not ok and "2 qubits" in why
    assert not figproof.same_circuit(GHZ, circuit(H0, {"gate": "CX", "controls": [1], "targets": [0]}, CX12))[0]


def test_angles_drawn_to_two_decimals_still_match():
    real = circuit({"gate": "RY", "targets": [0], "params": [2.0943951]}, CX01)
    drawn = circuit({"gate": "RY", "targets": [0], "params": [2.09]}, CX01)
    ok, why = figproof.same_circuit(real, drawn)
    assert ok and "precision" in why
    assert not figproof.same_circuit(real, circuit({"gate": "RY", "targets": [0], "params": [1.5]}, CX01))[0]


class Stub:
    """Reads back a queue of specs (None: unreadable) and counts edits."""

    def __init__(self, readings, can_edit=True):
        self.readings, self.edits, self.can_edit = list(readings), 0, can_edit
        call = ModelCall(provider="meta", model="stub", role="x")
        self.reasoning = SimpleNamespace(choose_concepts=lambda img, mime: ("circuit", ["box"], call),
                                         draft_spec=self._draft)
        self.segmentation = SimpleNamespace(segment=lambda img, mime, c: SimpleNamespace(call=call))
        self.image = SimpleNamespace(edit=self._edit)

    def _draft(self, img, mime, segs, kind, context=""):
        assert "Ignore the title and any captions" in context
        spec = self.readings.pop(0)
        return SimpleNamespace(spec=spec or {}, valid=spec is not None, issues=["unreadable"], call=ModelCall(
            provider="meta", model="stub", role="read sketch"))

    def _edit(self, image_b64, mime, prompt):
        if not self.can_edit:
            raise RuntimeError("no edits here")
        self.edits += 1
        assert "What is wrong now" in prompt and "CX with control on wire q0" in prompt
        return DiagramResult(image_b64=PNG, mime="image/png", caption="", call=ModelCall(provider="meta", model="stub",
                                                                                        role="correct figure"))


def _png() -> str:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 40), (20, 20, 24)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


PNG = _png()


def test_a_right_figure_is_proven_first_time():
    m = Stub([GHZ])
    p = figproof.prove(m, GHZ, PNG)
    assert p["verdict"] == "proven" and p["attempts"] == 1 and m.edits == 0 and p["image"] == PNG


def test_a_wrong_figure_is_corrected_then_proven():
    m = Stub([circuit(H0, CX12), GHZ])
    p = figproof.prove(m, GHZ, PNG)
    assert p["verdict"] == "repaired" and p["attempts"] == 2 and m.edits == 1
    assert "it shows H on q0, CX q1→q2" in p["detail"]


def test_a_figure_that_never_matches_is_replaced_by_the_exact_drawing():
    m = Stub([circuit(H0), circuit(H0, CX12), None])
    p = figproof.prove(m, GHZ, PNG)
    assert p["verdict"] == "unread" and m.edits == figproof.MAX_REPAIRS
    assert p["image"] != PNG and "exact Qiskit drawing" in p["detail"]
    m = Stub([circuit(H0)], can_edit=False)
    p = figproof.prove(m, GHZ, PNG)
    assert p["verdict"] == "mismatch" and "could not be corrected" in p["detail"]


def test_the_recorded_benchmark_adds_up():
    from inkubit import EXAMPLES_DIR

    path = EXAMPLES_DIR / "figure_benchmark.json"
    if not path.exists():
        pytest.skip("no recorded benchmark")
    data = json.loads(path.read_text(encoding="utf-8"))
    rows, t = data["circuits"], data["totals"]
    assert t["circuits"] == len(rows)
    assert t["first_try"] == sum(r["verdict"] == "proven" for r in rows)
    assert t["first_try"] + t["repaired"] + t["mismatch"] + t["unread"] == len(rows)
    for r in rows:
        assert (EXAMPLES_DIR / r["first_image"]).exists()
        assert r["verdict"] in ("proven", "repaired") or r.get("final_image")  # the exact drawing replaced it
