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

    async def publish(self, event: Event) -> None:
        async with self._lock:
            self._history.append(event)
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
