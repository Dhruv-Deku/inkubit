"""Results that take seconds to compute and depend only on the code, stored with the app so that a small server (a
free host with a tenth of a CPU) answers at once instead of spending minutes on them after every wake-up.

scripts/precompute.py rebuilds the files; tests/test_precomputed.py checks they still equal a fresh computation, so
they cannot go stale silently.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

DIR = Path(__file__).parent / "data" / "precomputed"
M = TypeVar("M", bound=BaseModel)


def load(name: str, model: type[M]) -> M | None:
    path = DIR / f"{name}.json"
    return model.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def load_raw(name: str) -> Any | None:
    path = DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save(name: str, value: BaseModel | Any) -> Path:
    DIR.mkdir(parents=True, exist_ok=True)
    path = DIR / f"{name}.json"
    text = value.model_dump_json() if isinstance(value, BaseModel) else json.dumps(value)
    path.write_text(text, encoding="utf-8")
    return path
