from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import AgentRole, MissionState, Task


class Agent(ABC):
    role: AgentRole

    @abstractmethod
    async def execute(self, state: MissionState, task: Task) -> Any:
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
