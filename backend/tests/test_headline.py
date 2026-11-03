"""The opening scene's figures are rebuilt from the stored results, and its replayed run passes the real verifier."""

import json

from fastapi.testclient import TestClient

from qcanvas import EXAMPLES_DIR
from qcanvas.api.app import app
from qcanvas.headline import MODELS, headline


def _load(name: str):
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def test_stats_match_the_stored_results():
    stats = {s["source"]: s for s in headline()["stats"]}
    missions = _load("mission_benchmark.json")
    assert stats["examples/mission_benchmark.json"]["value"] == f"{sum(m['status'] == 'done' for m in missions)}/{len(missions)}"
    proof = _load("proofsheet_benchmark.json")["totals"]
    assert stats["examples/proofsheet_benchmark.json"]["value"] == f"{proof['passed']}/{proof['passed'] + proof['failed']}"
    assert proof["failed"] == 0
    ibm = _load("ibm_experiments.json")
    if not ibm["rehearsal"]:
        assert float(stats["examples/ibm_experiments.json"]["value"]) == round(ibm["teleport"]["feed_forward"]["average"], 3)
        assert float(stats["examples/ibm_experiments.json"]["value"]) > ibm["teleport"]["classical_limit"]
    assert stats["health"]["value"] == str(len(MODELS))


def test_models_listed_are_the_configured_ones():
    from qcanvas.adapters.config import load_settings

    configured = set(load_settings().public()["models"].values())
    assert len(configured) == len(MODELS)


def test_scene_replays_a_verified_ghz_run():
    scene = headline()["scene"]
    assert scene["verified"] is True
    assert [o["key"] for o in scene["outcomes"]] == [format(i, "03b") for i in range(8)]
    assert abs(sum(o["measured"] for o in scene["outcomes"]) - 1) < 1e-9
    top = sorted(scene["outcomes"], key=lambda o: -o["measured"])[:2]
    assert {o["key"] for o in top} == {"000", "111"}
    assert len(scene["segments"]) == 8 and {s["concept"] for s in scene["segments"]} == {"gate box", "dot", "circle", "meter"}


def test_endpoint():
    r = TestClient(app).get("/api/headline")
    assert r.status_code == 200
    assert len(r.json()["stats"]) >= 3
