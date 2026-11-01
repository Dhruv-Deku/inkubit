"""Public mode: model-written code is never executed, and billed calls stop at the daily cap."""

from __future__ import annotations

import pytest

from qcanvas.adapters.config import load_settings
from qcanvas.adapters.meta_client import Budget, MetaAPIError


def test_public_mode_switches_to_template_code_and_a_cap(monkeypatch):
    monkeypatch.setenv("QCANVAS_PUBLIC", "1")
    monkeypatch.delenv("QCANVAS_CODE_BACKEND", raising=False)
    monkeypatch.delenv("QCANVAS_DAILY_CALLS", raising=False)
    s = load_settings()
    assert s.public_mode and s.code_backend == "template" and s.daily_calls == 300
    monkeypatch.setenv("QCANVAS_PUBLIC", "0")
    s = load_settings()
    assert not s.public_mode and s.code_backend == "api" and s.daily_calls == 0


def test_template_backend_uses_our_own_code_generator(monkeypatch):
    from qcanvas.adapters.mock_code import MockCodeModel
    from qcanvas.adapters.registry import _metas

    monkeypatch.setenv("QCANVAS_PUBLIC", "1")
    monkeypatch.setenv("META_API_KEY", "test-key-not-used")
    monkeypatch.setenv("QCANVAS_MODEL_PROVIDER", "meta")
    models = _metas(load_settings())
    assert isinstance(models["code"], MockCodeModel)


def test_budget_stops_at_the_cap():
    b = Budget()
    for _ in range(3):
        b.take(3)
    assert b.left(3) == 0
    with pytest.raises(MetaAPIError, match="daily budget"):
        b.take(3)
    b.take(0)  # no cap: never stops


def test_hardware_endpoint_is_404_until_a_real_run(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import qcanvas.api.app as appmod

    monkeypatch.setattr(appmod, "EXAMPLES_DIR", tmp_path)
    assert TestClient(appmod.app).get("/api/hardware").status_code == 404
