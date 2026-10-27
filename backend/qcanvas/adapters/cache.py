"""On-disk cache of real model responses, keyed by a hash of the request.

Repeated runs (and demos) reuse responses instead of spending API credits.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def request_key(endpoint: str, payload: dict[str, Any]) -> str:
    """Stable SHA-256 of endpoint + canonical JSON payload."""
    blob = json.dumps({"endpoint": endpoint, "payload": payload}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class DiskCache:
    """A directory of ``<key>.json`` files."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> Any | None:
        """Return the cached value or None."""
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def put(self, key: str, value: Any) -> None:
        """Store a JSON-serialisable value."""
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value), encoding="utf-8")
        tmp.replace(path)
