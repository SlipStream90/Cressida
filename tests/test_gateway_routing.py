"""Tests for gateway routing (core/providers/gateway.py, and its wiring into
core/agent_factory.py / core/providers/auto.py::detect_available_providers).

The hard requirement here isn't the exact scores in _PROVIDER_TIER_SCORE
(a heuristic, expected to be tuned over time) — it's that provider='auto'
(today's default, used by every existing mission) is completely unaffected,
and that provider='gateway' always resolves to something in the caller's
available-providers list, never a value outside it."""

from __future__ import annotations

from cressida.core import AgentRole
from cressida.core.agent_factory import create_all_agents
from cressida.core.registry import AgentRegistry
from cressida.core.providers.gateway import select_provider_for_role


def test_select_provider_for_role_picks_from_available_only():
    chosen = select_provider_for_role(AgentRole.BRANCH, ["ollama", "groq"])
    assert chosen in ("ollama", "groq")


def test_select_provider_for_role_prefers_strong_provider_for_executor_tier():
    # BRANCH ships implementation code (executor tier) — with both a frontier
    # provider and ollama available, the frontier one should win.
    chosen = select_provider_for_role(AgentRole.BRANCH, ["ollama", "anthropic"])
    assert chosen == "anthropic"


def test_select_provider_for_role_prefers_fast_provider_for_trivial_tier():
    # M is a one-shot classification role (trivial tier) — groq's speed
    # scoring should win over ollama when both are available.
    chosen = select_provider_for_role(AgentRole.M, ["ollama", "groq"])
    assert chosen == "groq"


def test_select_provider_for_role_raises_on_empty_list():
    import pytest

    with pytest.raises(ValueError):
        select_provider_for_role(AgentRole.BRANCH, [])


def test_select_provider_for_role_handles_unknown_provider_gracefully():
    # A provider not in _PROVIDER_TIER_SCORE must not crash — it just gets a
    # middling default score instead of being excluded.
    chosen = select_provider_for_role(AgentRole.BRANCH, ["some_future_provider"])
    assert chosen == "some_future_provider"


def test_gateway_provider_never_calls_detect_provider(monkeypatch):
    """provider='auto' must still resolve exactly as before — gateway routing
    is additive, not a replacement for the default path."""
    calls = {"detect_provider": 0, "detect_available": 0}

    import cressida.core.agent_factory as agent_factory_module

    def fake_detect_provider():
        calls["detect_provider"] += 1
        return "ollama"

    def fake_detect_available():
        calls["detect_available"] += 1
        return ["ollama"]

    def fake_create_agent(**kwargs):
        class _Fake:
            role = kwargs["role"]

            async def execute(self, *a, **k):
                return None

            async def get_capabilities(self):
                return []

        return _Fake()

    monkeypatch.setattr("cressida.core.providers.auto.detect_provider", fake_detect_provider)
    monkeypatch.setattr("cressida.core.providers.auto.detect_available_providers", fake_detect_available)
    monkeypatch.setattr("cressida.core.providers.auto.create_agent", fake_create_agent)

    registry = AgentRegistry()
    create_all_agents(registry, provider="auto")

    assert calls["detect_provider"] == 1
    assert calls["detect_available"] == 0
    assert registry.count == len(list(AgentRole))


def test_gateway_provider_routes_per_role(monkeypatch):
    """provider='gateway' should call detect_available_providers() (not
    detect_provider()) and register every role with a provider drawn from
    that available set."""
    seen_providers: set[str] = set()

    def fake_detect_available():
        return ["ollama", "anthropic"]

    def fake_create_agent(**kwargs):
        seen_providers.add(kwargs["provider"])

        class _Fake:
            role = kwargs["role"]

            async def execute(self, *a, **k):
                return None

            async def get_capabilities(self):
                return []

        return _Fake()

    def fail_detect_provider():
        raise AssertionError("detect_provider() should not be called under provider='gateway'")

    monkeypatch.setattr("cressida.core.providers.auto.detect_provider", fail_detect_provider)
    monkeypatch.setattr("cressida.core.providers.auto.detect_available_providers", fake_detect_available)
    monkeypatch.setattr("cressida.core.providers.auto.create_agent", fake_create_agent)

    registry = AgentRegistry()
    create_all_agents(registry, provider="gateway")

    assert registry.count == len(list(AgentRole))
    assert seen_providers <= {"ollama", "anthropic"}


def test_gateway_provider_raises_when_nothing_available(monkeypatch):
    import pytest

    monkeypatch.setattr("cressida.core.providers.auto.detect_available_providers", lambda: [])

    registry = AgentRegistry()
    with pytest.raises(RuntimeError):
        create_all_agents(registry, provider="gateway")


def test_detect_available_providers_respects_explicit_override(monkeypatch):
    from cressida.core.providers.auto import detect_available_providers

    monkeypatch.setenv("CRESSIDA_PROVIDER", "ollama")
    assert detect_available_providers() == ["ollama"]
