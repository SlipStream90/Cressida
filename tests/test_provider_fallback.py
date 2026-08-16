from __future__ import annotations

import asyncio

from cressida.core import AgentRole, MissionState, Task
from cressida.core.interfaces import Agent
from cressida.core.paths import mission_dir
from cressida.core.providers.fallback import FallbackAgent, has_usable_output
# One implementation lives in core.providers.auto (it also honours
# CRESSIDA_INVOKER for shell-launched missions); mcp_server calls it.
from cressida.core.providers.auto import provider_for_invoker as _provider_for_invoker


class _FakeAgent(Agent):
    def __init__(self, role, name, behavior):
        self.role = role
        self.name = name
        self.behavior = behavior
        self.calls = 0

    async def execute(self, state, task, event_bus=None):
        self.calls += 1
        return self.behavior(state, task)

    async def get_capabilities(self):
        return ["test"]


def _task(mission_id):
    return Task(
        id="research",
        name="research",
        description="",
        agent=AgentRole.INTELLIGENCE,
        metadata={"writes": [f"missions/{mission_id}/research.md"]},
    )


def test_fallback_tries_next_provider_after_cli_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_HOME", str(tmp_path))
    mission_id = "mission_fallback"
    state = MissionState(mission_id=mission_id, brief="brief")
    task = _task(mission_id)

    first = _FakeAgent(AgentRole.INTELLIGENCE, "claude_cli", lambda *_: (_ for _ in ()).throw(RuntimeError("OAuth expired")))

    def write_success(_state, _task):
        path = mission_dir(mission_id) / "research.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("research", encoding="utf-8")
        return "done"

    second = _FakeAgent(AgentRole.INTELLIGENCE, "opencode", write_success)
    agent = FallbackAgent(AgentRole.INTELLIGENCE, [first, second], ["claude_cli", "opencode"])

    result = asyncio.run(agent.execute(state, task))

    assert result == "done"
    assert first.calls == 1
    assert second.calls == 1


def test_empty_declared_output_is_not_success(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_HOME", str(tmp_path))
    mission_id = "mission_empty"
    state = MissionState(mission_id=mission_id, brief="brief")
    task = _task(mission_id)
    path = mission_dir(mission_id) / "research.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")

    assert not has_usable_output(state, task, "")


def test_mcp_invoker_identity_selects_matching_provider():
    assert _provider_for_invoker("auto", "opencode") == "opencode"
    assert _provider_for_invoker("auto", "kilo") == "kilocode"
    assert _provider_for_invoker("auto", "unknown") == "auto"
    assert _provider_for_invoker("claude_cli", "opencode") == "claude_cli"


def test_mcp_invoker_identity_can_come_from_environment(monkeypatch):
    monkeypatch.setenv("CRESSIDA_INVOKER", "opencode")
    assert _provider_for_invoker("auto", "") == "opencode"
