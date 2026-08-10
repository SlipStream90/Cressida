"""Tests for intra-task observability wired into GeminiAgent.execute().

Mirrors the pattern in tests/test_observability_spine.py: the tool-calling
loop in core/providers/gemini_agent.py should publish TOOL_USE_STARTED /
TOOL_USE_COMPLETED around each execute_tool() call, and doing so must never
change execute()'s return value or the content written via _write_output —
that's the hard constraint (see task description). We drive a fake two-round
tool-call conversation through the Gemini Chat API surface (chat.send_message)
without touching the network, and assert:

  1. Events fire with the right tool names/agent/task ids.
  2. execute() returns byte-identical output whether or not an event_bus is
     wired in, given the same mocked SDK responses.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cressida.core import AgentRole, MissionState, Task
from cressida.core.events import Event, EventBus, EventType
from cressida.core.providers import gemini_agent as gemini_agent_mod
from cressida.core.providers.gemini_agent import GeminiAgent


# ── Fake Gemini SDK response objects ───────────────────────────────────────

class _FakeFunctionCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class _FakePart:
    def __init__(self, text=None, function_call=None):
        self.text = text
        self.function_call = function_call


class _FakeContent:
    def __init__(self, parts):
        self.parts = parts


class _FakeCandidate:
    def __init__(self, parts):
        self.content = _FakeContent(parts)


class _FakeResponse:
    def __init__(self, parts):
        self.candidates = [_FakeCandidate(parts)]


def _make_fake_chat():
    """A fake Chat object whose send_message() returns a tool-call response
    on the first call (round 1) and a final text response on the second
    call (round 2) — i.e. exactly one tool round-trip."""
    tool_call_response = _FakeResponse(
        [_FakePart(function_call=_FakeFunctionCall("read_file", {"path": "README.md"}))]
    )
    final_response = _FakeResponse([_FakePart(text="Done reading the file.")])

    chat = MagicMock()
    chat.send_message.side_effect = [tool_call_response, final_response]
    return chat


def _make_agent(monkeypatch, tmp_path, tool_result="file contents here", tool_recorder=None):
    agent = GeminiAgent.__new__(GeminiAgent)  # bypass __init__ (no real SDK client / API key needed)
    agent.role = AgentRole.BRANCH
    agent._agents_dir = tmp_path  # no spec file present -> falls back to default text
    agent._context_builder = SimpleNamespace(
        build_prompt=lambda **kwargs: "fake user prompt"
    )
    agent._max_tokens = 8192
    agent._spec = None
    agent._model = "gemini-2.0-flash"

    fake_chat = _make_fake_chat()
    agent._client = MagicMock()
    agent._client.chats.create.return_value = fake_chat

    def fake_execute_tool(name, inputs, mission_id=""):
        if tool_recorder is not None:
            tool_recorder.append((name, inputs, mission_id))
        return tool_result

    monkeypatch.setattr(gemini_agent_mod, "execute_tool", fake_execute_tool)
    monkeypatch.setattr(gemini_agent_mod, "get_tools_for_role", lambda role: [])
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


def test_gemini_execute_emits_tool_started_and_completed(tmp_path, monkeypatch):
    recorder: list = []
    agent = _make_agent(monkeypatch, tmp_path, tool_result="file contents here", tool_recorder=recorder)
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
    assert "file contents here" in completed[0].data["result_preview"]
    assert len(recorder) == 1
    assert recorder[0][0] == "read_file"


def test_gemini_execute_output_identical_with_and_without_event_bus(tmp_path, monkeypatch):
    # Two fully independent agents/mocks so each gets its own fresh
    # side_effect queue on chat.send_message — otherwise the second call
    # would exhaust the first agent's mocked responses.
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
    # Same tool call happened in both cases, event_bus wiring is purely additive.
    assert recorder_a == [("read_file", {"path": "README.md"}, "mission_test")]
    assert recorder_b == [("read_file", {"path": "README.md"}, "mission_test")]

    written_path = tmp_path / "out.md"
    assert written_path.read_text(encoding="utf-8") == "Done reading the file."


def test_gemini_execute_no_tool_calls_never_emits_events(tmp_path, monkeypatch):
    agent = GeminiAgent.__new__(GeminiAgent)
    agent.role = AgentRole.BRANCH
    agent._agents_dir = tmp_path
    agent._context_builder = SimpleNamespace(build_prompt=lambda **kwargs: "fake prompt")
    agent._max_tokens = 8192
    agent._spec = None
    agent._model = "gemini-2.0-flash"

    fake_chat = MagicMock()
    fake_chat.send_message.return_value = _FakeResponse([_FakePart(text="No tools needed.")])
    agent._client = MagicMock()
    agent._client.chats.create.return_value = fake_chat

    called = []
    monkeypatch.setattr(gemini_agent_mod, "execute_tool", lambda *a, **kw: called.append(1))
    monkeypatch.setattr(gemini_agent_mod, "get_tools_for_role", lambda role: [])

    state, task = _make_state_and_task(tmp_path)
    bus = EventBus()
    events: list[Event] = []
    bus.subscribe(EventType.TOOL_USE_STARTED, lambda e: events.append(e))
    bus.subscribe(EventType.TOOL_USE_COMPLETED, lambda e: events.append(e))

    result = asyncio.run(agent.execute(state, task, event_bus=bus))

    assert result == "No tools needed."
    assert events == []
    assert called == []
