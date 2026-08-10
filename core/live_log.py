"""Per-mission live event log.

Every entry_point that starts a mission (cli/commands.py, mcp_server.py) wires
one instance of this per EventBus. It subscribes to every EventType and
appends each event as one JSON line to ``missions/<id>/live_events.jsonl`` —
the single artifact a live CLI viewer (or anything else) can tail with
nothing fancier than "read new lines since last read".

This exists because the only other way to see a mission "doing something
right now" was either watching a spawned console window (invisible under a
headless provider like opencode, or when the MCP server itself can't open a
window) or polling mission_status / execution_state.json, which only updates
at batch boundaries — long silent gaps read identically to "hung" and
"working". A human/agent watching a headless run has no way to tell the
difference without this.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from cressida.core.events import Event, EventBus, EventType
from cressida.core.paths import mission_dir


class LiveLogSink:
    """Appends every published event to a mission's live_events.jsonl.

    One JSON object per line: ``{"seq", "ts", "type", "source", "mission_id",
    "data"}``. ``seq`` is a monotonic per-sink counter so a tailer can detect
    gaps/dropped lines; ``mission_id`` is pulled from ``event.data`` when
    present so a single sink can be shared across missions (the daemon runs
    several concurrently) and a tailer can filter to the one it cares about.
    """

    def __init__(self) -> None:
        self._seq = 0
        self._lock = threading.Lock()

    def _path_for(self, mission_id: str) -> Path:
        d = mission_dir(mission_id)
        d.mkdir(parents=True, exist_ok=True)
        return d / "live_events.jsonl"

    def _write(self, event: Event) -> None:
        mission_id = event.data.get("mission_id") if isinstance(event.data, dict) else None
        if not mission_id:
            # Not every event is mission-scoped (e.g. daemon-level events);
            # nothing to tail against, so drop it rather than guessing a file.
            return
        with self._lock:
            self._seq += 1
            record = {
                "seq": self._seq,
                "ts": event.timestamp.isoformat(),
                "type": event.type.value,
                "source": str(event.source),
                "mission_id": mission_id,
                "data": event.data,
            }
            line = json.dumps(record, default=str)
        # File append itself doesn't need the lock — os-level appends of a
        # single write() call are atomic on both POSIX and Windows for
        # reasonable line lengths, and each sink instance is single-process.
        try:
            with self._path_for(mission_id).open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            # Never let logging plumbing break a mission.
            print(f"[live_log] failed to write event for {mission_id}: {e}")

    def __call__(self, event: Event) -> None:
        self._write(event)


def wire_live_log(event_bus: EventBus) -> LiveLogSink:
    """Subscribe a LiveLogSink to every EventType on ``event_bus``. Returns
    the sink (rarely needed by the caller, but useful for tests)."""
    sink = LiveLogSink()
    for event_type in EventType:
        event_bus.subscribe(event_type, sink)
    return sink
