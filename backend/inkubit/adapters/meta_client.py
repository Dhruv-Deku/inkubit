"""Minimal HTTP client for Meta Model API.

Endpoints, headers and payload shapes follow docs/meta-api (see SOURCES.md).
Responses are cached on disk by request hash. The API key is sent only in the
Authorization header and never logged.
"""

from __future__ import annotations

import os

import hashlib
import json
import logging
import random
import time
from typing import Any

import httpx

from inkubit.adapters.cache import DiskCache, request_key
from inkubit.adapters.config import Settings

log = logging.getLogger("inkubit.meta")
RETRY_STATUS = {429, 500, 502, 503, 504}


class MetaAPIError(RuntimeError):
    """A Meta Model API call failed (message is safe to show; no key inside)."""


class Budget:
    """Billed (uncached) calls per UTC day, shared by every client in the process. A hosted copy sets a cap so a
    burst of visitors cannot run up the bill; past it, calls fail and the labelled offline fallback answers."""

    def __init__(self) -> None:
        import threading

        self._lock = threading.Lock()
        self._day = ""
        self.used = 0

    def take(self, cap: int) -> None:
        from datetime import datetime, timezone

        with self._lock:
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if day != self._day:
                self._day, self.used = day, 0
            if cap and self.used >= cap:
                raise MetaAPIError(f"the daily budget of {cap} live model calls is used up; offline answers until "
                                   "midnight UTC")
            self.used += 1

    def left(self, cap: int) -> int | None:
        return None if not cap else max(0, cap - self.used)


BUDGET = Budget()


