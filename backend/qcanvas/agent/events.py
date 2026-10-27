"""Plain-language agent log events and a thread-safe event bus for SSE."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

Status = Literal["info", "running", "ok", "fail", "warn"]


class AgentEvent(BaseModel):
    """One line of the live log."""

    seq: int
    timestamp: str
    step: str  # plan | generate | inject | run | verify | diagnose | repair | network | explain | diagram | done
    status: Status
    message: str
    attempt: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class EventBus:
    """Append-only event list that worker threads write and SSE readers follow.

    Readers keep their own cursor and call :meth:`wait_for` to block (with a
    timeout) until events past that cursor exist or the run is closed.
    """

    def __init__(self, on_emit: Callable[[AgentEvent], None] | None = None):
        self._events: list[AgentEvent] = []
        self._cond = threading.Condition()
        self._closed = False
        self._on_emit = on_emit

    def emit(self, step: str, status: Status, message: str, attempt: int | None = None,
             **details: Any) -> AgentEvent:
        """Record and publish an event."""
        with self._cond:
            event = AgentEvent(
                seq=len(self._events),
                timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                step=step, status=status, message=message, attempt=attempt, details=details,
            )
            self._events.append(event)
            self._cond.notify_all()
        if self._on_emit:
            self._on_emit(event)
        return event

    def close(self) -> None:
        """Mark the stream finished."""
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    @property
    def closed(self) -> bool:
        return self._closed

    def events(self, since: int = 0) -> list[AgentEvent]:
        """Events with ``seq >= since``."""
        with self._cond:
            return self._events[since:]

    def wait_for(self, since: int, timeout: float = 0.5) -> list[AgentEvent]:
        """Block up to ``timeout`` seconds for events past ``since``."""
        with self._cond:
            if len(self._events) <= since and not self._closed:
                self._cond.wait(timeout)
            return self._events[since:]
