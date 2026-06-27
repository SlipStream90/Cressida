from __future__ import annotations

"""Shared base class for all provider-specific LLM agents.

Provider agents (OpenAI, Gemini, Groq, Ollama) inherit from ProviderAgentBase
instead of implementing Agent directly. This keeps spec loading, output writing,
and context assembly in one place without touching the existing core/llm_agent.py
(Anthropic agent).

All provider agents implement:
  execute(state, task) -> Any    (provider-specific agentic loop)
  get_capabilities() -> list[str]  (shared, from TASK_TYPE_ROUTE)
"""

from abc import abstractmethod
from pathlib import Path
from typing import Any

from cressida.core.interfaces import Agent
from cressida.core import AgentRole, MissionState, Task
from cressida.orchestration.context_builder import ContextBuilder


_MAX_TOOL_ROUNDS = 40


class ProviderAgentBase(Agent):
    """Abstract base that handles spec loading, context building, and output writing.

    Concrete provider agents only need to implement `execute()`.
    """

    def __init__(
        self,
        role: AgentRole,
        agents_dir: str | Path = "agents",
        cressida_root: str | Path = ".",
        max_tokens: int = 8192,
    ) -> None:
        self.role = role
        self._agents_dir = Path(agents_dir)
        self._context_builder = ContextBuilder(cressida_root)
        self._max_tokens = max_tokens
        self._spec: str | None = None

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _load_spec(self) -> str:
        if self._spec is None:
            spec_path = self._agents_dir / f"{self.role.value.lower()}.md"
            if spec_path.exists():
                self._spec = spec_path.read_text(encoding="utf-8")
            else:
                self._spec = (
                    f"You are the {self.role.value} agent in the CRESSIDA "
                    "multi-agent software engineering framework. "
                    "Execute the task assigned to you according to your role's responsibilities."
                )
        return self._spec

    def _build_user_prompt(self, state: MissionState, task: Task) -> str:
        return self._context_builder.build_prompt(
            task_id=task.id,
            agent_role=task.agent or self.role,
            mission_id=state.mission_id,
            brief=state.brief,
            reads=task.metadata.get("reads", []),
            task_description=task.description,
            objectives=state.objectives if state.objectives else None,
        )

    def _write_output(self, mission_id: str, task: Task, content: str) -> None:
        writes: list[str] = task.metadata.get("writes", [])
        if not writes:
            out_dir = Path("missions") / mission_id / "outputs"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{task.id}.md").write_text(content, encoding="utf-8")
            return
        for write_path in writes:
            resolved = write_path.replace("<mission_id>", mission_id)
            p = Path(resolved)
            if p.suffix:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
            else:
                p.mkdir(parents=True, exist_ok=True)
                (p / f"{task.id}.md").write_text(content, encoding="utf-8")

    async def get_capabilities(self) -> list[str]:
        from cressida.orchestration.router import TASK_TYPE_ROUTE
        return [k for k, v in TASK_TYPE_ROUTE.items() if v == self.role]

    # ── Abstract ──────────────────────────────────────────────────────────────

    @abstractmethod
    async def execute(self, state: MissionState, task: Task) -> Any:
        ...
