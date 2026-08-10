from __future__ import annotations

import asyncio
import io
import threading
import time

from cressida.core.events import Event, EventBus, EventType
from cressida.core.live_log import wire_live_log
from cressida.cli.watch import follow_mission_events, watch_mission, _find_latest_mission, _read_new_records


def _publish_synthetic_mission(bus: EventBus, mission_id: str, delay: float = 0.3) -> None:
    """Simulates a real mission: mission_started, two task start/complete
    pairs, mission_completed — with a real sleep between each publish so a
    tailer polling the file sees them arrive over time, not all at once."""

    async def _run():
        await bus.publish(Event(EventType.MISSION_STARTED, {"mission_id": mission_id}, source="coordinator"))
        await asyncio.sleep(delay)
        await bus.publish(Event(EventType.TASK_STARTED, {"mission_id": mission_id, "task_id": "research", "agent": "INTELLIGENCE"}, source="executor"))
        await asyncio.sleep(delay)
        await bus.publish(Event(EventType.TASK_COMPLETED, {"mission_id": mission_id, "task_id": "research"}, source="executor"))
        await asyncio.sleep(delay)
        await bus.publish(Event(EventType.TASK_STARTED, {"mission_id": mission_id, "task_id": "build", "agent": "FORGE"}, source="executor"))
        await asyncio.sleep(delay)
        await bus.publish(Event(EventType.TASK_COMPLETED, {"mission_id": mission_id, "task_id": "build"}, source="executor"))
        await asyncio.sleep(delay)
        await bus.publish(Event(EventType.MISSION_COMPLETED, {"mission_id": mission_id}, source="coordinator"))

    asyncio.run(_run())


def test_follow_mission_events_delivers_incrementally(tmp_path, monkeypatch):
    """The whole point of `watch`: events must show up as they're written,
    not only after the publisher finishes. Prove it by recording wall-clock
    arrival times from the polling generator and asserting they're spread
    out roughly matching the publisher's sleep cadence, not clustered at the
    end."""
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    bus = EventBus()
    wire_live_log(bus)
    mission_id = "mission_watch_test"

    publisher = threading.Thread(target=_publish_synthetic_mission, args=(bus, mission_id, 0.3), daemon=True)
    publisher.start()

    gen = follow_mission_events(mission_id, poll_interval=0.1, wait_timeout=10.0)
    start = time.monotonic()
    arrivals: list[tuple[float, str]] = []
    while len(arrivals) < 6:
        record = next(gen)
        if record is not None:
            arrivals.append((time.monotonic() - start, record["type"]))
    publisher.join(timeout=5)

    assert [t for _, t in arrivals] == [
        "mission_started", "task_started", "task_completed",
        "task_started", "task_completed", "mission_completed",
    ]
    # The first event lands quickly; the last should land only after ~5 * 0.3s
    # of publisher sleeps have elapsed — i.e. the generator did not just read
    # the whole file once at the end. Loose bounds to avoid CI flakiness.
    assert arrivals[0][0] < 1.0
    assert arrivals[-1][0] > 1.0


def test_read_new_records_holds_back_partial_line(tmp_path):
    # newline="" (and binary-safe open) avoids Windows' default \n -> \r\n text-mode
    # translation, which would otherwise desync the byte-offset math under test.
    path = tmp_path / "live_events.jsonl"
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write('{"seq": 1, "type": "task_started"}\n{"seq": 2, "typ')
    offset, records = _read_new_records(path, 0)
    assert [r["seq"] for r in records] == [1]
    # Offset should stop right after the complete line, not swallow the partial tail.
    assert offset == len('{"seq": 1, "type": "task_started"}\n'.encode("utf-8"))

    with path.open("a", encoding="utf-8", newline="") as f:
        f.write('e": "task_completed"}\n')
    offset2, records2 = _read_new_records(path, offset)
    assert [r["seq"] for r in records2] == [2]
    assert offset2 == path.stat().st_size


def test_find_latest_mission_picks_newest_mtime(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    older = tmp_path / "mission_old" / "live_events.jsonl"
    newer = tmp_path / "mission_new" / "live_events.jsonl"
    older.parent.mkdir(parents=True)
    newer.parent.mkdir(parents=True)
    older.write_text("{}\n", encoding="utf-8")
    time.sleep(0.05)
    newer.write_text("{}\n", encoding="utf-8")

    assert _find_latest_mission() == "mission_new"


def test_find_latest_mission_none_when_no_missions(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    assert _find_latest_mission() is None


def test_watch_mission_no_follow_renders_current_state(tmp_path, monkeypatch):
    """--no-follow path: exercises watch_mission end-to-end (auto-attach +
    render) without an infinite loop, so it's safe to assert on in a normal
    pytest run."""
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    bus = EventBus()
    wire_live_log(bus)
    mission_id = "mission_no_follow"
    asyncio.run(bus.publish(Event(EventType.MISSION_STARTED, {"mission_id": mission_id}, source="coordinator")))
    asyncio.run(bus.publish(Event(EventType.TASK_STARTED, {"mission_id": mission_id, "task_id": "research", "agent": "INTELLIGENCE"}, source="executor")))

    out = io.StringIO()
    rc = watch_mission(mission_id=None, follow=False, stream=out)  # None -> must auto-attach
    assert rc == 0
    text = out.getvalue()
    assert "mission_no_follow" in text
    assert "task started: research" in text
    assert "in progress" in text  # research has no task_completed yet


def test_watch_mission_missing_mission_returns_nonzero(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    out = io.StringIO()
    rc = watch_mission(mission_id=None, follow=False, stream=out)
    assert rc == 1
