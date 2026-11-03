"""Speech to text: Muse Voice Transcribe live, and an offline stand-in that says it cannot.

Request shape from docs/meta-api/api-reference_voice_transcribe.md: multipart
``request`` (JSON: model, audioEncoding WAV, mode PUSH_TO_TALK, keywords) and
``audio`` (RIFF/WAVE, mono 16-bit PCM at 16 or 24 kHz), answered with
``{"transcript", "audioDurationMs", ...}``. The browser records and encodes the
WAV itself, so the server never converts audio.
"""

from __future__ import annotations

import io
import time
import wave

from inkubit.adapters.base import ModelCall, SpeechModel, Transcript, Turn, TurnTranscript
from inkubit.adapters.config import Settings

MAX_SECONDS = 60
# Words the recogniser would otherwise mishear; the docs' `keywords` biasing exists for this.
KEYWORDS = ["qubit", "qubits", "Hadamard", "CNOT", "Toffoli", "Pauli", "GHZ", "Bell pair", "W state", "Grover",
            "Shor", "Bernstein-Vazirani", "Deutsch-Jozsa", "teleportation", "superdense coding", "phase estimation",
            "entangle", "satellite", "repeater", "fiber", "ground station", "kilometers"]


class AudioError(ValueError):
    """The upload is not audio the transcription endpoint accepts."""


def check_wav(data: bytes) -> float:
    """Validate a mono 16-bit PCM WAV at 16 or 24 kHz; returns its length in seconds."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            channels, width, rate, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    except (wave.Error, EOFError) as err:
        raise AudioError(f"not a WAV file ({err})") from None
    if channels != 1 or width != 2 or rate not in (16000, 24000):
        raise AudioError(f"needs mono 16-bit PCM at 16 or 24 kHz, got {channels} channel(s), {8 * width}-bit, {rate} Hz")
    seconds = frames / rate
    if seconds < 0.2:
        raise AudioError("the recording is empty")
    if seconds > MAX_SECONDS:
        raise AudioError(f"keep it under {MAX_SECONDS} seconds")
    return seconds


class MetaSpeechModel(SpeechModel):
    def __init__(self, settings: Settings, client: object):
        self.settings, self.client, self.model = settings, client, settings.voice_model

    def transcribe(self, wav: bytes, keywords: list[str] | None = None) -> Transcript:
        check_wav(wav)
        start = time.perf_counter()
        request = {"model": self.model, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK",
                   "keywords": list(keywords if keywords is not None else KEYWORDS)}
        data, cached = self.client.post_multipart("/asr/transcribe", request, wav, "speech.wav", "audio/wav")
        text = str(data.get("transcript", "")).strip()
        return Transcript(text=text, duration_ms=int(data.get("audioDurationMs") or 0),
                          call=ModelCall(provider="meta", model=self.model, role="transcribe", cached=cached,
                                         latency_s=time.perf_counter() - start))

    def transcribe_turns(self, wav: bytes, keywords: list[str] | None = None, source: str = "") -> TurnTranscript:
        """``DIARIZATION`` mode: the buffered answer lists turns with ``startMs``, ``endMs`` and a ``speaker`` label
        (docs/meta-api/api-reference_voice_schemas.md). Turns with no words are dropped."""
        check_wav(wav)
        start = time.perf_counter()
        request = {"model": self.model, "audioEncoding": "WAV", "mode": "DIARIZATION",
                   "keywords": list(keywords if keywords is not None else KEYWORDS)}
        data, cached = self.client.post_multipart("/asr/transcribe", request, wav, "lecture.wav", "audio/wav")
        turns = [Turn(speaker=str(t.get("speaker") or "?"), start=round(int(t.get("startMs") or 0) / 1000, 2),
                      end=round(int(t.get("endMs") or 0) / 1000, 2), text=str(t.get("transcript", "")).strip())
                 for t in data.get("turns") or []]
        turns = [t for t in turns if t.text]
        return TurnTranscript(turns=turns, text=str(data.get("transcript", "")).strip(),
                              duration_ms=int(data.get("audioDurationMs") or 0),
                              call=ModelCall(provider="meta", model=self.model, role="diarize", cached=cached,
                                             latency_s=time.perf_counter() - start))


class MockSpeechModel(SpeechModel):
    """Offline there is no speech model, and making up a transcript would be dishonest."""

    def transcribe(self, wav: bytes, keywords: list[str] | None = None) -> Transcript:
        raise RuntimeError("offline mode cannot transcribe audio; the browser's own speech recognition is used instead")

    def transcribe_turns(self, wav: bytes, keywords: list[str] | None = None, source: str = "") -> TurnTranscript:
        """Offline, only the bundled sample lecture has turns: the script that made it recorded who said what."""
        from inkubit.lecture import sample_record

        rec = sample_record(source)
        speakers = {"Teacher": "A", "Student": "B"}
        turns = [Turn(speaker=speakers.get(t["speaker"], "?"), start=t["start"], end=t["end"], text=t["text"])
                 for t in rec["turns"]]
        return TurnTranscript(turns=turns, text=" ".join(t.text for t in turns), duration_ms=int(rec["duration"] * 1000),
                              call=ModelCall(provider="mock", model="the sample's own script", role="diarize"))
