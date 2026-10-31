"""Runtime settings for model adapters, read from the environment and ``.env``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv

from qcanvas import BACKEND_DIR, PROJECT_DIR

# Defaults are model IDs documented in docs/meta-api/models.md.
DEFAULT_REASONING_MODEL = "muse-spark-1.3"
DEFAULT_CODE_MODEL = "muse-spark-1.3"
DEFAULT_IMAGE_MODEL = "muse-image-1.0"
DEFAULT_SEGMENT_MODEL = "sam-3.1"
DEFAULT_DEEP_MODEL = "muse-wonder-1.0"  # docs/meta-api/models.md (Muse Wonder, preview)
DEFAULT_VOICE_MODEL = "muse-voice-transcribe-1.0"  # docs/meta-api/api-reference_voice_transcribe.md
META_BASE_URL = "https://api.meta.ai/v1"

Provider = Literal["meta", "mock"]


@dataclass(frozen=True)
class Settings:
    """Adapter configuration. ``api_key`` is never logged or serialised."""

    provider: Provider
    allow_fallback: bool
    reasoning_model: str
    code_model: str
    image_model: str
    segment_model: str
    base_url: str
    voice_model: str
    cache_dir: str
    code_backend: str
    api_key: str | None = None
    deep_model: str = DEFAULT_DEEP_MODEL

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)

    def public(self) -> dict[str, object]:
        """Settings safe to show in the UI (no key)."""
        return {
            "provider": self.provider,
            "allow_fallback": self.allow_fallback,
            "has_key": self.has_key,
            "models": {
                "reasoning": self.reasoning_model,
                "code": self.code_model,
                "image": self.image_model,
                "segmentation": self.segment_model,
                "voice": self.voice_model,
                "deep": self.deep_model,
            },
            "code_backend": self.code_backend,
        }


_loaded = False


def load_settings() -> Settings:
    """Read settings fresh from the environment (``.env`` is loaded once, never overriding)."""
    global _loaded
    if not _loaded:
        load_dotenv(PROJECT_DIR / ".env", override=False)
        _loaded = True
    provider = os.environ.get("QCANVAS_MODEL_PROVIDER", "mock").strip().lower()
    if provider not in ("meta", "mock"):
        provider = "mock"
    return Settings(
        provider=provider,  # type: ignore[arg-type]
        allow_fallback=os.environ.get("QCANVAS_ALLOW_FALLBACK", "1").strip() == "1",
        reasoning_model=os.environ.get("QCANVAS_REASONING_MODEL", DEFAULT_REASONING_MODEL),
        code_model=os.environ.get("QCANVAS_CODE_MODEL", DEFAULT_CODE_MODEL),
        image_model=os.environ.get("QCANVAS_IMAGE_MODEL", DEFAULT_IMAGE_MODEL),
        segment_model=os.environ.get("QCANVAS_SEGMENT_MODEL", DEFAULT_SEGMENT_MODEL),
        base_url=os.environ.get("QCANVAS_META_BASE_URL", META_BASE_URL).rstrip("/"),
        voice_model=os.environ.get("QCANVAS_VOICE_MODEL", DEFAULT_VOICE_MODEL),
        cache_dir=os.environ.get("QCANVAS_CACHE_DIR", str(BACKEND_DIR / ".qcanvas_cache")),
        code_backend=os.environ.get("QCANVAS_CODE_BACKEND", "api"),
        api_key=(os.environ.get("META_API_KEY") or os.environ.get("MODEL_API_KEY") or None),
        deep_model=os.environ.get("QCANVAS_DEEP_MODEL", DEFAULT_DEEP_MODEL),
    )
