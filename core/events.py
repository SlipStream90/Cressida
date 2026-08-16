from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum, auto
from typing import Any, Callable

from .types import AgentRole


class EventType(StrEnum):
    MISSION_STARTED = auto()
    MISSION_COMPLETED = auto()
    MISSION_FAILED = auto()
    TASK_CREATED = auto()
    TASK_ASSIGNED = auto()
    TASK_STARTED = auto()
    TASK_COMPLETED = auto()
    TASK_FAILED = auto()
    TASK_BLOCKED = auto()
    AGENT_MESSAGE_SENT = auto()
    ARCHITECTURE_DECISION_MADE = auto()
    REVIEW_COMPLETED = auto()
    EVALUATION_RECORDED = auto()
    FEEDBACK_RECEIVED = auto()
    STATE_CHANGED = auto()
    ERROR_OCCURRED = auto()
    TASK_STALLED = auto()
    MISSION_SPAWNED = auto()
    # Intra-task observability — a task_started/task_completed pair brackets
    # an entire agent turn that can run for minutes; these fire for each
    # individual tool call *inside* that turn (file read/write, bash command,
    # web search, ...) so a live viewer (`cressida watch`) can show what's
    # actually happening right now, not just "task X is running". Emitted on
    # a best-effort basis (see publish_safe below) by provider agents that
    # support it — providers that don't emit these simply never publish them,
    # which degrades gracefully back to today's task-level-only visibility.
    TOOL_USE_STARTED = auto()
    TOOL_USE_COMPLETED = auto()


@dataclass
class Event:
    type: EventType
    data: dict[str, Any]
    source: AgentRole | str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "data": self.data,
            "source": str(self.source),
            "timestamp": self.timestamp.isoformat(),
        }


EventHandler = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[EventHandler]] = {}
        self._history: list[Event] = []
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    # Cap on retained events. The daemon (`cressida daemon`) runs indefinitely
    # and every tool call of every task publishes here, so an unbounded list
    # grows for the life of the process. The only readers ask for the last
    # 500-1000 (StallMonitor, StatusServer); the durable record is
    # live_events.jsonl on disk.
    _MAX_HISTORY = 10000

    async def publish(self, event: Event) -> None:
        async with self._lock:
            self._history.append(event)
            if len(self._history) > self._MAX_HISTORY:
                del self._history[: len(self._history) - self._MAX_HISTORY]
            handlers = self._subscribers.get(event.type, [])
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    error_event = Event(
                        type=EventType.ERROR_OCCURRED,
                        data={"handler_error": str(e), "original_event": event.to_dict()},
                        source="event_bus",
                    )
                    self._history.append(error_event)

    def get_history(
        self,
        event_type: EventType | None = None,
        limit: int = 100,
    ) -> list[Event]:
        if event_type is None:
            return self._history[-limit:]
        return [e for e in self._history if e.type == event_type][-limit:]

    def clear(self) -> None:
        self._history.clear()


async def publish_safe(
    event_bus: EventBus | None,
    event_type: EventType,
    data: dict[str, Any],
    source: AgentRole | str,
) -> None:
    """Publish an event that can never affect the caller's control flow.

    Built for provider agents' intra-task observability events (see
    TOOL_USE_STARTED/COMPLETED above): those are a purely additive side
    channel, and a caller instrumenting its own agentic loop with these calls
    must never have that instrumentation change whether a task succeeds,
    fails, or what it returns. `EventBus.publish` already isolates subscriber
    handler exceptions from each other, but a bad `event_bus` (None — the
    default before a caller wires one in) or a bad `data` dict (e.g. containing
    something that can't be handled downstream) is not something callers
    should have to guard against individually at every call site, so this
    swallows both cases and never raises.
    """
    if event_bus is None:
        return
    try:
        await event_bus.publish(Event(type=event_type, data=data, source=source))
    except Exception:
        pass
