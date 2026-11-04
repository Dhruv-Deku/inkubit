"""The quantum internet planner: route physics, the offline designer, the exhaustive search, the plan loop and the API."""

import time

import pytest
from fastapi.testclient import TestClient

from inkubit import qnet


def test_great_circle_and_arc_points():
    km = qnet.great_circle(qnet.CITIES["london"][1:], qnet.CITIES["paris"][1:])
    assert 330 < km < 360
    pts = qnet.arc_points(qnet.CITIES["london"][1:], qnet.CITIES["new_york"][1:], 10)
    assert len(pts) == 11 and pts[0] == pytest.approx(qnet.CITIES["london"][1:], abs=1e-3)
    assert pts[-1] == pytest.approx(qnet.CITIES["new_york"][1:], abs=1e-3)


def test_fiber_loses_its_key_with_distance():
    near = qnet.evaluate_route(qnet.Route(a="london", b="paris", kind="fiber"))
    far = qnet.evaluate_route(qnet.Route(a="delhi", b="mumbai", kind="fiber"))
    assert near["key_rate_bps"] > 0 and near["loss_db"] == pytest.approx(0.2 * near["distance_km"], rel=1e-3)
    assert far["key_rate_bps"] == 0 and "no secret key" in far["limit"]


def test_repeaters_need_better_memories_than_todays():
    fiber = qnet.evaluate_route(qnet.Route(a="london", b="paris", kind="fiber"))["key_rate_bps"]
    today = qnet.evaluate_route(qnet.Route(a="london", b="paris", kind="repeaters", repeaters=3))
    future = qnet.evaluate_route(qnet.Route(a="london", b="paris", kind="repeaters", repeaters=3, memory_ms=10_000))
    assert today["key_rate_bps"] == 0 and "10 ms memories" in today["limit"]
    assert future["key_rate_bps"] > 3 * fiber
    assert len(future["repeater_points"]) == 3


def test_the_offline_designer_reads_cities_in_order():
    assert qnet._mentioned("Connect Delhi, Mumbai and London please") == ["delhi", "mumbai", "london"]
    d = qnet.rule_of_thumb(["geneva", "zurich", "delhi"])
    assert [r.kind for r in d.routes] == ["repeaters", "satellite"]


def test_model_routes_are_sanitised():
    d = qnet._routes_from({"routes": [{"a": "london", "b": "paris", "kind": "repeaters", "repeaters": 40, "satellite": "none"},
                                      {"a": "atlantis", "b": "paris", "kind": "fiber"},
                                      {"a": "delhi", "b": "london", "kind": "satellite", "satellite": "none"}],
                           "why": "x"}, "Muse Spark", "why")
    assert [(r.kind, r.repeaters, r.satellite) for r in d.routes] == [("repeaters", 12, None), ("satellite", 0, "speqtre")]
    with pytest.raises(ValueError):
        qnet._routes_from({"routes": [{"a": "atlantis", "b": "x", "kind": "fiber"}]}, "Muse Spark", "why")


def test_satellite_routes_use_the_real_orbit_and_a_trusted_node():
    ev = qnet.evaluate_route(qnet.Route(a="london", b="new_york", kind="satellite", satellite="speqtre"))
    assert ev["satellite_name"] == "SpeQtre" and ev["passes_a"] >= 0 and ev["passes_b"] >= 0
    assert ev["bits_per_day"] == pytest.approx(ev["key_rate_bps"] * 86400)
    assert ev["key_rate_bps"] == 0 or (ev["passes_a"] and ev["passes_b"])


def test_the_exhaustive_search_is_at_least_as_good_as_every_option():
    route, best = qnet.best_route("london", "paris")
    for opt in (qnet.Route(a="london", b="paris", kind="fiber"), qnet.Route(a="london", b="paris", kind="repeaters", repeaters=2)):
        assert best["key_rate_bps"] >= qnet.evaluate_route(opt)["key_rate_bps"]


def test_a_design_is_scored_by_its_weakest_pair():
    ev = qnet.evaluate(qnet.Design(routes=[qnet.Route(a="london", b="paris", kind="fiber"),
                                           qnet.Route(a="delhi", b="mumbai", kind="fiber")]))
    assert ev["score_bps"] == 0 and ev["weakest"] == {"a": "delhi", "b": "mumbai"}


def test_offline_plan_runs_every_step(monkeypatch):
    monkeypatch.setenv("INKUBIT_MODEL_PROVIDER", "mock")
    monkeypatch.setenv("META_API_KEY", "")
    from inkubit.adapters.registry import get_models

    s = qnet.Session("Link Geneva, Zurich and Munich")
    qnet.run(s, get_models())
    v = s.view()
    assert [st["status"] for st in v["steps"]] == ["offline", "done", "offline", "offline", "done", "done"]
    r = v["result"]
    assert r["first"]["by"] == "rule of thumb" and r["best"]["score_bps"] >= r["first"]["score_bps"]
    assert r["verdict"]["text"]
    with pytest.raises(ValueError):
        qnet.run(qnet.Session("somewhere nice"), get_models())


def test_sky_tracks_both_satellites():
    sky = qnet.sky(hours=0.5, step_s=60)
    assert {s["id"] for s in sky["satellites"]} == {"speqtre", "qube2"}
    for s in sky["satellites"]:
        assert len(s["track"]) == 30 and all(300 < h < 800 for _, _, h in s["track"])


def test_api(monkeypatch):
    monkeypatch.setenv("INKUBIT_MODEL_PROVIDER", "mock")
    monkeypatch.setenv("META_API_KEY", "")
    from inkubit.api.app import app

    c = TestClient(app)
    assert len(c.get("/api/qnet/cities").json()["cities"]) == len(qnet.CITIES)
    ev = c.post("/api/qnet/evaluate", json={"routes": [{"a": "london", "b": "paris", "kind": "fiber"}]}).json()
    assert ev["routes"][0]["key_rate_bps"] > 0
    assert c.post("/api/qnet/evaluate", json={"routes": [{"a": "atlantis", "b": "paris", "kind": "fiber"}]}).status_code == 422
    pid = c.post("/api/qnet/plan", json={"request": "Link Geneva and Zurich"}).json()["plan_id"]
    for _ in range(600):
        view = c.get(f"/api/qnet/plan/{pid}").json()
        if view["status"] != "running":
            break
        time.sleep(0.1)
    assert view["status"] == "done", view["error"]
    assert c.get("/api/qnet/plan/nope").status_code == 404
