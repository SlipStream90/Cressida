from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cressida.core.events import Event, EventBus, EventType
from cressida.core.paths import cressida_home, mission_dir
from cressida.core.registry import AgentRegistry
from cressida.core.types import AgentRole, MissionState, MissionStatus, Task, TaskStatus
from cressida.memory.system import MemorySystem
from cressida.state.shared_state import SharedState

from cressida.learning import Curator, PlaybookStore, ReflectionEngine, SkillSynthesizer

from .dependency_graph import CyclicDependencyError, DependencyGraph
from .dispatcher import Dispatcher
from .executor import TaskExecutor
from .router import TaskRouter
from .scheduler import Scheduler


class CoordinationError(Exception):
    pass


class Coordinator:
    def __init__(
        self,
        registry: AgentRegistry,
        event_bus: EventBus,
        memory: MemorySystem,
    ) -> None:
        self._registry = registry
        self._event_bus = event_bus
        self._memory = memory
        self._router = TaskRouter()
        self._dispatcher = Dispatcher(self._router)
        self._executor = TaskExecutor(registry, self._router, event_bus)
        self._graph = DependencyGraph()
        self._scheduler = Scheduler(self._graph)

        # Learning layer (agent R): reflection distils lessons into per-agent
        # playbooks after every mission; the curator keeps them consolidated.
        # Anchor to the canonical home so the write side lines up with the
        # ContextBuilder read side, which resolves knowledge/ the same way.
        pkg_dir = cressida_home()
        self._playbooks = PlaybookStore(pkg_dir / "knowledge" / "playbooks")
        self._reflection = ReflectionEngine(
            playbooks=self._playbooks,
            evaluations_path=pkg_dir / "evaluations",
        )
        self._skills = SkillSynthesizer(pkg_dir / "knowledge" / "skills")
        self._curator = Curator(playbooks=self._playbooks, skills=self._skills)

    async def run_mission(self, state: MissionState, shared: SharedState | None = None) -> MissionState:
        state.status = MissionStatus.IN_PROGRESS
        await self._event_bus.publish(
            Event(type=EventType.MISSION_STARTED, data={"mission_id": state.mission_id, "brief": state.brief}, source="coordinator")
        )

        try:
            # M commissions the mission first: prune agents/tools/skills per task
            # (annotates task.metadata) so downstream agents run lean. Recording
            # the plan is best-effort and never blocks execution.
            self._commission_mission(state)

            self._build_graph(state)
            schedule = self._scheduler.compute_schedule()
            self._memory.strategic.record_decision(
                decision_id=f"schedule_{state.mission_id}",
                title="Execution schedule",
                description=f"Schedule with {len(schedule.order)} tasks across {len(schedule.parallel_batches)} batches",
                alternatives=[],
                chosen="topological_sort",
                rationale="Optimal parallelization with dependency resolution",
                author="coordinator",
                tags=["scheduling", state.mission_id],
            )

            for batch_idx, batch in enumerate(schedule.parallel_batches):
                batch_tasks = [state.tasks[tid] for tid in batch if tid in state.tasks]
                await self._execute_batch(batch_tasks, state, batch_idx, schedule)

            self._finalize_mission(state)

        except CyclicDependencyError as e:
            state.status = MissionStatus.FAILED
            self._persist_state(state)
            await self._event_bus.publish(
                Event(type=EventType.MISSION_FAILED, data={"mission_id": state.mission_id, "error": str(e)}, source="coordinator")
            )

        except Exception as e:
            state.status = MissionStatus.FAILED
            self._persist_state(state)
            await self._event_bus.publish(
                Event(type=EventType.MISSION_FAILED, data={"mission_id": state.mission_id, "error": str(e)}, source="coordinator")
            )

        return state

    def _commission_mission(self, state: MissionState) -> None:
        """Run M's dispatcher, annotate tasks, and record the plan (best-effort)."""
        try:
            plan = self._dispatcher.commission(state, annotate=True)
        except Exception as e:  # never let commissioning block a mission
            print(f"[coordinator] commission skipped: {e}")
            return

        savings = self._dispatcher.estimate_savings(plan)

        # 1) Strategic memory — durable, queryable record of the plan.
        try:
            self._memory.strategic.record_decision(
                decision_id=f"commission_{state.mission_id}",
                title="M commission plan",
                description=(
                    f"Activated {len(plan.activated_agents)} agents; "
                    f"dropped {savings['tool_schemas_dropped']} tool schemas "
                    f"({savings['tool_schemas_exposed']} exposed)."
                ),
                alternatives=["commission all agents with full toolsets"],
                chosen="selective_commission",
                rationale="Minimise token usage by activating only required agents/tools.",
                author="M",
                tags=["commission", "dispatch", state.mission_id],
            )
        except Exception as e:
            print(f"[coordinator] commission memory write failed: {e}")

        # 2) Obsidian — store the plan as a subnode under the Logs branch.
        try:
            from cressida.obsidian.bridge import get_bridge

            bridge = get_bridge()
            if bridge is not None:
                body = self._render_commission_note(plan, savings)
                bridge.store_subnode(
                    branch="logs",
                    title=f"Commission — {state.mission_id}",
                    content=body,
                    tags=["commission", "dispatch"],
                    metadata={"mission_id": state.mission_id, "agent": "M"},
                )
        except Exception as e:
            print(f"[coordinator] commission obsidian write failed: {e}")

    @staticmethod
    def _render_commission_note(plan: Any, savings: dict[str, int]) -> str:
        lines = [
            f"# Commission Plan — {plan.mission_id}",
            "",
            f"**Activated agents:** {', '.join(a.value for a in plan.activated_agents)}",
            f"**Tool schemas exposed:** {savings['tool_schemas_exposed']}  ",
            f"**Tool schemas dropped:** {savings['tool_schemas_dropped']}  ",
            f"**Agents activated / available:** {savings['agents_activated']} / {savings['agents_available']}",
            "",
            "## Per-task commission",
            "",
            "| Task | Agent | Tools | Skills | Model | Skip |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for c in plan.per_task:
            lines.append(
                f"| {c.task_id} | {c.agent.value} | {', '.join(c.tools) or '—'} | "
                f"{', '.join(c.skills) or '—'} | {c.model or 'default'} | {'yes' if c.skip else 'no'} |"
            )
        return "\n".join(lines)

    def _build_graph(self, state: MissionState) -> None:
        for task_id, task in state.tasks.items():
            self._graph.add_node(task_id, weight=task.priority.value if hasattr(task.priority, "value") else 50)
        for task_id, task in state.tasks.items():
            for dep_id in task.depends_on:
                self._graph.add_dependency(task_id, dep_id)

    async def _execute_batch(
        self,
        tasks: list[Task],
        state: MissionState,
        batch_idx: int,
        schedule: Any,
    ) -> None:
        pending: list[Task] = [t for t in tasks if t.status == TaskStatus.PENDING]
        if not pending:
            return

        if len(pending) == 1:
            await self._executor.execute_task(pending[0], state)
        else:
            await self._executor.execute_parallel(pending, state)

        for task in pending:
            if task.status == TaskStatus.COMPLETED:
                state.complete_task(task.id)
                await self._event_bus.publish(
                    Event(type=EventType.EVALUATION_RECORDED, data={
                        "task_id": task.id,
                        "agent": str(task.agent) if task.agent else "unknown",
                        "execution_time": task.execution_time,
                    }, source="coordinator")
                )
            elif task.status == TaskStatus.FAILED:
                state.fail_task(task.id, task.error or "unknown error")

        self._persist_state(state)

    def _finalize_mission(self, state: MissionState) -> None:
        all_completed = all(
            t.status == TaskStatus.COMPLETED for t in state.tasks.values()
        )
        any_failed = any(
            t.status == TaskStatus.FAILED for t in state.tasks.values()
        )

        if all_completed:
            state.status = MissionStatus.COMPLETED
            self._event_bus.publish(
                Event(type=EventType.MISSION_COMPLETED, data={"mission_id": state.mission_id}, source="coordinator")
            )
        elif any_failed:
            state.status = MissionStatus.FAILED
            self._event_bus.publish(
                Event(type=EventType.MISSION_FAILED, data={"mission_id": state.mission_id, "error": "One or more tasks failed"}, source="coordinator")
            )
        else:
            state.status = MissionStatus.COMPLETED
            self._event_bus.publish(
                Event(type=EventType.MISSION_COMPLETED, data={"mission_id": state.mission_id}, source="coordinator")
            )

        # Close the learning loop: distil this mission's experience into agent
        # playbooks, mint/refresh skills, and consolidate. Best-effort — never
        # allowed to affect the mission's outcome.
        self._learn_from_mission(state)

        self._persist_state(state)

    def _learn_from_mission(self, state: MissionState) -> None:
        """Run reflection + skill synthesis + consolidation after a mission."""
        try:
            insights = self._reflection.reflect_on_mission(
                state,
                strategic_memory=self._memory.strategic,
            )
            skills = self._skills.synthesize_from_mission(state)
            self._curator.consolidate_all(decay=False)
            print(
                f"[learning] mission {state.mission_id}: "
                f"{len(insights)} lesson(s), {len(skills)} skill(s) touched."
            )
        except Exception as e:  # learning must never break a mission
            print(f"[coordinator] learning skipped: {e}")

    def _persist_state(self, state: MissionState) -> None:
        """Write execution_state.json so MCP status tools can read it."""
        # Canonical mission dir — see core/paths.py. The previous
        # `Path(__file__).parent.parent.parent` climbed one level above the repo
        # root and wrote missions outside it, splitting them from agent output.
        path = mission_dir(state.mission_id) / "execution_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tasks_data = {}
        for tid, task in state.tasks.items():
            tasks_data[tid] = {
                "status": task.status.value if hasattr(task.status, "value") else str(task.status),
                "agent": task.agent.value if task.agent else None,
                "name": task.name,
                "error": task.error,
            }
        payload = {
            "mission_id": state.mission_id,
            "status": state.status.value if hasattr(state.status, "value") else str(state.status),
            "tasks": tasks_data,
            "updated_at": datetime.now().isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
