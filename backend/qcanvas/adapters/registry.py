"""Pick meta or mock adapters from settings, with honest, labelled fallback.

``QCANVAS_MODEL_PROVIDER=meta`` uses Meta Model API. If a live call fails and
``QCANVAS_ALLOW_FALLBACK=1``, the mock answers instead and its result is
marked ``provider="mock-fallback"`` with the error, so the UI never presents a
mock answer as a Meta one. With fallback off, the error propagates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from qcanvas.adapters.base import CodeModel, ImageModel, ModelCall, ReasoningModel, SegmentationModel, SpeechModel
from qcanvas.adapters.config import Settings, load_settings

log = logging.getLogger("qcanvas.adapters")


class ModelUnavailable(RuntimeError):
    """A live model call failed and fallback is disabled."""


class _Unavailable:
    """Stands in for a meta adapter that could not be built (e.g. no key)."""

    def __init__(self, reason: str):
        self._reason = reason

    def __getattr__(self, name: str) -> Callable[..., Any]:
        def fail(*_a: Any, **_k: Any) -> Any:
            raise ModelUnavailable(self._reason)
        return fail


def _mark(result: Any, err: Exception) -> Any:
    msg = f"{type(err).__name__}: {err}"[:300]
    call = getattr(result, "call", None)
    if isinstance(result, tuple):
        call = next((x for x in result if isinstance(x, ModelCall)), None)
    if isinstance(call, ModelCall):
        call.provider = "mock-fallback"
        call.error = msg
    return result


class _WithFallback:
    """Calls ``primary``; on failure, optionally calls ``fallback`` and labels the result."""

    def __init__(self, primary: Any, fallback: Any, allow: bool, kind: str):
        self._primary, self._fallback, self._allow, self._kind = primary, fallback, allow, kind

    def __getattr__(self, name: str) -> Callable[..., Any]:
        primary_fn = getattr(self._primary, name)

        def call(*args: Any, **kwargs: Any) -> Any:
            try:
                return primary_fn(*args, **kwargs)
            except Exception as err:  # noqa: BLE001 - any live failure is reported, never hidden
                log.warning("live %s.%s failed: %s", self._kind, name, err)
                if not self._allow:
                    raise ModelUnavailable(f"{self._kind}.{name} failed: {err}") from err
                return _mark(getattr(self._fallback, name)(*args, **kwargs), err)
        return call


@dataclass
class Models:
    """The five adapters the app uses."""

    segmentation: SegmentationModel
    reasoning: ReasoningModel
    code: CodeModel
    image: ImageModel
    settings: Settings
    speech: SpeechModel


def _mocks() -> dict[str, Any]:
    from qcanvas.adapters.mock_code import MockCodeModel

    from qcanvas.adapters.voice import MockSpeechModel

    out: dict[str, Any] = {"code": MockCodeModel(), "speech": MockSpeechModel()}
    try:
        from qcanvas.adapters.mock_vision import MockImageModel, MockReasoningModel, MockSegmentationModel

        out.update(segmentation=MockSegmentationModel(), reasoning=MockReasoningModel(), image=MockImageModel())
    except ImportError:  # pragma: no cover - only during early milestones
        out.update(segmentation=_Unavailable("not built"), reasoning=_Unavailable("not built"),
                   image=_Unavailable("not built"))
    return out


def _metas(settings: Settings) -> dict[str, Any]:
    try:
        from qcanvas.adapters.meta_client import MetaClient
        from qcanvas.adapters.meta_code import MetaCodeModel

        client = MetaClient(settings)
    except Exception as err:  # noqa: BLE001
        reason = str(err)
        return {k: _Unavailable(reason) for k in ("segmentation", "reasoning", "code", "image", "speech")}
    from qcanvas.adapters.voice import MetaSpeechModel

    out: dict[str, Any] = {"code": MetaCodeModel(settings, client), "speech": MetaSpeechModel(settings, client)}
    if settings.code_backend == "muse-cli":
        from qcanvas.adapters.muse_cli import MuseCodeCliModel

        out["code"] = MuseCodeCliModel(settings, out["code"])
    try:
        from qcanvas.adapters.meta_vision import MetaImageModel, MetaReasoningModel, MetaSegmentationModel

        out.update(segmentation=MetaSegmentationModel(settings, client),
                   reasoning=MetaReasoningModel(settings, client), image=MetaImageModel(settings, client))
    except ImportError:  # pragma: no cover
        out.update(segmentation=_Unavailable("not built"), reasoning=_Unavailable("not built"),
                   image=_Unavailable("not built"))
    return out


def get_models(settings: Settings | None = None) -> Models:
    """Build the adapter set for the current settings."""
    settings = settings or load_settings()
    mocks = _mocks()
    if settings.provider == "mock":
        return Models(settings=settings, **mocks)
    metas = _metas(settings)
    wrapped = {k: _WithFallback(metas[k], mocks[k], settings.allow_fallback, k) for k in mocks}
    return Models(settings=settings, **wrapped)  # type: ignore[arg-type]
