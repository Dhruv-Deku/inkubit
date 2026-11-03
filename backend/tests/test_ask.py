"""Ask Inkubit: questions answered only from a finished run's facts."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from inkubit.adapters.config import load_settings
from inkubit.adapters.meta_vision import MetaReasoningModel
from inkubit.api.app import app
from inkubit.ask import ask_context, offline_answer
from inkubit.network.agent import run_network_agent
from inkubit.spec import parse_spec

client = TestClient(app)


def _finished(spec: dict, **options) -> str:
    job = client.post("/api/jobs/spec", json={"spec": spec, "options": {"pace_s": 0, **options}}).json()["job_id"]
    for _ in range(400):
        body = client.get(f"/api/jobs/{job}").json()
        if body["status"] in ("done", "failed"):
            return job
        time.sleep(0.3)
    raise AssertionError("job did not finish")


def test_offline_answers_come_from_the_run(example):
    job = _finished(example("bell"), noise="realistic", demo_mode=True, demo_fault="missing_cnot")
    ask = lambda q: client.post(f"/api/jobs/{job}/ask", json={"question": q}).json()  # noqa: E731
    repair = ask("Why did the first attempt fail?")
    assert "Missing CNOT" in repair["text"] and "Attempt 1 failed" in repair["text"]
    assert repair["call"]["model"] == "offline answer rules"
    assert "maximally entangled" in ask("Is it entangled?")["text"]
    assert "better" in ask("How good must the hardware be?")["text"]
    assert "Readout errors" in ask("Which noise costs the most?")["text"]
    assert "limit" in ask("Can I trust the verification?")["text"]
    assert "can't answer that offline" in ask("What is the capital of France?")["text"]


def test_network_questions(example):
    spec = parse_spec(example("network_satellite"))
    ctx = ask_context(spec, run_network_agent(spec).model_dump(mode="json"))
    assert "bottleneck" in offline_answer("Where is the bottleneck?", ctx)
    assert "bit/s" in offline_answer("What key rate do we get?", ctx)
    assert "applied" in offline_answer("What fixes did you try?", ctx)


def test_html_report(example):
    job = _finished(example("bell"), noise="realistic", demo_mode=True, demo_fault="missing_cnot")
    resp = client.get(f"/api/jobs/{job}/report")
    assert resp.status_code == 200 and "attachment" in resp.headers["content-disposition"]
    page = resp.text
    assert page.startswith("<!doctype html>") and "Verified" in page and "data:image/png;base64," in page
    assert "What the agent repaired" in page and "Missing" in page and "Entanglement" in page
    net = _finished(example("network_fiber_chain"))
    assert "Fixes the agent tried" in client.get(f"/api/jobs/{net}/report").text
    assert client.get("/api/jobs/nope/report").status_code == 404


def test_ask_errors():
    assert client.post("/api/jobs/nope/ask", json={"question": "hi"}).status_code == 404


class FakeClient:
    def __init__(self, reply):
        self.reply, self.requests = reply, []

    def chat(self, model, messages, **kw):
        self.requests.append(messages)
        return self.reply, False


def test_live_answer_sends_the_facts_and_the_question(example):
    spec = parse_spec(example("network_fiber_chain"))
    ctx = ask_context(spec, run_network_agent(spec).model_dump(mode="json"))
    fake = FakeClient("The 200 km middle span is the bottleneck.")
    out = MetaReasoningModel(load_settings(), fake).answer("Where is the bottleneck?", ctx)  # type: ignore[arg-type]
    assert out.call.provider == "meta" and out.call.role == "answer" and "200 km" in out.text
    user = fake.requests[0][1]["content"]
    assert "Question: Where is the bottleneck?" in user and json.loads(user.split("Facts about this run:\n")[1]
                                                                        .split("\n\nQuestion:")[0])["kind"] == "network"
