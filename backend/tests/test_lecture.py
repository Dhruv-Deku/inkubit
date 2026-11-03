"""The lecture checker: exact claim checks, the board timeline, the sample's record, the offline run and the API."""

import hashlib
import time

import pytest
from fastapi.testclient import TestClient

from inkubit import lecture
from inkubit.adapters.base import ModelCall, Track, TrackResult

GHZ = {"kind": "circuit", "version": "1.0", "num_qubits": 3, "num_clbits": 3,
       "operations": [{"gate": "H", "targets": [0]}, {"gate": "CX", "controls": [0], "targets": [1]},
                      {"gate": "CX", "controls": [1], "targets": [2]}],
       "measurements": [{"qubit": q, "clbit": q} for q in range(3)], "metadata": {"title": "t"}}


def claim(kind, qubits, **kw):
    return {"kind": kind, "qubits": qubits, "outcome": kw.get("outcome", ""), "value": kw.get("value", -1),
            "outcomes": kw.get("outcomes", []), "state": kw.get("state", "none")}


def test_probability_claims_are_exact_and_respect_qubit_order():
    assert lecture.check_claim(GHZ, [0], claim("probability", [0], outcome="1", value=0.5))["verdict"] == "true"
    assert lecture.check_claim(GHZ, [0], claim("probability", [0], outcome="1", value=0.6))["verdict"] == "false"
    # H on q0 only: q0 reads 1 half the time, q1 never; the outcome's first bit is the first listed qubit
    assert lecture.check_claim(GHZ, [0], claim("probability", [0, 1], outcome="10", value=0.5))["verdict"] == "true"
    assert lecture.check_claim(GHZ, [0], claim("probability", [1, 0], outcome="01", value=0.5))["verdict"] == "true"
    assert lecture.check_claim(GHZ, [], claim("probability", [0, 1, 2], outcome="000", value=1))["verdict"] == "true"


def test_outcome_sets_entanglement_and_named_states():
    ghz = [0, 1, 2]
    assert lecture.check_claim(GHZ, ghz, claim("outcomes", [0, 1, 2], outcomes=["000", "111"]))["verdict"] == "true"
    out = lecture.check_claim(GHZ, ghz, claim("outcomes", [0, 1, 2], outcomes=["001", "010", "100"]))
    assert out["verdict"] == "false" and out["numbers"]["possible"] == ["000", "111"]
    assert lecture.check_claim(GHZ, [0, 1], claim("entangled", [0, 1]))["verdict"] == "true"
    assert lecture.check_claim(GHZ, [0, 1], claim("entangled", [2]))["verdict"] == "false"
    assert lecture.check_claim(GHZ, [0, 1], claim("not_entangled", [2]))["verdict"] == "true"
    w = lecture.check_claim(GHZ, ghz, claim("state", [0, 1, 2], state="W"))
    assert w["verdict"] == "false" and "GHZ" in w["detail"] and w["numbers"]["GHZ"] == pytest.approx(1)
    assert lecture.check_claim(GHZ, ghz, claim("state", [0, 1, 2], state="GHZ"))["verdict"] == "true"
    assert lecture.check_claim(GHZ, [0, 1], claim("state", [0, 1], state="Bell"))["verdict"] == "true"
    assert lecture.check_claim(GHZ, [0, 1], claim("state", [2], state="zero"))["verdict"] == "true"


def test_claims_it_cannot_settle_are_said_to_be_unclear():
    for c in (claim("other", [0]), claim("probability", [5], outcome="1", value=0.5),
              claim("probability", [0], outcome="11", value=0.5), claim("outcomes", [0, 1], outcomes=["0"]),
              claim("probability", [0, 0], outcome="11", value=0.5)):
        assert lecture.check_claim(GHZ, [0], c)["verdict"] == "unclear"


def _tracks(*items):
    return TrackResult(width=1280, height=720, frames=100, fps=2, concepts=["square", "circle"],
                       call=ModelCall(provider="mock", model="t", role="track"),
                       tracks=[Track(id=i, concept="square", first_s=f, last_s=50, bbox=b) for i, f, b in items])


def test_each_operation_appears_when_all_of_its_tracked_parts_have():
    spec = {**GHZ, "operations": [
        {"gate": "H", "targets": [0], "source": {"bbox": [240, 170, 360, 290]}},
        {"gate": "CX", "controls": [0], "targets": [1], "source": {"bbox": [480, 200, 560, 420], "segment_id": "c1"}}]}
    tr = _tracks(("s0", 7.0, (245, 175, 355, 284)), ("d0", 13.0, (506, 216, 534, 244)), ("c1", 14.5, (480, 342, 559, 416)),
                 ("far", 1.0, (900, 600, 950, 650)))
    times = lecture.op_times(spec, tr, None)
    assert [t["appears"] for t in times] == [7.0, 14.5]
    assert set(times[1]["tracks"]) == {"d0", "c1"}
    board = lecture.versions(times)
    assert [(v["time"], v["ops"]) for v in board] == [(0.0, []), (7.0, [0]), (14.5, [0, 1])]


