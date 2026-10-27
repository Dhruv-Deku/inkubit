"""JSON Schema export for specs (``spec/schema.json``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from qcanvas.spec.models import SPEC_VERSION, CircuitSpec, NetworkSpec, Spec

SCHEMA_PATH = Path(__file__).with_name("schema.json")


def spec_json_schema() -> dict[str, Any]:
    """The full discriminated-union schema for any spec."""
    schema = TypeAdapter(Spec).json_schema(by_alias=True)
    schema["$id"] = f"https://q-canvas.local/spec/{SPEC_VERSION}/schema.json"
    schema["title"] = f"Q-Canvas spec v{SPEC_VERSION}"
    return schema


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            name = node["$ref"].split("/")[-1]
            return _inline_refs(defs[name], defs)
        return {k: _inline_refs(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


def kind_schema(kind: str) -> dict[str, Any]:
    """A self-contained (no ``$ref``) schema for one spec kind.

    Used for model structured output, where a plain-object root is safest.
    """
    model = CircuitSpec if kind == "circuit" else NetworkSpec
    raw = model.model_json_schema(by_alias=True)
    return _inline_refs(raw, raw.get("$defs", {}))


def write_schema(path: Path = SCHEMA_PATH) -> Path:
    """Write the schema file and return its path."""
    path.write_text(json.dumps(spec_json_schema(), indent=2) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    print(write_schema())
