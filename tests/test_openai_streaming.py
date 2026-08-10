"""Tests for intra-task observability wired into OpenAICompatibleAgent.execute()
(shared by GroqAgent/OllamaAgent, which don't override execute()).

Mirrors tests/test_gemini_streaming.py: drives a fake two-round tool-call
conversation through the OpenAI chat.completions.create() surface without
touching the network, and asserts:

  1. TOOL_USE_STARTED / TOOL_USE_COMPLETED fire with the right tool names.
  2. execute() returns byte-identical output whether or not an event_bus is
     wired in, given the same mocked SDK responses (the hard constraint).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from cressida.core import AgentRole, MissionState, Task
from cressida.core.events import Event, EventBus, EventType
from cressida.core.providers import openai_agent as openai_agent_mod
from cressida.core.providers.openai_agent import OpenAICompatibleAgent


# ── Fake OpenAI SDK response objects ───────────────────────────────────────

class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, id_, name, arguments):
        self.id = id_
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_unset=False):
        return {
            "role": "assistant",
            "content": self.content,
            "tool_calls": self.tool_calls,
        }


class _FakeChoice:
    def __init__(self, message, finish_reason):
        self.message = message
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, choices):
        self.choices = choices


def _make_agent(monkeypatch, tmp_path, tool_result="tool output here", tool_recorder=None):
    agent = OpenAICompatibleAgent.__new__(OpenAICompatibleAgent)  # bypass __init__ (no real SDK client/key needed)
    agent.role = AgentRole.BRANCH
    agent._agents_dir = tmp_path  # no spec file present -> falls back to default text
    agent._context_builder = SimpleNamespace(build_prompt=lambda **kwargs: "fake user prompt")
    agent._max_tokens = 8192
    agent._spec = None
    agent._model_map = {}
    agent._model = "gpt-4o-mini"

    tool_call_response = _FakeResponse(
        [_FakeChoice(
            _FakeMessage(content=None, tool_calls=[_FakeToolCall("call_1", "read_file", '{"path": "README.md"}')]),
            finish_reason="tool_calls",
        )]
    )
    final_response = _FakeResponse(
        [_FakeChoice(_FakeMessage(content="Done reading the file.", tool_calls=None), finish_reason="stop")]
    )

    agent._client = MagicMock()
    agent._client.chat.completions.create.side_effect = [tool_call_response, final_response]

    def fake_execute_tool(name, inputs, mission_id=""):
        if tool_recorder is not None:
            tool_recorder.append((name, inputs, mission_id))
        return tool_result

    monkeypatch.setattr(openai_agent_mod, "execute_tool", fake_execute_tool)
    monkeypatch.setattr(openai_agent_mod, "get_tools_for_role", lambda role: [])
    return agent


def _make_state_and_task(tmp_path):
    state = MissionState(mission_id="mission_test", brief="test brief", metadata={"project_dir": str(tmp_path)})
    task = Task(
        id="task_1",
        name="do the thing",
        description="do the thing",
        agent=AgentRole.BRANCH,
        metadata={"writes": [str(tmp_path / "out.md")]},
    )
    return state, task


def test_openai_execute_emits_tool_started_and_completed(tmp_path, monkeypatch):
    recorder: list = []
    agent = _make_agent(monkeypatch, tmp_path, tool_result="tool output here", tool_recorder=recorder)
    state, task = _make_state_and_task(tmp_path)

    bus = EventBus()
    started: list[Event] = []
    completed: list[Event] = []
    bus.subscribe(EventType.TOOL_USE_STARTED, lambda e: started.append(e))
    bus.subscribe(EventType.TOOL_USE_COMPLETED, lambda e: completed.append(e))

    result = asyncio.run(agent.execute(state, task, event_bus=bus))

    assert result == "Done reading the file."
    assert len(started) == 1
    assert len(completed) == 1
    assert started[0].data["tool_name"] == "read_file"
    assert started[0].data["task_id"] == "task_1"
    assert started[0].data["mission_id"] == "mission_test"
    assert started[0].data["agent"] == "BRANCH"
    assert completed[0].data["tool_name"] == "read_file"
    assert completed[0].data["is_error"] is False
    assert "tool output here" in completed[0].data["result_preview"]
    assert len(recorder) == 1
    assert recorder[0] == ("read_file", {"path": "README.md"}, "mission_test")


def test_openai_execute_output_identical_with_and_without_event_bus(tmp_path, monkeypatch):
    recorder_a: list = []
    agent_no_bus = _make_agent(monkeypatch, tmp_path, tool_result="same result", tool_recorder=recorder_a)
    state1, task1 = _make_state_and_task(tmp_path)
    result_no_bus = asyncio.run(agent_no_bus.execute(state1, task1, event_bus=None))

    recorder_b: list = []
    agent_with_bus = _make_agent(monkeypatch, tmp_path, tool_result="same result", tool_recorder=recorder_b)
    state2, task2 = _make_state_and_task(tmp_path)
    bus = EventBus()
    result_with_bus = asyncio.run(agent_with_bus.execute(state2, task2, event_bus=bus))

    assert result_no_bus == result_with_bus == "Done reading the file."
    assert recorder_a == [("read_file", {"path": "README.md"}, "mission_test")]
    assert recorder_b == [("read_file", {"path": "README.md"}, "mission_test")]

    written_path = tmp_path / "out.md"
    assert written_path.read_text(encoding="utf-8") == "Done reading the file."


def test_openai_execute_no_tool_calls_never_emits_events(tmp_path, monkeypatch):
    agent = OpenAICompatibleAgent.__new__(OpenAICompatibleAgent)
    agent.role = AgentRole.BRANCH
    agent._agents_dir = tmp_path
    agent._context_builder = SimpleNamespace(build_prompt=lambda **kwargs: "fake prompt")
    agent._max_tokens = 8192
    agent._spec = None
    agent._model_map = {}
    agent._model = "gpt-4o-mini"

    response = _FakeResponse(
        [_FakeChoice(_FakeMessage(content="No tools needed.", tool_calls=None), finish_reason="stop")]
    )
    agent._client = MagicMock()
    agent._client.chat.completions.create.return_value = response

    called = []
    monkeypatch.setattr(openai_agent_mod, "execute_tool", lambda *a, **kw: called.append(1))
    monkeypatch.setattr(openai_agent_mod, "get_tools_for_role", lambda role: [])

    state, task = _make_state_and_task(tmp_path)
    bus = EventBus()
    events: list[Event] = []
    bus.subscribe(EventType.TOOL_USE_STARTED, lambda e: events.append(e))
    bus.subscribe(EventType.TOOL_USE_COMPLETED, lambda e: events.append(e))

    result = asyncio.run(agent.execute(state, task, event_bus=bus))

    assert result == "No tools needed."
    assert events == []
    assert called == []
