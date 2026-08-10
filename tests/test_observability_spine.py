"""Tests for the intra-task observability spine: publish_safe (core/events.py)
and ProviderAgentBase's _emit_tool_started/_emit_tool_completed helpers
(core/providers/base.py). These are the shared contract every provider's
streaming work builds on — the one hard requirement is that none of it can
ever affect a task's success/failure or return value, so the tests here focus
on that "never raises, degrades gracefully" property."""

from __future__ import annotations

import asyncio

from cressida.core import AgentRole
from cressida.core.events import Event, EventBus, EventType, publish_safe
from cressida.core.providers.base import ProviderAgentBase


def test_publish_safe_with_none_bus_is_a_no_op():
    # Must not raise even though there's nothing to publish to.
    asyncio.run(publish_safe(None, EventType.TOOL_USE_STARTED, {"mission_id": "m1"}, source="test"))


def test_publish_safe_delivers_event(tmp_path):
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe(EventType.TOOL_USE_STARTED, lambda e: received.append(e))

    asyncio.run(publish_safe(bus, EventType.TOOL_USE_STARTED, {"mission_id": "m1", "tool_name": "Read"}, source="BRANCH"))

    assert len(received) == 1
    assert received[0].data["tool_name"] == "Read"


def test_publish_safe_swallows_bad_data_without_raising():
    class Unserializable:
        def __repr__(self):
            raise RuntimeError("boom")

    bus = EventBus()
    # Should not raise even though the data dict contains something hostile.
    asyncio.run(publish_safe(bus, EventType.TOOL_USE_STARTED, {"weird": Unserializable()}, source="test"))


class _FakeProviderAgent(ProviderAgentBase):
    async def execute(self, state, task, event_bus=None):
        return "unused in this test"


def test_emit_tool_started_and_completed_publish_expected_shape():
    agent = _FakeProviderAgent(role=AgentRole.BRANCH)
    bus = EventBus()
    started: list[Event] = []
    completed: list[Event] = []
    bus.subscribe(EventType.TOOL_USE_STARTED, lambda e: started.append(e))
    bus.subscribe(EventType.TOOL_USE_COMPLETED, lambda e: completed.append(e))

    asyncio.run(agent._emit_tool_started(bus, "mission_1", "task_1", "Bash", {"command": "npm test"}))
    asyncio.run(agent._emit_tool_completed(bus, "mission_1", "task_1", "Bash", "all tests passed", is_error=False))

    assert len(started) == 1 and len(completed) == 1
    assert started[0].data["task_id"] == "task_1"
    assert started[0].data["tool_name"] == "Bash"
    assert started[0].data["agent"] == "BRANCH"
    assert completed[0].data["is_error"] is False
    assert "all tests passed" in completed[0].data["result_preview"]


def test_emit_helpers_never_raise_with_no_event_bus():
    agent = _FakeProviderAgent(role=AgentRole.BRANCH)
    asyncio.run(agent._emit_tool_started(None, "m", "t", "Read"))
    asyncio.run(agent._emit_tool_completed(None, "m", "t", "Read", "content"))
