from __future__ import annotations

"""Live-tail a mission's ``live_events.jsonl`` from the terminal.

Exists because the headless path (opencode / Claude Code driving Cressida via
the MCP server) has no window to watch, so the only visibility a human had was
repeatedly calling ``mission_status`` — a round trip that costs tokens and
still only reflects state as of the last batch boundary, so a long silent gap
looks identical to a hang. ``core/live_log.py`` now writes one JSON line per
event as missions run; this module just tails that file. No MCP calls, no
``mission_status`` polling — reading a local file on a short interval is the
whole point, it's local and free.

Polling rather than watching: Windows has no cheap inotify-equivalent without
extra dependencies (see core/paths.py's Windows-first framing), so this reads
the file's new bytes on a plain timer instead of trying to watch it.
"""

import json
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from cressida.core.paths import mission_dir, missions_root

# Full-screen redraw so the view reads as a small dashboard rather than an
# ever-growing log dump — matches the "unambiguous, at-a-glance" goal better
# than plain tail -f scrollback would. Standard VT100 sequence; on a terminal
# that doesn't honor it this just prints literally, it never breaks the loop.
_ANSI_CLEAR = "\x1b[2J\x1b[H"

# Event types that close out a task_id previously opened by task_started —
# used to compute "what's in progress right now" from the tail alone.
_TASK_CLOSING_TYPES = {"task_completed", "task_failed", "task_blocked"}
_MISSION_END_TYPES = {"mission_completed", "mission_failed"}


