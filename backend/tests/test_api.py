"""P6: API integration tests with FastAPI's TestClient (mock provider)."""

from __future__ import annotations

import io
import json
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from qcanvas import EXAMPLES_DIR
from qcanvas.api.app import app

client = TestClient(app)


def wait_for(job_id: str, timeout: float = 120) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.3)
    raise AssertionError("job did not finish")


def test_health_reports_mode():
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["mode"] == "mock"
    assert "api_key" not in json.dumps(body)


def test_examples():
    body = client.get("/api/examples").json()
    assert {s["id"] for s in body["specs"]} >= {"bell", "ghz3", "network_satellite"}
    assert len(body["images"]) == 3 and {f["name"] for f in body["faults"]} >= {"missing_cnot"}
    img = client.get(body["images"][0]["url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert client.get("/api/examples/images/..%2F..%2Fsecret.png").status_code == 404


def test_validate(example):
    bad = client.post("/api/spec/validate", json={"spec": example("invalid_circuit")}).json()
    assert not bad["valid"] and any("out of range" in i["message"] for i in bad["issues"])
    good = client.post("/api/spec/validate", json={"spec": example("bell")}).json()
    assert good["valid"]


def test_image_job_returns_overlay():
    png = (EXAMPLES_DIR / "images" / "bell_sketch.png").read_bytes()
    body = client.post("/api/jobs/image", files={"file": ("bell.png", png, "image/png")}).json()
    assert body["kind"] == "circuit" and body["valid"]
    assert body["width"] == 1400 and any(o["linked_to"] == "operations[1]" for o in body["overlay"])
    assert [c["provider"] for c in body["calls"]] == ["mock", "mock", "mock"]


def test_unknown_image_in_mock_mode_is_honest():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="JPEG")
    resp = client.post("/api/jobs/image", files={"file": ("x.jpg", buf.getvalue(), "image/jpeg")})
    assert resp.status_code == 422 and "bundled sample sketches" in resp.json()["detail"]


def test_invalid_spec_job_rejected(example):
    resp = client.post("/api/jobs/spec", json={"spec": example("invalid_circuit")})
    assert resp.status_code == 422
    assert resp.json()["detail"]["issues"]


@pytest.mark.slow
def test_demo_job_streams_failure_and_repair(example):
    resp = client.post("/api/jobs/spec", json={"spec": example("bell"), "options": {
        "noise": "realistic", "demo_mode": True, "demo_fault": "missing_cnot", "pace_s": 0}})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    events = []
    with client.stream("GET", f"/api/jobs/{job_id}/events") as stream:
        name = None
        for line in stream.iter_lines():
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and name == "log":
                events.append(json.loads(line[5:]))
            elif line.startswith("data:") and name == "end":
                break
    steps = [(e["step"], e["status"]) for e in events]
    assert ("inject", "warn") in steps and ("diagnose", "fail") in steps and ("repair", "ok") in steps
    assert ("done", "ok") in steps and ("explain", "ok") in steps and ("diagram", "ok") in steps
    body = wait_for(job_id)
    result = body["result"]
    assert body["status"] == "done" and result["verified"] and len(result["attempts"]) == 2
    assert "entangle" in result["explanation"]["text"]
    assert result["diagram"]["image_b64"] and result["exact_diagram"]["image_b64"]


def test_missing_job_404():
    assert client.get("/api/jobs/nope").status_code == 404
