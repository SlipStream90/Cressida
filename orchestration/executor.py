from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cressida.core.events import Event, EventBus, EventType
from cressida.core.registry import AgentRegistry
from cressida.core.types import AgentRole, MissionState, Task, TaskStatus, Priority
from cressida.orchestration.context_builder import ContextBuilder
from cressida.orchestration.dependency_graph import DependencyGraph
from cressida.orchestration.router import RoutingError, TaskRouter


class TaskExecutor:
    def __init__(
        self,
        registry: AgentRegistry,
        router: TaskRouter,
        event_bus: EventBus,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ) -> None:
        self._registry = registry
        self._router = router
        self._event_bus = event_bus
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._context_builder = ContextBuilder()

    async def execute_backlog(
        self,
        backlog_path: str | Path,
        mission_id: str,
        brief: str,
        objectives: list[str] | None = None,
    ) -> None:
        path = Path(backlog_path)
        if not path.exists():
            raise FileNotFoundError(f"Backlog not found: {backlog_path}")
        backlog = json.loads(path.read_text(encoding="utf-8"))

        graph = DependencyGraph()
        tasks_by_id: dict[str, dict[str, Any]] = {}
        for item in backlog:
            tid = item["task_id"]
            graph.add_node(tid)
            tasks_by_id[tid] = item
        for item in backlog:
            for dep in item.get("dependencies", []):
                graph.add_dependency(item["task_id"], dep)

        task_status: dict[str, str] = {item["task_id"]: "pending" for item in backlog}
        completed: set[str] = set()
        batch_num = 0

        while len(completed) < len(backlog):
            batch_num += 1
            ready = [tid for tid in graph.get_ready_nodes(completed) if task_status.get(tid) != "in_progress"]
            if not ready:
                break
            for tid in ready:
                task_status[tid] = "in_progress"

            tasks = [tasks_by_id[tid] for tid in ready]
            await self._execute_batch(tasks, mission_id, brief, objectives, task_status, completed)

            self._persist_state(mission_id, task_status)

        all_failed = all(v == "failed" for v in task_status.values())
        if all_failed:
            await self._event_bus.publish(Event(
                type=EventType.MISSION_FAILED,
                data={"mission_id": mission_id, "error": "All tasks failed"},
                source="executor",
            ))

    async def _execute_batch(
        self,
        tasks: list[dict[str, Any]],
        mission_id: str,
        brief: str,
        objectives: list[str] | None,
        task_status: dict[str, str],
        completed: set[str],
    ) -> None:
        if len(tasks) == 1:
            await self._execute_single(tasks[0], mission_id, brief, objectives, task_status, completed)
        else:
            await asyncio.gather(*[
                self._execute_single(t, mission_id, brief, objectives, task_status, completed)
                for t in tasks
            ])

    async def _execute_single(
        self,
        item: dict[str, Any],
        mission_id: str,
        brief: str,
        objectives: list[str] | None,
        task_status: dict[str, str],
        completed: set[str],
    ) -> None:
        tid = item["task_id"]
        agent_name = item.get("agent", "")
        agent_role = next((r for r in AgentRole if r.value == agent_name), None)
        if not agent_role:
            task_status[tid] = "failed"
            return

        prompt = self._context_builder.build_prompt(
            task_id=tid,
            agent_role=agent_role,
            mission_id=mission_id,
            brief=brief,
            reads=item.get("reads", []),
            task_description=item.get("description", ""),
            objectives=objectives,
        )

        await self._event_bus.publish(Event(
            type=EventType.TASK_STARTED,
            data={"task_id": tid, "mission_id": mission_id, "agent": agent_name},
            source="executor",
        ))

        retries = 0
        while retries <= self._max_retries:
            try:
                agent = self._registry.get(agent_role)
                if agent:
                    fake_state = MissionState(mission_id=mission_id, brief=brief)
                    fake_task = Task(
                        id=tid,
                        name=item.get("name", tid),
                        description=item.get("description", ""),
                        agent=agent_role,
                    )
                    await agent.execute(fake_state, fake_task)

                task_status[tid] = "completed"
                completed.add(tid)
                await self._event_bus.publish(Event(
                    type=EventType.TASK_COMPLETED,
                    data={"task_id": tid, "mission_id": mission_id, "agent": agent_name},
                    source="executor",
                ))
                return

            except Exception as e:
                retries += 1
                if retries <= self._max_retries:
                    await asyncio.sleep(self._retry_delay)
                else:
                    task_status[tid] = "failed"
                    await self._event_bus.publish(Event(
                        type=EventType.TASK_FAILED,
                        data={"task_id": tid, "mission_id": mission_id, "error": str(e), "retries": retries},
                        source="executor",
                    ))
                    await self._event_bus.publish(Event(
                        type=EventType.TASK_BLOCKED,
                        data={"task_id": tid, "mission_id": mission_id, "error": f"Retries exhausted ({retries})"},
                        source="executor",
                    ))

    def _persist_state(self, mission_id: str, task_status: dict[str, str]) -> None:
        path = Path("missions") / mission_id / "execution_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                "mission_id": mission_id,
                "task_status": task_status,
                "updated_at": datetime.now().isoformat(),
            }, indent=2),
            encoding="utf-8",
        )

    async def execute_task(self, task: Task, state: MissionState) -> None:
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now()
        role = task.agent
        if role is None:
            try:
                role = self._router.route(task)
            except RoutingError:
                task.status = TaskStatus.FAILED
                task.error = "No agent could route this task"
                return
        agent = self._registry.get(role)
        if agent is None:
            task.status = TaskStatus.FAILED
            task.error = f"No agent registered for role: {role}"
            return
        try:
            result = await agent.execute(state, task)
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            task.output = result
            await self._event_bus.publish(Event(
                type=EventType.TASK_COMPLETED,
                data={"task_id": task.id, "mission_id": state.mission_id},
                source="executor",
            ))
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            await self._event_bus.publish(Event(
                type=EventType.TASK_FAILED,
                data={"task_id": task.id, "mission_id": state.mission_id, "error": str(e)},
                source="executor",
            ))

    async def execute_parallel(self, tasks: list[Task], state: MissionState) -> None:
        await asyncio.gather(*[self.execute_task(t, state) for t in tasks])