class MetaClient:
    """POSTs JSON to Meta Model API with retries and an on-disk response cache."""

    def __init__(self, settings: Settings, timeout_s: float = 120.0, max_retries: int = 3):
        if not settings.api_key:
            raise MetaAPIError("META_API_KEY is not set (add it to .env)")
        self._settings = settings
        self._key = settings.api_key
        self._timeout = float(os.environ.get("INKUBIT_HTTP_TIMEOUT") or timeout_s)  # a local model may need longer
        self._retries = max_retries
        self.cache = DiskCache(settings.cache_dir)

    def _headers(self, stream: bool = False) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        if stream:
            h["Accept"] = "text/event-stream"
        return h

    def post(self, path: str, payload: dict[str, Any], use_cache: bool = True) -> tuple[dict[str, Any], bool]:
        """POST ``payload`` to ``path`` (e.g. ``/chat/completions``). Returns (json, cached)."""
        key = request_key(path, payload)
        if use_cache:
            hit = self.cache.get(key)
            if hit is not None:
                return hit, True
        BUDGET.take(self._settings.daily_calls)
        url = self._settings.base_url + path
        last_error = "no attempt made"
        for attempt in range(self._retries + 1):
            try:
                resp = httpx.post(url, headers=self._headers(), json=payload, timeout=self._timeout)
            except httpx.HTTPError as err:
                last_error = f"network error: {type(err).__name__}"
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    if use_cache:
                        self.cache.put(key, data)
                    return data, False
                last_error = f"HTTP {resp.status_code}: {_error_message(resp)}"
                if resp.status_code not in RETRY_STATUS:
                    break
                wait = _retry_after(resp)
                if wait is not None and attempt < self._retries:
                    time.sleep(min(wait, 20.0))
                    continue
            if attempt < self._retries:
                time.sleep(min(2 ** attempt + random.random(), 20.0))
        log.warning("Meta API call to %s failed: %s", path, last_error)
        raise MetaAPIError(f"{path} failed: {last_error}")

    def post_multipart(self, path: str, request: dict[str, Any], audio: bytes, filename: str, mime: str,
                       use_cache: bool = True) -> tuple[dict[str, Any], bool]:
        """POST a ``request`` JSON part and an ``audio`` part (the transcription endpoint). Returns (json, cached)."""
        key = request_key(path + "#multipart", {"request": request, "audio_sha256": hashlib.sha256(audio).hexdigest()})
        if use_cache:
            hit = self.cache.get(key)
            if hit is not None:
                return hit, True
        BUDGET.take(self._settings.daily_calls)
        url = self._settings.base_url + path
        headers = {"Authorization": f"Bearer {self._key}", "Accept": "application/json"}
        files = {"request": (None, json.dumps(request), "application/json"), "audio": (filename, audio, mime)}
        last_error = "no attempt made"
        for attempt in range(self._retries + 1):
            try:
                resp = httpx.post(url, headers=headers, files=files, timeout=self._timeout)
            except httpx.HTTPError as err:
                last_error = f"network error: {type(err).__name__}"
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    if use_cache:
                        self.cache.put(key, data)
                    return data, False
                last_error = f"HTTP {resp.status_code}: {_error_message(resp)}"
                if resp.status_code not in RETRY_STATUS:
                    break
            if attempt < self._retries:
                time.sleep(min(2 ** attempt + random.random(), 20.0))
        log.warning("Meta API call to %s failed: %s", path, last_error)
        raise MetaAPIError(f"{path} failed: {last_error}")

    def post_stream_text(self, path: str, payload: dict[str, Any], use_cache: bool = True) -> tuple[str, bool]:
        """POST a streaming Responses request and return the concatenated output text."""
        body = {**payload, "stream": True}
        key = request_key(path + "#stream", body)
        if use_cache:
            hit = self.cache.get(key)
            if hit is not None:
                return hit["text"], True
        BUDGET.take(self._settings.daily_calls)
        url = self._settings.base_url + path
        last_error = "no attempt made"
        for attempt in range(self._retries + 1):
            try:
                parts: list[str] = []
                failed: str | None = None
                with httpx.stream("POST", url, headers=self._headers(stream=True), json=body,
                                  timeout=self._timeout) as resp:
                    if resp.status_code != 200:
                        resp.read()
                        last_error = f"HTTP {resp.status_code}: {_error_message(resp)}"
                        if resp.status_code not in RETRY_STATUS:
                            break
                        raise _Retry()
                    for line in resp.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[len("data: "):]
                        if data == "[DONE]":
                            break
                        event = json.loads(data)
                        etype = event.get("type")
                        if etype == "response.output_text.delta" and event.get("delta"):
                            parts.append(event["delta"])
                        elif etype in ("response.failed", "error"):
                            failed = json.dumps(event.get("response", event).get("error", event))[:300]
                if failed:
                    last_error = f"stream failed: {failed}"
                    raise _Retry()
                text = "".join(parts)
                if use_cache:
                    self.cache.put(key, {"text": text})
                return text, False
            except _Retry:
                pass
            except httpx.HTTPError as err:
                last_error = f"network error: {type(err).__name__}"
            if attempt < self._retries:
                time.sleep(min(2 ** attempt + random.random(), 20.0))
        log.warning("Meta API stream to %s failed: %s", path, last_error)
        raise MetaAPIError(f"{path} failed: {last_error}")

    def chat(self, model: str, messages: list[dict[str, Any]], *, schema: dict[str, Any] | None = None,
             schema_name: str = "result", reasoning_effort: str | None = None,
             max_tokens: int | None = None) -> tuple[str, bool]:
        """Chat Completions call; returns (message content, cached)."""
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if schema is not None:
            payload["response_format"] = {"type": "json_schema",
                                          "json_schema": {"name": schema_name, "schema": schema}}
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        if max_tokens:
            payload["max_completion_tokens"] = max_tokens
        data, cached = self.post("/chat/completions", payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise MetaAPIError("chat completion returned no message content") from None
        if isinstance(content, list):  # tolerate content-part arrays
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return content or "", cached


    def chat_message(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *,
                     reasoning_effort: str | None = None, max_tokens: int | None = None) -> tuple[dict[str, Any], bool]:
        """Chat Completions with tools; returns (the full assistant message, cached). See docs/meta-api/tool-calling.md."""
        payload: dict[str, Any] = {"model": model, "messages": messages, "tools": tools}
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        if max_tokens:
            payload["max_completion_tokens"] = max_tokens
        data, cached = self.post("/chat/completions", payload)
        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise MetaAPIError("chat completion returned no message") from None
        if isinstance(msg.get("content"), list):
            msg = {**msg, "content": "".join(p.get("text", "") for p in msg["content"] if isinstance(p, dict))}
        return msg, cached


class _Retry(Exception):
    pass


def _error_message(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error", {})
        return str(err.get("message") or err.get("type") or resp.text[:200])
    except (ValueError, AttributeError):
        return resp.text[:200]


def _retry_after(resp: httpx.Response) -> float | None:
    value = resp.headers.get("Retry-After")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
