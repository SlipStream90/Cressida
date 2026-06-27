from __future__ import annotations

from pathlib import Path

from cressida.core import AgentRole
from cressida.core.registry import AgentRegistry


def create_all_agents(
    registry: AgentRegistry,
    agents_dir: str | Path = "agents",
    cressida_root: str | Path = ".",
    max_tokens: int = 8192,
    provider: str = "auto",
    ollama_model: str = "llama3.2",
    ollama_host: str = "http://localhost:11434",
) -> None:
    """Instantiate one agent per AgentRole and register it.

    provider: one of 'auto' | 'anthropic' | 'openai' | 'gemini' | 'groq' | 'ollama'
              'auto' probes environment variables and installed packages in order.

    Already-registered roles are skipped, so calling multiple times is safe.
    """
    from cressida.core.providers.auto import detect_provider, create_agent

    resolved = provider if provider != "auto" else detect_provider()

    agents_path = Path(agents_dir)
    root_path = Path(cressida_root)

    for role in AgentRole:
        if registry.is_registered(role):
            continue
        agent = create_agent(
            role=role,
            provider=resolved,
            agents_dir=agents_path,
            cressida_root=root_path,
            max_tokens=max_tokens,
            ollama_model=ollama_model,
            ollama_host=ollama_host,
        )
        registry.register(agent)
