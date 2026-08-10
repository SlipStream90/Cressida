from __future__ import annotations

import asyncio
import json

from cressida.core.events import Event, EventBus, EventType
from cressida.core.live_log import wire_live_log


def test_live_log_appends_jsonl_per_mission(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    bus = EventBus()
    wire_live_log(bus)

    async def _publish():
        await bus.publish(Event(EventType.TASK_STARTED, {"mission_id": "mission_x", "task_id": "research"}, source="test"))
        await bus.publish(Event(EventType.TASK_COMPLETED, {"mission_id": "mission_x", "task_id": "research"}, source="test"))
        await bus.publish(Event(EventType.MISSION_STARTED, {"mission_id": "mission_y"}, source="test"))

    asyncio.run(_publish())

    log_x = tmp_path / "mission_x" / "live_events.jsonl"
    log_y = tmp_path / "mission_y" / "live_events.jsonl"
    assert log_x.exists() and log_y.exists()

    lines = [json.loads(l) for l in log_x.read_text(encoding="utf-8").splitlines()]
    assert [l["type"] for l in lines] == ["task_started", "task_completed"]
    assert [l["seq"] for l in lines] == [1, 2]
    assert lines[0]["mission_id"] == "mission_x"


def test_live_log_ignores_events_with_no_mission_id(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    bus = EventBus()
    wire_live_log(bus)

    asyncio.run(bus.publish(Event(EventType.ERROR_OCCURRED, {"handler_error": "x"}, source="test")))

    assert list(tmp_path.iterdir()) == []
