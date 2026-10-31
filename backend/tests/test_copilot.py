"""Ask Q-Canvas: the tools, the number tracer, the live tool loop (with a scripted model) and the offline router."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from qcanvas.adapters.base import ModelCall
from qcanvas.api.app import app
from qcanvas.copilot import TOOLS, ToolRun, ask_live, ask_offline, run_tool, trace

GHZ = {"num_qubits": 3, "operations": [{"gate": "H", "targets": [0]}, {"gate": "CX", "controls": [0], "targets": [1]},
                                       {"gate": "CX", "controls": [0], "targets": [2]}]}


def test_every_tool_is_declared_and_runs():
    names = {t["function"]["name"] for t in TOOLS}
    cases = {
        "simulate_circuit": GHZ, "optimize_circuit": GHZ, "molecule_h2": {"bond_length_angstrom": 1.2},
        "quantum_key_distribution": {"eavesdrop_share": 0.5}, "factor_with_shor": {"a": 7},
        "max_cut": {"names": ["Ana", "Ben", "Cai"], "conflicts": [["Ana", "Ben"], ["ben", "Cai"]]},
        "plan_quantum_link": {"distance_km": 200, "medium": "fiber", "repeaters": 1}, "error_correction": {"gate_quality": 1},
        "translate_notation": {"text": "(|01⟩ − |10⟩)/√2"},
    }
    assert names == set(cases)
    for name, args in cases.items():
        run = run_tool(name, args)
        assert run.error is None and run.facts and run.card, (name, run.error)
    ghz = run_tool("simulate_circuit", GHZ)
    assert ghz.facts["outcomes_perfect"] == {"000": 0.5, "111": 0.5} and ghz.facts["entangled_qubits"] == [0, 1, 2]
    assert run_tool("max_cut", cases["max_cut"]).facts["best_possible_separated"] == 2


def test_bad_arguments_come_back_as_errors_the_model_can_fix():
    run = run_tool("simulate_circuit", {"num_qubits": 2, "operations": [{"gate": "CX", "controls": [0], "targets": [5]}]})
    assert run.error and not run.facts
    assert run_tool("no_such_tool", {}).error


def test_trace_flags_numbers_no_tool_returned():
    runs = [ToolRun(name="x", args={}, facts={"energy": -1.13728, "share": 0.413, "bits": 356})]
    t = trace("Energy -1.1373 Ha, 41.3% of the way, 356 bits, 3 layers, outcome 0110, and a made-up 0.777.", "", runs)
    assert t.checked == 4 and t.traced == 3 and t.untraced == ["0.777"]
    assert trace("You asked about 1.5 Å.", "H2 at 1.5 angstrom", runs).given == 1


def test_live_loop_runs_the_tools_the_model_asks_for_and_sends_results_back():
    seen = []

    def scripted(messages, tools):
        seen.append(messages)
        if len(seen) == 1:
            return ({"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "simulate_circuit", "arguments": json.dumps(GHZ)}},
                {"id": "c2", "type": "function", "function": {"name": "factor_with_shor", "arguments": "{\"a\": 7}"}}]},
                ModelCall(provider="meta", model="muse-spark-1.3", role="assistant"))
        return ({"role": "assistant", "content": "GHZ reads 000 or 111 with probability 0.5 each; the period is 4 and "
                 "a perfect run succeeds 0.5 of the time, 9.99 made up."}, ModelCall(provider="meta", model="muse-spark-1.3", role="assistant"))

    reply = ask_live("GHZ and Shor please", [], scripted)
    assert [r.name for r in reply.tools] == ["simulate_circuit", "factor_with_shor"] and len(reply.calls) == 2
    second = seen[1]
    assert second[-3]["tool_calls"] and second[-2]["role"] == "tool" and second[-2]["tool_call_id"] == "c1"
    assert second[-1]["tool_call_id"] == "c2" and "factors" in second[-1]["content"]
    assert reply.trace.untraced == ["9.99"]
    assert second[0]["role"] == "system" and "never work out a quantum result yourself" in second[0]["content"]


@pytest.mark.parametrize("q, tool", [
    ("What is the energy of H2 at 1.5 angstrom?", "molecule_h2"), ("Eve listens to 30% of photons", "quantum_key_distribution"),
    ("factor 15 with shor a=7", "factor_with_shor"), ("600 km of fiber with 2 repeaters", "plan_quantum_link"),
    ("GHZ state on 4 qubits", "simulate_circuit"), ("when does error correction break even", "error_correction"),
])
def test_offline_router(q, tool):
    reply = ask_offline(q)
    assert [r.name for r in reply.tools] == [tool] and reply.router == "offline"
    assert not reply.trace.untraced, reply.answer


def test_endpoint_offline_is_labelled():
    d = TestClient(app).post("/api/copilot", json={"message": "Eve listens to 80% of photons"}).json()
    assert d["router"] == "offline" and d["calls"][0]["provider"] == "mock" and d["tools"][0]["facts"]["eavesdropper_caught"]


class ToolClient:
    def __init__(self):
        self.calls = []

    def chat_message(self, model, messages, tools, **kw):
        self.calls.append((model, kw))
        return {"role": "assistant", "content": "done"}, False


def test_deep_mode_asks_muse_wonder_with_more_effort():
    from qcanvas.adapters.config import load_settings
    from qcanvas.adapters.meta_vision import MetaReasoningModel

    fake = ToolClient()
    m = MetaReasoningModel(load_settings(), fake)  # type: ignore[arg-type]
    _, fast = m.tool_chat([], [])
    _, deep = m.tool_chat([], [], model="muse-wonder-1.0", effort="medium")
    assert fast.model == "muse-spark-1.3" and deep.model == "muse-wonder-1.0"
    assert fake.calls[0] == ("muse-spark-1.3", {"reasoning_effort": "low", "max_tokens": 6000})
    assert fake.calls[1] == ("muse-wonder-1.0", {"reasoning_effort": "medium", "max_tokens": 16000})


def test_round_limit_is_respected():
    calls = []

    def loop(messages, tools):
        calls.append(1)
        return ({"role": "assistant", "content": None, "tool_calls": [
            {"id": f"c{len(calls)}", "type": "function", "function": {"name": "factor_with_shor", "arguments": "{\"a\": 7}"}}]},
            ModelCall(provider="meta", model="muse-wonder-1.0", role="assistant"))

    reply = ask_live("keep going", [], loop, rounds=6)
    assert len(calls) == 7 and len(reply.tools) == 7 and "did not finish" in reply.answer
