from __future__ import annotations

"""Layer 5 — Failure Post-Mortem Analyzer.

Subscribes to TASK_FAILED events on the EventBus. When a task exhausts its
retries (signalled by a TASK_BLOCKED event immediately following TASK_FAILED),
the analyzer:

  1. Builds a structured failure record from event data
  2. Writes it to memory/postmortems/<task_id>_<ts>.json
  3. Calls StrategicMemory.record_pattern() so future missions learn from it
  4. If an INTELLIGENCE agent is registered and the error is non-trivial,
     queues a lightweight async analysis task to generate a remediation note

The remediation note is stored in knowledge/lessons.md (appended, not replaced),
which INTELLIGENCE and other agents read via the existing ContextBuilder.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cressida.core.events import Event, EventBus, EventType
from cressida.core.registry import AgentRegistry
from cressida.memory.strategic import StrategicMemory


_TRIVIAL_ERRORS = frozenset({
    "No agent could route this task",
    "No agent registered for role",
})

_LESSONS_FILE = Path("knowledge/lessons.md")
_POSTMORTEMS_DIR = Path("memory/postmortems")


class PostMortemAnalyzer:
    """Listens on the event bus and creates post-mortem reports for failed tasks."""

    def __init__(
        self,
        event_bus: EventBus,
        registry: AgentRegistry,
        memory: StrategicMemory | None = None,
    ) -> None:
        self._bus = event_bus
        self._registry = registry
        self._memory = memory or StrategicMemory()
        self._failed_tasks: dict[str, dict[str, Any]] = {}
        self._blocked_tasks: set[str] = set()

        # Subscribe to relevant events
        event_bus.subscribe(EventType.TASK_FAILED, self._on_task_failed)
        event_bus.subscribe(EventType.TASK_BLOCKED, self._on_task_blocked)

    def _on_task_failed(self, event: Event) -> None:
        task_id = event.data.get("task_id", "")
        if task_id:
            self._failed_tasks[task_id] = {
                "task_id": task_id,
                "mission_id": event.data.get("mission_id", ""),
                "agent": event.data.get("agent", ""),
                "error": event.data.get("error", "unknown"),
                "retries": event.data.get("retries", 0),
                "failed_at": event.timestamp.isoformat(),
            }

    def _on_task_blocked(self, event: Event) -> None:
        task_id = event.data.get("task_id", "")
        if task_id in self._failed_tasks and task_id not in self._blocked_tasks:
            self._blocked_tasks.add(task_id)
            record = self._failed_tasks[task_id]
            asyncio.ensure_future(self._run_postmortem(record))

    async def _run_postmortem(self, record: dict[str, Any]) -> None:
        task_id = record["task_id"]
        error   = record["error"]
        mission = record["mission_id"]

        print(f"[POSTMORTEM] Analyzing failure: task={task_id} mission={mission}")

        # 1. Write structured failure record
        self._write_postmortem_record(record)

        # 2. Record pattern in strategic memory
        self._record_pattern(record)

        # 3. Generate remediation note if error is non-trivial
        if not any(triv in error for triv in _TRIVIAL_ERRORS):
            await self._generate_remediation_note(record)

    def _write_postmortem_record(self, record: dict[str, Any]) -> None:
        _POSTMORTEMS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{record['task_id']}_{ts}.json"
        out: dict[str, Any] = {
            **record,
            "postmortem_at": datetime.now().isoformat(),
            "type": "task_failure_postmortem",
        }
        (_POSTMORTEMS_DIR / fname).write_text(json.dumps(out, indent=2), encoding="utf-8")

    def _record_pattern(self, record: dict[str, Any]) -> None:
        try:
            self._memory.record_pattern(
                pattern=f"Task failure: {record['task_id']} [{record['agent']}]",
                context=(
                    f"mission={record['mission_id']} "
                    f"error={record['error'][:200]} "
                    f"retries={record['retries']}"
                ),
                success=False,
            )
        except Exception as exc:
            print(f"[POSTMORTEM] Could not record pattern: {exc}")

    async def _generate_remediation_note(self, record: dict[str, Any]) -> None:
        """Ask the registered INTELLIGENCE agent to produce a remediation note.

        This is a lightweight self-contained task — it does NOT go through the
        full Coordinator/DAG pipeline to avoid recursion. The agent receives
        a targeted prompt and writes its finding directly to knowledge/lessons.md.
        """
        from cressida.core import AgentRole, MissionState, Task

        agent = self._registry.get(AgentRole.INTELLIGENCE)
        if agent is None:
            print("[POSTMORTEM] INTELLIGENCE not registered — skipping remediation note.")
            return

        task_id    = record["task_id"]
        error      = record["error"]
        mission_id = record["mission_id"]
        agent_name = record["agent"]

        analysis_task = Task(
            id=f"postmortem_{task_id}",
            name=f"Post-mortem analysis for {task_id}",
            description=(
                f"A task has failed in mission {mission_id}.\n\n"
                f"Failed task: {task_id}\n"
                f"Agent: {agent_name}\n"
                f"Error: {error}\n\n"
                "Analyze the likely root cause of this failure. "
                "Produce a concise remediation note (max 300 words) that:\n"
                "1. States the likely root cause\n"
                "2. Suggests a specific fix or mitigation\n"
                "3. Notes any pattern this represents for future missions\n\n"
                f"Write the note to knowledge/lessons.md (append, do not overwrite)."
            ),
            agent=AgentRole.INTELLIGENCE,
            metadata={"writes": ["knowledge/lessons.md"]},
        )

        synthetic_state = MissionState(
            mission_id=f"postmortem_{mission_id}",
            brief=f"Post-mortem analysis for failed task {task_id}",
        )

        try:
            await agent.execute(synthetic_state, analysis_task)
            print(f"[POSTMORTEM] Remediation note written for {task_id}")
        except Exception as exc:
            print(f"[POSTMORTEM] Remediation analysis failed: {exc}")
            # Fallback: append a minimal note ourselves
            self._append_minimal_lesson(record)

    def _append_minimal_lesson(self, record: dict[str, Any]) -> None:
        _LESSONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = (
            f"\n\n## Task Failure: {record['task_id']} "
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}]\n\n"
            f"- **Agent:** {record['agent']}\n"
            f"- **Mission:** {record['mission_id']}\n"
            f"- **Error:** {record['error'][:300]}\n"
            f"- **Retries:** {record['retries']}\n"
        )
        with open(_LESSONS_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
