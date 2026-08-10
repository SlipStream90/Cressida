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
    timeout: float = 0,
) -> None:
    """Instantiate one agent per AgentRole and register it.

    provider: one of 'auto' | 'gateway' | 'anthropic' | 'openai' | 'gemini' | 'groq' | 'ollama' |
              'claude_cli' | 'opencode' | 'codex' | 'kilocode'
              'auto' probes environment variables and installed packages in order, and every
              role runs on the single provider it picks.
              'gateway' also probes availability, but picks a provider *per role* (via
              core/providers/gateway.py) instead of one fixed provider for the whole
              mission — see that module's docstring for the rationale.
    timeout: per-agent task timeout in seconds (0 = use provider default).

    Already-registered roles are skipped, so calling multiple times is safe.
    """
    from cressida.core.providers.auto import detect_provider, detect_available_providers, create_agent

    agents_path = Path(agents_dir)
    root_path = Path(cressida_root)

    # 'gateway' resolves a provider per role below (a different provider per
    # AgentRole is the whole point); every other value — including 'auto' —
    # resolves once and applies to every role, exactly as before this option
    # existed.
    gateway_providers: list[str] | None = None
    resolved = provider
    if provider == "gateway":
        gateway_providers = detect_available_providers()
        if not gateway_providers:
            raise RuntimeError(
                "provider='gateway' but no LLM provider is available at all — same "
                "requirement as provider='auto'. See detect_provider()'s error message "
                "for how to make one available."
            )
    elif provider == "auto":
        resolved = detect_provider()

    for role in AgentRole:
        if registry.is_registered(role):
            continue
        role_provider = (
            _select_gateway_provider(role, gateway_providers) if gateway_providers is not None else resolved
        )
        kwargs = dict(
            role=role,
            provider=role_provider,
            agents_dir=agents_path,
            cressida_root=root_path,
            max_tokens=max_tokens,
            ollama_model=ollama_model,
            ollama_host=ollama_host,
        )
        if timeout > 0:
            kwargs["timeout"] = timeout
        agent = create_agent(**kwargs)
        registry.register(agent)


def _select_gateway_provider(role: AgentRole, available_providers: list[str]) -> str:
    from cressida.core.providers.gateway import select_provider_for_role

    chosen = select_provider_for_role(role, available_providers)
    print(f"[gateway] {role.value}: {chosen} (available: {available_providers})")
    return chosen
