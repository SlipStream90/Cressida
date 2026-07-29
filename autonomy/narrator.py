from __future__ import annotations

"""Live CLI narration of a running mission.

Popular agentic loops (Aider, Hermes-style runners) print a running narrative
of what the agent is doing, so a human watching the terminal can tell the run
is alive without polling anything. Cressida's mission execution used to be
silent between "Starting mission: ..." and the final result line — nothing
printed while research/architecture/implementation actually happened, even
though a single phase can run for minutes. ConsoleNarrator subscribes to the
mission's own EventBus (core/events.py) and prints one line per
task-lifecycle event, so `cressida run` and each mission's own spawned
console window (mcp_server.py::_spawn_mission_window) show real, continuous
progress instead of a long silent wait.
"""

import sys
import time
from datetime import datetime

from cressida.core.events import Event, EventBus, EventType


class ConsoleNarrator:
    """Prints a live, human-readable narrative of mission progress to stdout.

    Uses plain ASCII tags ("[RUN]", "[OK]", ...) rather than emoji: this
    prints straight to a freshly spawned console window (see
    mcp_server.py::_spawn_mission_window), which on Windows defaults to the
    legacy cp1252 codepage — emoji there raise UnicodeEncodeError on every
    single line, and a broad except silently eats it, so the "live" narration
    would in practice print nothing at all.
    """

    def __init__(self) -> None:
        self._task_agent: dict[str, str] = {}
        self._task_started_at: dict[str, float] = {}
        # Best-effort: if the console *can* do UTF-8, use it; if this stream
        # doesn't support reconfigure (e.g. redirected to a non-file object in
        # tests), just fall back silently — the ASCII tags below never need it.
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass

    def _print(self, line: str) -> None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {line}", flush=True)

    def _elapsed_suffix(self, task_id: str) -> str:
        start = self._task_started_at.pop(task_id, None)
        return f" ({time.time() - start:.1f}s)" if start is not None else ""

    async def _on_event(self, event: Event) -> None:
        data = event.data
        try:
            if event.type == EventType.MISSION_STARTED:
                brief = (data.get("brief") or "").replace("\n", " ")[:110]
                self._print(f"[RUN]  Mission {data.get('mission_id')} started - {brief}")

            elif event.type == EventType.TASK_STARTED:
                tid, agent = data.get("task_id", ""), data.get("agent", "?")
                self._task_agent[tid] = agent
                self._task_started_at[tid] = time.time()
                self._print(f"[....] {agent} -> {tid} starting")

            elif event.type == EventType.TASK_COMPLETED:
                tid = data.get("task_id", "")
                agent = data.get("agent") or self._task_agent.get(tid, "?")
                self._print(f"[OK]   {agent} -> {tid} done{self._elapsed_suffix(tid)}")

            elif event.type == EventType.TASK_FAILED:
                tid = data.get("task_id", "")
                agent = data.get("agent") or self._task_agent.get(tid, "?")
                retries = data.get("retries")
                suffix = f" (after {retries} retries)" if retries else ""
                self._print(f"[FAIL] {agent} -> {tid}{suffix}: {data.get('error', '')}")

            elif event.type == EventType.TASK_BLOCKED:
                self._print(f"[STOP] {data.get('task_id', '')} blocked: {data.get('error', '')}")

            elif event.type == EventType.TASK_STALLED:
                mins = data.get("elapsed_seconds", 0) / 60
                self._print(
                    f"[WARN] {data.get('agent', '?')} -> {data.get('task_id', '')} "
                    f"looks stalled - no update in {mins:.0f}m"
                )

            elif event.type == EventType.MISSION_COMPLETED:
                self._print(f"[DONE] Mission {data.get('mission_id')} completed")

            elif event.type == EventType.MISSION_FAILED:
                self._print(f"[DEAD] Mission {data.get('mission_id')} failed: {data.get('error', '')}")

            elif event.type == EventType.ARCHITECTURE_DECISION_MADE:
                self._print(f"[ARCH] {data.get('title') or data.get('decision', '')}")

        except Exception:
            pass  # narration must never break a mission

    def subscribe(self, event_bus: EventBus) -> None:
        for event_type in (
            EventType.MISSION_STARTED,
            EventType.TASK_STARTED,
            EventType.TASK_COMPLETED,
            EventType.TASK_FAILED,
            EventType.TASK_BLOCKED,
            EventType.TASK_STALLED,
            EventType.MISSION_COMPLETED,
            EventType.MISSION_FAILED,
            EventType.ARCHITECTURE_DECISION_MADE,
        ):
            event_bus.subscribe(event_type, self._on_event)


def wire_console_narrator(event_bus: EventBus) -> ConsoleNarrator:
    narrator = ConsoleNarrator()
    narrator.subscribe(event_bus)
    return narrator
