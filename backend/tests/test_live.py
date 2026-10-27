"""Opt-in live smoke tests: one cheap real call per Meta model.

    cd backend && ../.venv/Scripts/python -m pytest -m live -q

Skipped automatically when no META_API_KEY is set. Responses are cached on disk,
so re-running costs nothing; set QCANVAS_LIVE_NOCACHE=1 to force fresh calls.
"""

from __future__ import annotations

import base64
import os

import pytest

from qcanvas import EXAMPLES_DIR
from qcanvas.adapters.config import load_settings
from qcanvas.adapters.meta_client import MetaClient
from qcanvas.adapters.sam_parse import parse_sam_output

pytestmark = pytest.mark.live
USE_CACHE = os.environ.get("QCANVAS_LIVE_NOCACHE") != "1"


@pytest.fixture(scope="module")
def client() -> MetaClient:
    return MetaClient(load_settings())


def test_muse_spark_chat(client):
    settings = load_settings()
    payload = {"model": settings.reasoning_model, "reasoning_effort": "low", "max_completion_tokens": 400,
               "messages": [{"role": "user", "content": "Reply with the single word OK."}]}
    data, _ = client.post("/chat/completions", payload, use_cache=USE_CACHE)
    assert "ok" in data["choices"][0]["message"]["content"].lower()


def test_sam_segments_sample_sketch(client):
    image = (EXAMPLES_DIR / "images" / "bell_sketch.png").read_bytes()
    url = "data:image/png;base64," + base64.b64encode(image).decode()
    text, _ = client.post_stream_text("/responses", {
        "model": load_settings().segment_model, "metadata": {"include_confidence": "true"},
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "circle"}, {"type": "input_image", "image_url": url}]}],
    }, use_cache=USE_CACHE)
    assert isinstance(parse_sam_output(text), list)


def test_muse_image_generates(client):
    data, _ = client.post("/images/generations", {
        "model": load_settings().image_model, "prompt": "A single black circle on a white background.",
        "n": 1, "size": "1024x1024", "response_format": "b64_json", "output_format": "png",
        "reasoning_strength": "low",
    }, use_cache=USE_CACHE)
    assert base64.b64decode(data["data"][0]["b64_json"])[:4] == b"\x89PNG"
