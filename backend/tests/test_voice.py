"""Muse Voice Transcribe: WAV checks, the live adapter's request, and the endpoint's honest refusals."""

from __future__ import annotations

import io
import math
import struct
import wave

import pytest
from fastapi.testclient import TestClient

from qcanvas.adapters.config import load_settings
from qcanvas.adapters.voice import KEYWORDS, AudioError, MetaSpeechModel, MockSpeechModel, check_wav
from qcanvas.api.app import app


def make_wav(seconds: float = 1.0, rate: int = 16000, channels: int = 1, width: int = 2) -> bytes:
    n = int(seconds * rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        if width == 2:
            frames = b"".join(struct.pack("<h", int(8000 * math.sin(i / 8))) * channels for i in range(n))
        else:
            frames = bytes(n * channels * width)
        w.writeframes(frames)
    return buf.getvalue()


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def post_multipart(self, path, request, audio, filename, mime, use_cache=True):
        self.calls.append((path, request, audio, filename, mime))
        return self.reply, False


def test_check_wav_accepts_16_and_24_khz_mono_pcm():
    assert check_wav(make_wav(1.5)) == pytest.approx(1.5)
    assert check_wav(make_wav(0.5, rate=24000)) == pytest.approx(0.5)


@pytest.mark.parametrize("data, needle", [
    (b"not audio at all", "not a WAV"),
    (make_wav(1, channels=2), "2 channel"),
    (make_wav(1, rate=44100), "44100 Hz"),
    (make_wav(1, width=1), "8-bit"),
    (make_wav(0.05), "empty"),
    (make_wav(61, rate=16000), "under 60"),
], ids=["junk", "stereo", "44k", "8bit", "empty", "too-long"])
def test_check_wav_rejects_what_the_endpoint_cannot_take(data, needle):
    with pytest.raises(AudioError, match=needle):
        check_wav(data)


def test_live_adapter_sends_push_to_talk_wav_with_quantum_keywords():
    fake = FakeClient({"transcript": "  make a GHZ state on three qubits  ", "audioDurationMs": 4640})
    wav = make_wav(1)
    out = MetaSpeechModel(load_settings(), fake).transcribe(wav)
    assert out.text == "make a GHZ state on three qubits" and out.duration_ms == 4640
    assert out.call.model == "muse-voice-transcribe-1.0" and out.call.role == "transcribe" and not out.call.cached
    path, request, audio, filename, mime = fake.calls[0]
    assert path == "/asr/transcribe" and audio == wav and mime == "audio/wav"
    assert request["audioEncoding"] == "WAV" and request["mode"] == "PUSH_TO_TALK"
    assert "GHZ" in request["keywords"] and request["keywords"] == KEYWORDS


def test_mock_never_makes_up_a_transcript():
    with pytest.raises(RuntimeError, match="cannot transcribe"):
        MockSpeechModel().transcribe(make_wav(1))


def test_endpoint_checks_audio_before_anything_else():
    c = TestClient(app)
    r = c.post("/api/transcribe", files={"audio": ("x.wav", make_wav(1, rate=44100), "audio/wav")})
    assert r.status_code == 400 and "16 or 24 kHz" in r.json()["detail"]


def test_endpoint_refuses_offline_instead_of_guessing():
    c = TestClient(app)
    r = c.post("/api/transcribe", files={"audio": ("x.wav", make_wav(1), "audio/wav")})
    assert r.status_code == 409 and "offline" in r.json()["detail"]


def test_health_lists_the_voice_model():
    assert TestClient(app).get("/api/health").json()["models"]["voice"] == "muse-voice-transcribe-1.0"