def _find_latest_mission() -> str | None:
    """Pick the mission whose live_events.jsonl was written to most recently
    — that's "the mission currently doing something" among whatever's under
    missions_root(). Returns None if nothing has ever written one."""
    root = missions_root()
    if not root.exists():
        return None
    newest_id: str | None = None
    newest_mtime = -1.0
    for path in root.glob("*/live_events.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > newest_mtime:
            newest_mtime = mtime
            newest_id = path.parent.name
    return newest_id


def _read_new_records(path: Path, offset: int) -> tuple[int, list[dict[str, Any]]]:
    """Read whatever bytes were appended to ``path`` since ``offset`` and
    parse the complete lines among them.

    Reads/seeks in binary mode so the returned offset is an exact byte
    position regardless of encoding — a text-mode seek/tell pair can drift
    under multi-byte UTF-8 content. If the tail of the read doesn't end in a
    newline (we caught the writer mid-append), that partial line is held back
    and re-read on the next poll rather than parsed or consumed, since
    ``LiveLogSink`` writes each record with a single ``write()`` call and a
    trailing "\\n" — a line without a trailing newline is simply not finished
    yet, not corrupt.
    """
    try:
        with path.open("rb") as f:
            f.seek(offset)
            chunk = f.read()
    except OSError:
        return offset, []
    if not chunk:
        return offset, []

    text = chunk.decode("utf-8", errors="replace")
    if text.endswith("\n"):
        complete, consumed = text, len(chunk)
    else:
        split_at = text.rfind("\n")
        if split_at == -1:
            return offset, []  # nothing complete yet
        complete = text[: split_at + 1]
        consumed = len(complete.encode("utf-8"))

    records: list[dict[str, Any]] = []
    for line in complete.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a torn line slipping through the newline check; skip rather than crash the watcher
    return offset + consumed, records


def follow_mission_events(mission_id: str, poll_interval: float = 0.75, wait_timeout: float = 30.0):
    """Generator yielding parsed event dicts as they're appended to
    ``missions/<mission_id>/live_events.jsonl``, forever.

    Yields ``None`` on poll cycles with no new data — that's the heartbeat
    tick a caller uses to refresh an "Ns since last event" display even when
    nothing happened. Waits (rather than raising immediately) if the file
    doesn't exist yet, since a mission that just started may not have had its
    sink write the first event; raises ``FileNotFoundError`` only after
    ``wait_timeout`` seconds of the file never appearing.
    """
    path = mission_dir(mission_id) / "live_events.jsonl"
    waited = 0.0
    while not path.exists():
        if waited >= wait_timeout:
            raise FileNotFoundError(
                f"No live_events.jsonl appeared for mission {mission_id!r} after {wait_timeout:.0f}s "
                f"(looked in {path}) - has the mission actually started?"
            )
        time.sleep(poll_interval)
        waited += poll_interval

    offset = 0
    while True:
        offset, records = _read_new_records(path, offset)
        for record in records:
            yield record
        if not records:
            yield None
        time.sleep(poll_interval)


def _describe_event(record: dict[str, Any]) -> str:
    """One human-readable line for an event record, keyed off ``type`` with a
    generic fallback for any EventType this function doesn't special-case
    (keeps the watcher forward-compatible with new event types)."""
    event_type = record.get("type", "?")
    data = record.get("data") or {}

    if event_type == "mission_started":
        return f"mission started ({data.get('mission_id', '?')})"
    if event_type == "task_created":
        return f"task created: {data.get('task_id', '?')}"
    if event_type == "task_assigned":
        return f"task assigned: {data.get('task_id', '?')} -> {data.get('agent', data.get('assignee', '?'))}"
    if event_type == "task_started":
        return f"task started: {data.get('task_id', '?')} (agent={data.get('agent', '?')})"
    if event_type == "task_completed":
        return f"task completed: {data.get('task_id', '?')}"
    if event_type == "task_failed":
        return f"TASK FAILED: {data.get('task_id', '?')} - {data.get('error', data.get('reason', ''))}"
    if event_type == "task_blocked":
        return f"task blocked: {data.get('task_id', '?')} - {data.get('reason', '')}"
    if event_type == "task_stalled":
        return f"TASK STALLED: {data.get('task_id', '?')}"
    if event_type == "agent_message_sent":
        return f"message: {data.get('from', data.get('agent', '?'))} -> {data.get('to', '?')}: {str(data.get('message', ''))[:60]}"
    if event_type == "architecture_decision_made":
        return f"architecture decision: {str(data.get('decision', ''))[:60]}"
    if event_type == "review_completed":
        return f"review completed: {data.get('task_id', '?')} verdict={data.get('verdict', data.get('result', '?'))}"
    if event_type == "evaluation_recorded":
        return f"evaluation recorded: {data.get('task_id', '?')} score={data.get('score', '?')}"
    if event_type == "feedback_received":
        return f"feedback received: {data.get('task_id', '?')}"
    if event_type == "state_changed":
        return f"state changed: {data.get('field', data.get('key', ''))}"
    if event_type == "error_occurred":
        return f"ERROR: {data.get('handler_error', data.get('error', ''))}"
    if event_type == "mission_completed":
        return "MISSION COMPLETED"
    if event_type == "mission_failed":
        return f"MISSION FAILED: {data.get('reason', '')}"
    if event_type == "mission_spawned":
        return f"sub-mission spawned: {data.get('child_mission_id', '?')}"
    if event_type == "tool_use_started":
        return (
            f"  -> {data.get('agent', '?')} calling {data.get('tool_name', '?')}"
            f"({str(data.get('tool_input', ''))[:80]})"
        )
    if event_type == "tool_use_completed":
        marker = "FAILED" if data.get("is_error") else "ok"
        return (
            f"  <- {data.get('tool_name', '?')} {marker}: "
            f"{str(data.get('result_preview', ''))[:80]}"
        )
    return f"{event_type}: {json.dumps(data, default=str)[:60]}"


def _render_frame(
    mission_id: str,
    buffer: deque[dict[str, Any]],
    in_progress: dict[str, dict[str, Any]],
    last_event_ts: datetime | None,
    mission_ended: bool,
    clear: bool = True,
) -> str:
    lines: list[str] = [_ANSI_CLEAR] if clear else []
    lines.append(f"cressida watch - mission {mission_id}")

    if last_event_ts is not None:
        elapsed = max(0.0, (datetime.now() - last_event_ts).total_seconds())
        heartbeat = f"{elapsed:.0f}s since last event"
        if elapsed > 60:
            heartbeat += "  (quiet a while - still not necessarily stuck; check for a long-running tool call)"
    else:
        heartbeat = "waiting for first event..."

    if mission_ended:
        status = "mission has ended (see last event below)"
    elif in_progress:
        parts = []
        for tid, info in in_progress.items():
            piece = f"{tid} (agent={info.get('agent', '?')})"
            current_tool = info.get("current_tool")
            if current_tool:
                piece += f" -> {current_tool}"
            parts.append(piece)
        status = "in progress: " + ", ".join(parts)
    else:
        status = "idle / between tasks"

    lines.append(f"status:    {status}")
    lines.append(f"heartbeat: {heartbeat}")
    lines.append("-" * 78)
    if not buffer:
        lines.append("(no events yet)")
    for record in buffer:
        ts = str(record.get("ts", ""))[:19].replace("T", " ")
        event_type = str(record.get("type", "?"))
        lines.append(f"[{ts}] {event_type:<26} {_describe_event(record)}")
    lines.append("-" * 78)
    lines.append("Ctrl-C to stop watching (the mission itself keeps running)")
    return "\n".join(lines)


def watch_mission(
    mission_id: str | None = None,
    tail: int = 20,
    poll_interval: float = 0.75,
    wait_timeout: float = 30.0,
    follow: bool = True,
    stream: TextIO | None = None,
) -> int:
    """Live-tail a mission's event log. Returns a process-style exit code.

    ``mission_id=None`` auto-attaches to whichever mission most recently
    wrote to its live_events.jsonl (see ``_find_latest_mission``). With
    ``follow=False`` this renders the current state once and exits instead of
    polling forever — useful for scripting/tests.
    """
    out = stream or sys.stdout

    if mission_id is None:
        mission_id = _find_latest_mission()
        if mission_id is None:
            print(
                f"No missions with a live_events.jsonl found under {missions_root()} - "
                "nothing appears to be running yet.",
                file=sys.stderr,
            )
            return 1
        print(f"(auto-attached to most recently active mission: {mission_id})", file=out)

    buffer: deque[dict[str, Any]] = deque(maxlen=max(1, tail))
    in_progress: dict[str, dict[str, Any]] = {}
    last_event_ts: datetime | None = None
    mission_ended = False

    def _apply(record: dict[str, Any]) -> None:
        nonlocal last_event_ts, mission_ended
        buffer.append(record)
        ts_raw = record.get("ts")
        try:
            last_event_ts = datetime.fromisoformat(ts_raw) if ts_raw else datetime.now()
        except ValueError:
            last_event_ts = datetime.now()
        event_type = record.get("type")
        data = record.get("data") or {}
        task_id = data.get("task_id")
        if event_type == "task_started" and task_id:
            in_progress[task_id] = data
        elif event_type == "tool_use_started" and task_id and task_id in in_progress:
            # Tags the in-progress task's entry with what it's doing *right
            # now*, without discarding the task_started data it already
            # carries (agent name, etc.) — this is what makes the status
            # line show "BRANCH -> Edit(...)" instead of just "BRANCH".
            in_progress[task_id] = {**in_progress[task_id], "current_tool": data.get("tool_name")}
        elif event_type == "tool_use_completed" and task_id and task_id in in_progress:
            in_progress[task_id] = {**in_progress[task_id], "current_tool": None}
        elif event_type in _TASK_CLOSING_TYPES and task_id:
            in_progress.pop(task_id, None)
        elif event_type in _MISSION_END_TYPES:
            mission_ended = True

    if not follow:
        path = mission_dir(mission_id) / "live_events.jsonl"
        if path.exists():
            _offset, records = _read_new_records(path, 0)
            for record in records[-tail:]:
                _apply(record)
        print(_render_frame(mission_id, buffer, in_progress, last_event_ts, mission_ended, clear=False), file=out)
        return 0

    try:
        events = follow_mission_events(mission_id, poll_interval=poll_interval, wait_timeout=wait_timeout)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1

    try:
        for record in events:
            if record is not None:
                _apply(record)
            print(_render_frame(mission_id, buffer, in_progress, last_event_ts, mission_ended), file=out, flush=True)
        return 0  # unreachable in practice — follow_mission_events runs forever until interrupted
    except KeyboardInterrupt:
        print("\nStopped watching (the mission, if still running, is unaffected).", file=out)
        return 0
