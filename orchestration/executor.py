from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cressida.core.events import Event, EventBus, EventType
from cressida.core.paths import mission_dir, project_dir
from cressida.core.registry import AgentRegistry
from cressida.core.types import AgentRole, MissionState, Task, TaskStatus, Priority
from cressida.orchestration.context_builder import ContextBuilder
from cressida.orchestration.dependency_graph import DependencyGraph
from cressida.orchestration.router import RoutingError, TaskRouter
from cressida.core.providers.base import declared_write_targets
from cressida.core.providers.fallback import has_usable_output

# Roles whose job is to persist files (not just return prose) — a mission
# genuinely stalling on write access still returns a normal-looking text
# response (the agent narrates the code it couldn't save instead of raising),
# so "the coroutine didn't throw" is not sufficient evidence of success for
# these roles. See mission_20260728_130409: BRANCH's implementation task was
# recorded COMPLETED with error=None despite writing zero files, because the
# CLI subprocess it shells out to had its write access denied and it returned
# a description of the code as chat text instead.
_VERIFY_FILES_WRITTEN_ROLES = {AgentRole.BRANCH}


def _wrote_files_since(
    mission_id: str, since: datetime, target_dir: Path | None = None,
    ignore: set[Path] | None = None,
) -> bool:
    """True if any file under the mission dir (or the mission's target project
    dir, when given) was created/modified at or after `since`.

    ``ignore`` excludes the task's own declared output files — the ones
    ProviderAgentBase._write_output persists from the agent's closing message
    *before* this check runs. Counting them made this guard validate its own
    side effect: it could never fail, and the exact failure it exists to catch
    walked straight through it. Observed live on
    missions/20260816-small-url-shortener-service-03: BRANCH wrote no code at
    all, the mission was marked COMPLETED, and REVIEW — reviewing nothing —
    scored the delivery 2.0/10.
    """
    # A little slack for filesystem mtime resolution / clock skew between the
    # agent subprocess and this process.
    cutoff = since.timestamp() - 2.0
    ignored = {p.resolve() for p in (ignore or set())}
    dirs = [mission_dir(mission_id)]
    if target_dir is not None:
        dirs.append(target_dir)
    for d in dirs:
        if not d.exists():
            continue
        for f in d.rglob("*"):
            if f.is_file():
                try:
                    if f.resolve() in ignored:
                        continue
                    if f.stat().st_mtime >= cutoff:
                        return True
                except OSError:
                    continue
    return False


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
            ready = [tid for tid in graph.get_ready_nodes(completed) if task_status.get(tid) == "pending"]
            if not ready:
                for tid, status in task_status.items():
                    if status == "pending":
                        task_status[tid] = "blocked"
                break
            for tid in ready:
                task_status[tid] = "in_progress"

            tasks = [tasks_by_id[tid] for tid in ready]
            await self._execute_batch(tasks, mission_id, brief, objectives, task_status, completed)

            # A failed task cannot satisfy its dependents. Mark the dependent
            # chain explicitly so the backlog reaches a deterministic terminal
            # state instead of waiting for a graph deadlock to imply it.
            blocked = True
            while blocked:
                blocked = False
                for tid, item in tasks_by_id.items():
                    if task_status.get(tid) != "pending":
                        continue
                    dependencies = item.get("dependencies", [])
                    failed_dependency = next(
                        (dep for dep in dependencies if task_status.get(dep) in ("failed", "blocked")),
                        None,
                    )
                    if failed_dependency is None:
                        continue
                    task_status[tid] = "blocked"
                    blocked = True
                    await self._event_bus.publish(Event(
                        type=EventType.TASK_BLOCKED,
                        data={
                            "task_id": tid,
                            "mission_id": mission_id,
                            "error": f"Dependency {failed_dependency} failed or was blocked",
                        },
                        source="executor",
                    ))

            self._persist_state(mission_id, task_status)

        failed = any(v in ("failed", "blocked") for v in task_status.values())
        if failed:
            await self._event_bus.publish(Event(
                type=EventType.MISSION_FAILED,
                data={"mission_id": mission_id, "error": "One or more backlog tasks failed or were blocked"},
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
            writes=item.get("writes", []),
            objectives=objectives,
            target_dir=item.get("project_dir") or None,
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
                    fake_state = MissionState(
                        mission_id=mission_id,
                        brief=brief,
                        metadata={"project_dir": item.get("project_dir", "")},
                    )
                    fake_task = Task(
                        id=tid,
                        name=item.get("name", tid),
                        description=item.get("description", ""),
                        agent=agent_role,
                        metadata={
                            "reads": item.get("reads", []),
                            "writes": item.get("writes", []),
                            "toolset": item.get("toolset", []),
                        },
                    )
                    result = await agent.execute(fake_state, fake_task, event_bus=self._event_bus)
                    if fake_task.metadata.get("writes") and not has_usable_output(
                        fake_state, fake_task, result
                    ):
                        raise RuntimeError(f"Task {tid} produced no usable declared outputs")

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
        # Canonical mission dir — see core/paths.py. The previous
        # `Path(__file__).parent.parent.parent` climbed one level above the repo
        # root and wrote missions outside it, splitting them from agent output
        # (and from the Coordinator-written execution_state.json that resume /
        # mission_status read). Use the shared path so all writers agree.
        path = mission_dir(mission_id) / "execution_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Build tasks dict in the format mission_status expects
        tasks_data = {}
        for tid, status in task_status.items():
            tasks_data[tid] = {
                "status": status,
                "agent": None,
                "name": tid,
                "error": None,
            }
        path.write_text(
            json.dumps({
                "mission_id": mission_id,
                "status": (
                    "failed" if any(s in ("failed", "blocked") for s in task_status.values())
                    else "completed" if all(s == "completed" for s in task_status.values())
                    else "in_progress"
                ),
                "tasks": tasks_data,
                "updated_at": datetime.now().isoformat(),
            }, indent=2),
            encoding="utf-8",
        )

    # Signatures of the transient "-1"/4294967295 (0xFFFFFFFF) exit code class
    # (see core/providers/claude_cli_agent.py) — a Windows job-object/console
    # kill or similar environmental termination, not a logic error in the
    # prompt or task. Three consecutive missions were fully written off by
    # this before a single retry existed on this code path (Coordinator's
    # execute_task, as opposed to the separate execute_backlog path, which
    # already retried) — see CRESSIDA_ROBUSTNESS_AND_RETRIEVAL_PLAN.md §3.3.
    _TRANSIENT_EXIT_CODE_MARKERS = ("exited -1", "exited 4294967295")

    @classmethod
    def _is_transient_failure(cls, error: str) -> bool:
        lowered = error.lower()
        return any(marker in lowered for marker in cls._TRANSIENT_EXIT_CODE_MARKERS)

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

        # Announce the start before the agent runs. Without this nothing is
        # written between mission_started and the task's *completion*, and on
        # a provider that reports tool calls only after its CLI exits
        # (opencode/kilocode) a mission can go 10+ minutes emitting nothing —
        # indistinguishable from a dead process in `cressida watch` and in the
        # dashboard, which then shows every task as PENDING.
        await self._event_bus.publish(Event(
            type=EventType.TASK_STARTED,
            data={"task_id": task.id, "mission_id": state.mission_id, "agent": role.value},
            source="executor",
        ))

        attempt = 0
        max_transient_retries = 2  # 3 total attempts, matching the plan's "2 attempts, exponential"
        while True:
            try:
                result = await agent.execute(state, task, event_bus=self._event_bus)

                # Every declared artifact-producing task must leave a usable
                # artifact. Previously only BRANCH had this guard, so an
                # expired/auth-failed CLI could make research, architecture,
                # or BOND appear COMPLETED with zero-byte files.
                if (
                    role != AgentRole.BRANCH
                    and task.metadata.get("writes")
                    and not has_usable_output(
                        state, task, result
                    )
                ):
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now()
                    task.output = result
                    task.error = (
                        f"{role.value} returned without producing usable declared outputs "
                        f"for task {task.id}; refusing to mark the task completed."
                    )
                    await self._event_bus.publish(Event(
                        type=EventType.TASK_FAILED,
                        data={"task_id": task.id, "mission_id": state.mission_id, "error": task.error},
                        source="executor",
                    ))
                    return

                if role in _VERIFY_FILES_WRITTEN_ROLES and not _wrote_files_since(
                    state.mission_id, task.started_at, project_dir(state),
                    ignore=declared_write_targets(state.mission_id, task),
                ):
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now()
                    task.output = result
                    task.error = (
                        f"{role.value} returned without writing any files to the mission or "
                        "project directory. Likely a denied file write (e.g. a sandboxed CLI "
                        "subprocess with no one to approve the edit) that the agent narrated "
                        "as text instead of raising — treating that as a completed "
                        "implementation would silently ship no code."
                    )
                    await self._event_bus.publish(Event(
                        type=EventType.TASK_FAILED,
                        data={"task_id": task.id, "mission_id": state.mission_id, "error": task.error},
                        source="executor",
                    ))
                    return

                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now()
                task.output = result
                await self._event_bus.publish(Event(
                    type=EventType.TASK_COMPLETED,
                    data={"task_id": task.id, "mission_id": state.mission_id},
                    source="executor",
                ))
                return

            except Exception as e:
                error_str = str(e)
                if attempt < max_transient_retries and self._is_transient_failure(error_str):
                    attempt += 1
                    delay = self._retry_delay * (2 ** (attempt - 1))
                    await self._event_bus.publish(Event(
                        type=EventType.TASK_BLOCKED,
                        data={
                            "task_id": task.id, "mission_id": state.mission_id,
                            "error": f"Transient failure (attempt {attempt}/{max_transient_retries}), "
                                     f"retrying in {delay}s: {error_str[:300]}",
                        },
                        source="executor",
                    ))
                    await asyncio.sleep(delay)
                    task.status = TaskStatus.IN_PROGRESS
                    task.started_at = datetime.now()
                    continue

                task.status = TaskStatus.FAILED
                task.error = error_str
                await self._event_bus.publish(Event(
                    type=EventType.TASK_FAILED,
                    data={"task_id": task.id, "mission_id": state.mission_id, "error": error_str},
                    source="executor",
                ))
                return

    async def execute_parallel(self, tasks: list[Task], state: MissionState) -> None:
        await asyncio.gather(*[self.execute_task(t, state) for t in tasks])
