from __future__ import annotations

from typing import Any

from cressida.core.interfaces import Agent
from cressida.core.types import AgentRole


class AgentRegistrationError(Exception):
    pass


class AgentRegistry:
    _agents: dict[AgentRole, Agent]

    def __init__(self) -> None:
        self._agents = {}

    def register(self, agent: Agent) -> None:
        if agent.role in self._agents:
            raise AgentRegistrationError(f"Agent already registered for role: {agent.role}")
        self._agents[agent.role] = agent

    def unregister(self, role: AgentRole) -> None:
        self._agents.pop(role, None)

    def get(self, role: AgentRole) -> Agent | None:
        return self._agents.get(role)

    def list_roles(self) -> list[AgentRole]:
        return list(self._agents.keys())

    async def can_handle(self, role: AgentRole, task_type: str) -> bool:
        agent = self.get(role)
        if agent is None:
            return False
        capabilities = await agent.get_capabilities()
        return task_type in capabilities

    def is_registered(self, role: AgentRole) -> bool:
        return role in self._agents

    @property
    def count(self) -> int:
        return len(self._agents)

    def register_default(
        self,
        agents_dir: str = "agents",
        cressida_root: str = ".",
        provider: str = "auto",
        ollama_model: str = "llama3.2",
        ollama_host: str = "http://localhost:11434",
    ) -> None:
        """Register one LLM agent per AgentRole using the specified (or auto-detected) provider.

        provider: 'auto' | 'anthropic' | 'openai' | 'gemini' | 'groq' | 'ollama'
        Delegates to AgentFactory — the registry stays decoupled from LLM details.
        Safe to call multiple times — already-registered roles are skipped.
        """
        from cressida.core.agent_factory import create_all_agents
        create_all_agents(
            self,
            agents_dir=agents_dir,
            cressida_root=cressida_root,
            provider=provider,
            ollama_model=ollama_model,
            ollama_host=ollama_host,
        )
