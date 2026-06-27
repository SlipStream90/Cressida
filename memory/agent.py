from __future__ import annotations

from typing import Any


class AgentMemory:
    def __init__(self) -> None:
        self._context: dict[str, Any] = {}

    def store(self, key: str, value: Any) -> None:
        self._context[key] = value

    def retrieve(self, key: str, default: Any = None) -> Any:
        return self._context.get(key, default)

    def clear(self) -> None:
        self._context.clear()

    def snapshot(self) -> dict[str, Any]:
        return dict(self._context)