def test_the_board_a_claim_is_checked_against_must_have_been_there_during_the_turn():
    board = [{"index": 0, "time": 0.0, "ops": []}, {"index": 1, "time": 7.0, "ops": [0]},
             {"index": 2, "time": 30.0, "ops": [0, 1]}]
    turn = {"start": 26.7, "end": 29.0}
    assert lecture._allowed_version(board, turn, 1) == 1
    assert lecture._allowed_version(board, turn, 2) == 2  # drawn within a second of the turn's end
    assert lecture._allowed_version(board, {"start": 10, "end": 12}, 2) == 1  # not yet drawn: the board at the start
    assert lecture._allowed_version(board, turn, 0) == 1  # long gone
    assert lecture._allowed_version(board, turn, "x") == 1


def test_the_sample_record_matches_its_video():
    rec = lecture._sample()
    assert hashlib.sha256(lecture.sample_video()).hexdigest() == rec["sha256"]
    assert [e["appears"] for e in rec["elements"]] == sorted(e["appears"] for e in rec["elements"])
    assert {t["speaker"] for t in rec["turns"]} == {"Teacher", "Student"}
    with pytest.raises(RuntimeError):
        lecture.sample_record("0" * 64)


def test_media_cuts_sound_clip_and_frames_and_refuses_what_it_cannot_check():
    m = lecture.Media(lecture.sample_video())
    assert abs(m.duration - lecture._sample()["duration"]) < 0.3
    assert m.wav[:4] == b"RIFF" and (m.width, m.height) == (1280, 720)
    assert len(m.grey) == pytest.approx(m.duration * lecture.TRACK_FPS, abs=2)
    with pytest.raises(lecture.LectureError):
        lecture.Media(b"not a video at all")


def test_pixels_find_when_a_part_was_drawn_without_any_model():
    m = lecture.Media(lecture.sample_video())
    rec = lecture._sample()
    for e in rec["elements"][1:]:
        box = e["segments"][-1]["bbox"]
        found = lecture._pixels_first(m, tuple(box))
        assert found is not None and abs(found - e["appears"]) <= 1.0, (e["id"], found, e["appears"])


def test_the_sample_checks_offline_and_catches_both_speakers_mistakes(monkeypatch):
    monkeypatch.setenv("INKUBIT_MODEL_PROVIDER", "mock")
    monkeypatch.setenv("META_API_KEY", "")
    from inkubit.adapters.registry import get_models

    s = lecture.Session("sample")
    r = lecture.run(s, lecture.sample_video(), get_models(), True)
    assert r["offline"] and r["source"] == "sample"
    assert r["tally"] == {"true": 7, "false": 3, "unclear": 0}
    wrong = {(c["speaker"], c["quote"]) for c in r["claims"] if c["verdict"] == "false"}
    assert ("B", "And the third qubit is entangled with them too, right?") in wrong
    assert ("A", "This is the W state") in wrong
    assert [o["appears"] for o in r["ops"]] == [e["appears"] for e in lecture._sample()["elements"][1:4]]
    assert all(st["status"] in ("done", "offline") for st in s.steps)
    assert len(r["notes"]["corrections"]) == 3 and r["figure"]["image"].startswith("data:image/png;base64,")


def test_offline_refuses_an_upload_it_has_no_record_for(monkeypatch):
    monkeypatch.setenv("INKUBIT_MODEL_PROVIDER", "mock")
    monkeypatch.setenv("META_API_KEY", "")
    from inkubit.adapters.registry import get_models

    import subprocess

    import imageio_ffmpeg

    other = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", str(lecture.LECTURE_DIR / "lecture.mp4"),
                            "-t", "5", "-c:v", "libx264", "-c:a", "aac", "-f", "mp4", "-movflags", "frag_keyframe+empty_moov", "-"],
                           capture_output=True, check=True).stdout
    with pytest.raises(lecture.LectureError):
        lecture.run(lecture.Session("upload"), other, get_models(), False)


def test_api_runs_the_sample(monkeypatch):
    monkeypatch.setenv("INKUBIT_MODEL_PROVIDER", "mock")
    monkeypatch.setenv("META_API_KEY", "")
    from inkubit.api.app import app

    c = TestClient(app)
    meta = c.get("/api/lecture/sample").json()
    assert meta["video"] == "/api/lecture/sample.mp4"
    assert c.get(meta["video"]).headers["content-type"] == "video/mp4"
    lid = c.post("/api/lecture").json()["lecture_id"]
    for _ in range(300):
        view = c.get(f"/api/lecture/{lid}").json()
        if view["status"] != "running":
            break
        time.sleep(0.1)
    assert view["status"] == "done", view["error"]
    assert view["result"]["tally"]["false"] == 3
    assert c.get("/api/lecture/nope").status_code == 404


@pytest.mark.live
def test_live_models_check_the_sample():
    from inkubit.adapters.registry import get_models

    models = get_models()
    if not models.settings.has_key:
        pytest.skip("needs META_API_KEY")
    s = lecture.Session("sample")
    r = lecture.run(s, lecture.sample_video(), models, True)
    assert not r["offline"]
    roles = {c["role"]: c for c in r["calls"]}
    assert roles["diarize"]["provider"] == "meta" and roles["track"]["provider"] == "meta"
    assert {t["speaker"] for t in r["turns"]} >= {"A", "B"}
    wrong = [c for c in r["claims"] if c["verdict"] == "false"]
    assert any("W state" in c["quote"] for c in wrong)
    assert any("third qubit is entangled" in c["quote"] for c in wrong)
    assert [round(o["appears"]) for o in r["ops"]] == [7, 14, 30]
