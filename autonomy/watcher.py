from __future__ import annotations

"""Layer 4 — Self-Triggering via mission inbox and cron scheduler.

MissionWatcher polls two directories:
  missions/inbox/   — YAML or Markdown files trigger immediate missions
  missions/scheduled/ — YAML files with a 'schedule:' field trigger on a cron/interval

Inbox format (YAML file or .md with YAML frontmatter):
    ---
    priority: HIGH       # optional, default MEDIUM
    mission_id: MSN-XYZ  # optional, auto-generated if absent
    auto_approve: false  # optional
    ---
    <mission brief text here>

Scheduled format (.yaml only):
    ---
    schedule: "@daily"   # @hourly | @daily | @weekly | @monthly | ISO datetime
    priority: LOW
    ---
    <brief>

Cron expressions (5-field) are supported if 'croniter' is installed.
Otherwise, only the @-shortcuts and ISO datetimes are supported.
"""

import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from cressida.core.events import Event, EventBus, EventType
from cressida.core.registry import AgentRegistry
from cressida.core import AgentRole, MissionState, MissionStatus, Priority, Task, TaskStatus
from cressida.memory.system import MemorySystem
from cressida.orchestration.coordinator import Coordinator
from cressida.state.shared_state import SharedState


_SCHEDULE_INTERVALS: dict[str, timedelta] = {
    "@hourly":  timedelta(hours=1),
    "@daily":   timedelta(days=1),
    "@weekly":  timedelta(weeks=1),
    "@monthly": timedelta(days=30),
}

_PRIORITY_MAP: dict[str, Priority] = {
    "LOWEST":   Priority.LOWEST,
    "LOW":      Priority.LOW,
    "MEDIUM":   Priority.MEDIUM,
    "HIGH":     Priority.HIGH,
    "CRITICAL": Priority.CRITICAL,
}


