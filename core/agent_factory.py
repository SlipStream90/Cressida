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
              'auto' probes all available providers in priority order and wraps each role in a
              runtime fallback chain, so an unavailable CLI does not abort the mission.
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
    fallback_providers: list[str] | None = None
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
        # Keep every currently available provider in order. A binary being
        # installed does not guarantee its session is authenticated, so the
        # runtime wrapper also falls through when a provider fails mid-task.
        fallback_providers = detect_available_providers()
        if not fallback_providers:
            # Preserve detect_provider's detailed diagnostic for the empty
            # environment case.
            resolved = detect_provider()
        else:
            resolved = fallback_providers[0]

    for role in AgentRole:
        if registry.is_registered(role):
            continue
        role_provider = (
            _select_gateway_provider(role, gateway_providers) if gateway_providers is not None else resolved
        )
        provider_list = fallback_providers if fallback_providers is not None else [role_provider]
        candidates = []
        candidate_names = []
        for candidate_provider in provider_list:
            kwargs = dict(
                role=role,
                provider=candidate_provider,
                agents_dir=agents_path,
                cressida_root=root_path,
                max_tokens=max_tokens,
                ollama_model=ollama_model,
                ollama_host=ollama_host,
            )
            if timeout > 0:
                kwargs["timeout"] = timeout
            try:
                candidates.append(create_agent(**kwargs))
                candidate_names.append(candidate_provider)
            except Exception as exc:
                if fallback_providers is None:
                    raise
                print(f"[provider-fallback] skipping {candidate_provider}: {exc}")

        if not candidates:
            raise RuntimeError(f"No provider could be initialized for role {role.value}")

        if fallback_providers is not None and len(candidates) > 1:
            from cressida.core.providers.fallback import FallbackAgent
            agent = FallbackAgent(role, candidates, candidate_names)
        else:
            agent = candidates[0]
        registry.register(agent)


def _select_gateway_provider(role: AgentRole, available_providers: list[str]) -> str:
    from cressida.core.providers.gateway import select_provider_for_role

    chosen = select_provider_for_role(role, available_providers)
    print(f"[gateway] {role.value}: {chosen} (available: {available_providers})")
    return chosen
