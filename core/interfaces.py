from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .events import EventBus
from .types import AgentRole, MissionState, Task


class Agent(ABC):
    role: AgentRole

    @abstractmethod
    async def execute(self, state: MissionState, task: Task, event_bus: EventBus | None = None) -> Any:
        """Run this agent's work for ``task``.

        ``event_bus``, when given, is an optional side channel for intra-task
        observability (TOOL_USE_STARTED/COMPLETED — see core/events.py) —
        purely additive, never required for correctness. Implementations that
        don't emit these events can ignore the parameter entirely; the
        default of None means "no live observability wired up", not an error.
        """
        ...

    @abstractmethod
    async def get_capabilities(self) -> list[str]:
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} role={self.role}>"


class ContextBuilder(ABC):
    @abstractmethod
    def build_prompt(
        self,
        task_id: str,
        agent_role: AgentRole,
        mission_id: str,
        brief: str,
        reads: list[str],
        task_description: str,
        objectives: list[str] | None = None,
    ) -> str:
        ...