def _parse_brief_file(path: Path) -> dict[str, Any] | None:
    """Parse a brief file into {'brief': str, 'meta': dict}.

    Supports:
      - Pure YAML files (.yaml / .yml) where the top-level value is a dict
        with optional 'brief' key; everything else is treated as meta.
      - Markdown files (.md) with optional YAML frontmatter fenced by '---'.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None

    if path.suffix in (".yaml", ".yml"):
        try:
            data = yaml.safe_load(text) or {}
        except Exception:
            return None
        brief = data.pop("brief", text)
        return {"brief": str(brief).strip(), "meta": data}

    # Markdown: extract YAML frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if fm_match:
        try:
            meta = yaml.safe_load(fm_match.group(1)) or {}
        except Exception:
            meta = {}
        brief = text[fm_match.end():].strip()
    else:
        meta = {}
        brief = text.strip()

    return {"brief": brief, "meta": meta}


def _next_fire(schedule: str) -> datetime | None:
    """Return the next fire time for a schedule expression."""
    now = datetime.now()

    # @-shortcut
    delta = _SCHEDULE_INTERVALS.get(schedule.lower())
    if delta:
        return now + delta

    # ISO 8601 datetime — fire once
    try:
        return datetime.fromisoformat(schedule)
    except ValueError:
        pass

    # Cron expression (requires croniter)
    try:
        from croniter import croniter  # type: ignore[import]
        return croniter(schedule, now).get_next(datetime)
    except ImportError:
        pass

    return None


class MissionWatcher:
    """Polls missions/inbox/ and missions/scheduled/ and fires missions."""

    def __init__(
        self,
        registry: AgentRegistry,
        event_bus: EventBus,
        memory: MemorySystem,
        inbox_dir: str | Path = "missions/inbox",
        scheduled_dir: str | Path = "missions/scheduled",
        poll_interval: float = 10.0,
    ) -> None:
        self._registry = registry
        self._event_bus = event_bus
        self._memory = memory
        self._inbox = Path(inbox_dir)
        self._scheduled = Path(scheduled_dir)
        self._poll_interval = poll_interval
        self._seen_inbox: set[str] = set()
        self._schedule_state: dict[str, datetime] = {}  # filename → next fire time

    async def run(self) -> None:
        """Main loop — runs indefinitely until cancelled."""
        self._inbox.mkdir(parents=True, exist_ok=True)
        self._scheduled.mkdir(parents=True, exist_ok=True)
        print(f"[WATCHER] Watching {self._inbox} and {self._scheduled}")
        while True:
            try:
                await self._poll_inbox()
                await self._poll_scheduled()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[WATCHER] Poll error: {exc}")
            await asyncio.sleep(self._poll_interval)

    # ── Inbox ────────────────────────────────────────────────────────────────

    async def _poll_inbox(self) -> None:
        for path in sorted(self._inbox.iterdir()):
            if path.name.startswith(".") or path.name in self._seen_inbox:
                continue
            if path.suffix not in (".yaml", ".yml", ".md"):
                continue
            parsed = _parse_brief_file(path)
            if parsed is None:
                continue
            meta = parsed["meta"]
            if meta.get("status") == "processed":
                self._seen_inbox.add(path.name)
                continue
            self._seen_inbox.add(path.name)
            await self._trigger_mission(parsed["brief"], meta, source=path)
            self._mark_processed(path)

    def _mark_processed(self, path: Path) -> None:
        processed = path.parent / "processed"
        processed.mkdir(exist_ok=True)
        dest = processed / path.name
        try:
            path.rename(dest)
        except Exception:
            pass

    # ── Scheduled ────────────────────────────────────────────────────────────

    async def _poll_scheduled(self) -> None:
        now = datetime.now()
        for path in sorted(self._scheduled.iterdir()):
            if path.suffix not in (".yaml", ".yml"):
                continue
            parsed = _parse_brief_file(path)
            if parsed is None:
                continue
            schedule_expr = parsed["meta"].get("schedule", "")
            if not schedule_expr:
                continue
            next_fire = self._schedule_state.get(path.name)
            if next_fire is None:
                next_fire = _next_fire(schedule_expr)
                if next_fire:
                    self._schedule_state[path.name] = next_fire
            if next_fire and now >= next_fire:
                print(f"[WATCHER] Scheduled mission firing: {path.name}")
                await self._trigger_mission(parsed["brief"], parsed["meta"], source=path)
                # Compute next fire time
                new_next = _next_fire(schedule_expr)
                if new_next:
                    self._schedule_state[path.name] = new_next
                else:
                    # One-shot: remove from schedule tracking
                    del self._schedule_state[path.name]

    # ── Mission triggering ───────────────────────────────────────────────────

    async def _trigger_mission(
        self,
        brief: str,
        meta: dict[str, Any],
        source: Path | None = None,
    ) -> None:
        from cressida.cli.commands import _build_mission_state

        mission_id = meta.get("mission_id") or f"MSN-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        priority_str = str(meta.get("priority", "MEDIUM")).upper()
        priority = _PRIORITY_MAP.get(priority_str, Priority.MEDIUM)

        print(f"[WATCHER] Triggering mission {mission_id}: {brief[:80]}...")

        await self._event_bus.publish(Event(
            type=EventType.MISSION_SPAWNED,
            data={"mission_id": mission_id, "source": str(source), "brief": brief[:200]},
            source="watcher",
        ))

        state = _build_mission_state(mission_id, brief, priority)
        coordinator = Coordinator(self._registry, self._event_bus, self._memory)
        shared = SharedState()
        shared.mission = type(shared.mission)(mission_id=mission_id, brief=brief)

        try:
            result = await coordinator.run_mission(state, shared)
            print(f"[WATCHER] Mission {mission_id} finished: {result.status}")
        except Exception as exc:
            print(f"[WATCHER] Mission {mission_id} error: {exc}")
