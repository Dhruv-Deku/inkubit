"""Shared fixtures. Tests never make live model calls unless marked ``live``."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from qcanvas import EXAMPLES_DIR

SPECS_DIR = EXAMPLES_DIR / "specs"


def load_example(name: str) -> dict[str, Any]:
    """Load an example spec as a dict."""
    return json.loads((SPECS_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _force_mock_provider(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every non-live test runs against the deterministic mock adapters."""
    if "live" not in request.keywords:
        monkeypatch.setenv("QCANVAS_MODEL_PROVIDER", "mock")
        monkeypatch.setenv("QCANVAS_ALLOW_FALLBACK", "0")


@pytest.fixture
def specs_dir() -> Path:
    return SPECS_DIR


@pytest.fixture
def example() -> Any:
    return load_example


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("QCANVAS_LIVE_OK") == "1":
        return
    from qcanvas.adapters.config import load_settings  # reads .env, like the app

    has_key = load_settings().has_key
    for item in items:
        if "live" in item.keywords and not has_key:
            item.add_marker(pytest.mark.skip(reason="no META_API_KEY set"))
