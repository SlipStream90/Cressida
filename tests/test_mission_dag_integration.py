"""End-to-end mission DAG test with a mocked provider — the "confirmed gap"
called out in CRESSIDA_ROBUSTNESS_AND_RETRIEVAL_PLAN.md: no committed test
exercised research -> ... -> BOND -> planning -> implementation -> review
with a real Coordinator.run_mission() call. This catches regressions like
the BOND markdown-parser bug that only ever showed up on a live mission
before (see tests/test_bond_gate_parser.py for the narrower unit test).

The mocked agent is deliberately dumb: it satisfies exactly the two things
Coordinator/TaskExecutor actually check (BOND must produce a parseable
APPROVED decision file; BRANCH/implementation must write a file, or
TaskExecutor fails it — see executor.py's _VERIFY_FILES_WRITTEN_ROLES) and
otherwise just returns a string. No LLM, no subprocess, no network."""

from __future__ import annotations

import json

import pytest

from cressida.cli.commands import _build_mission_state
from cressida.core import AgentRole, MissionState, MissionStatus, Task, TaskStatus
from cressida.core.events import EventBus, EventType
from cressida.core.paths import mission_dir
from cressida.core.registry import AgentRegistry
from cressida.memory.system import MemorySystem
from cressida.orchestration.coordinator import Coordinator


class _MockAgent:
    """Minimal Agent implementation — writes what the gate/verification checks
    for its role, otherwise just returns a short string."""

    def __init__(self, role: AgentRole) -> None:
        self.role = role

    async def get_capabilities(self) -> list[str]:
        return ["*"]

    async def execute(self, state: MissionState, task: Task, event_bus: EventBus | None = None):
        if self.role == AgentRole.BOND:
            decisions_dir = mission_dir(state.mission_id) / "bond_decisions"
            decisions_dir.mkdir(parents=True, exist_ok=True)
            (decisions_dir / f"{task.id}.json").write_text(json.dumps({
                "decision": "APPROVED",
                "reason": "mock approval for integration test",
                "approved_mcp_tools": [],
            }), encoding="utf-8")
        elif self.role == AgentRole.BRANCH:
            # TaskExecutor._VERIFY_FILES_WRITTEN_ROLES requires BRANCH to
            # actually write a file, or the task is force-FAILED.
            from cressida.core.paths import project_dir
            target = project_dir(state)
            target.mkdir(parents=True, exist_ok=True)
            (target / "mock_output.txt").write_text("mock implementation output", encoding="utf-8")
        if task.metadata.get("writes"):
            from cressida.core.paths import resolve_mission_artifact_path
            for raw_path in task.metadata["writes"]:
                path = resolve_mission_artifact_path(
                    raw_path.replace("<mission_id>", state.mission_id), state.mission_id
                )
                target = path if path.suffix else path / f"{task.id}.md"
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_text(f"mock artifact for {task.id}", encoding="utf-8")
        return f"mock output for {task.id}"


def _mock_registry() -> AgentRegistry:
    registry = AgentRegistry()
    for role in AgentRole:
        registry.register(_MockAgent(role))
    return registry


@pytest.mark.asyncio
async def test_full_dag_completes_with_mocked_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path / "missions"))
    mission_id = "mission_dag_integration_test"
    project = tmp_path / "project"
    project.mkdir()

    state = _build_mission_state(mission_id, "build a small utility", target_dir=str(project))
    assert "bond_approve_plan" in state.tasks
    assert "implementation" in state.tasks
    assert "review" in state.tasks

    coordinator = Coordinator(_mock_registry(), EventBus(), MemorySystem())
    result = await coordinator.run_mission(state)

    assert result.status == MissionStatus.COMPLETED, (
        f"mission did not complete: status={result.status}, "
        f"errors={[(t.id, t.error) for t in result.tasks.values() if t.error]}"
    )
    for task in result.tasks.values():
        assert task.status == TaskStatus.COMPLETED, f"{task.id} was left {task.status}: {task.error}"

    exec_state = json.loads((mission_dir(mission_id) / "execution_state.json").read_text(encoding="utf-8"))
    assert exec_state["status"] == "COMPLETED"
    assert (project / "mock_output.txt").exists()


@pytest.mark.asyncio
async def test_bond_rejection_escalates_and_blocks_downstream(tmp_path, monkeypatch):
    """A REJECTED BOND decision must stop the mission before planning/
    implementation ever run — the exact gate this file's parser bug used to
    silently defeat."""
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path / "missions"))
    mission_id = "mission_dag_bond_reject_test"
    project = tmp_path / "project"
    project.mkdir()

    class _RejectingBond(_MockAgent):
        async def execute(self, state, task, event_bus=None):
            decisions_dir = mission_dir(state.mission_id) / "bond_decisions"
            decisions_dir.mkdir(parents=True, exist_ok=True)
            (decisions_dir / f"{task.id}.json").write_text(json.dumps({
                "decision": "REJECTED", "reason": "not ready", "approved_mcp_tools": [],
            }), encoding="utf-8")
            return "rejected"

    registry = _mock_registry()
    registry.unregister(AgentRole.BOND)
    registry.register(_RejectingBond(AgentRole.BOND))

    state = _build_mission_state(mission_id, "build a small utility", target_dir=str(project))
    coordinator = Coordinator(registry, EventBus(), MemorySystem())
    result = await coordinator.run_mission(state)

    assert result.status == MissionStatus.ESCALATED
    assert result.tasks["planning"].status == TaskStatus.PENDING
    assert result.tasks["implementation"].status == TaskStatus.PENDING
    assert not (project / "mock_output.txt").exists()


@pytest.mark.asyncio
async def test_every_task_announces_a_start_event(tmp_path, monkeypatch):
    """Each task must publish TASK_STARTED before its agent runs.

    Without it the only task-level events on the bus are completions, so a
    mission running a slow agent looks identical to a dead one — every task
    reads PENDING in the dashboard and `cressida watch` reports "idle /
    between tasks" while an agent is actively working."""
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path / "missions"))
    mission_id = "mission_dag_task_started_test"
    project = tmp_path / "project"
    project.mkdir()

    started: list[str] = []
    bus = EventBus()

    async def _record(event):
        started.append(event.data.get("task_id"))

    bus.subscribe(EventType.TASK_STARTED, _record)

    state = _build_mission_state(mission_id, "build a small utility", target_dir=str(project))
    result = await Coordinator(_mock_registry(), bus, MemorySystem()).run_mission(state)

    assert result.status == MissionStatus.COMPLETED
    assert set(started) == set(result.tasks), (
        f"tasks with no TASK_STARTED event: {set(result.tasks) - set(started)}"
    )


@pytest.mark.asyncio
async def test_failed_task_blocks_its_dependents(tmp_path, monkeypatch):
    """A task whose dependency failed must not run.

    The schedule is computed once, up front, from the dependency graph — so
    nothing re-checked whether a batch's dependencies actually *succeeded*.
    Observed live: `architecture` completed on a mission whose
    `product_definition` had failed, i.e. Q designed against a PRD that was
    never written."""
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path / "missions"))
    mission_id = "mission_dag_blocked_downstream_test"
    project = tmp_path / "project"
    project.mkdir()

    class _FailingIntelligence(_MockAgent):
        async def execute(self, state, task, event_bus=None):
            if task.id == "product_definition":
                raise RuntimeError("simulated provider failure")
            return await super().execute(state, task, event_bus=event_bus)

    registry = AgentRegistry()
    for role in AgentRole:
        registry.register(
            _FailingIntelligence(role) if role == AgentRole.INTELLIGENCE else _MockAgent(role)
        )

    state = _build_mission_state(mission_id, "build a small utility", target_dir=str(project))
    result = await Coordinator(registry, EventBus(), MemorySystem()).run_mission(state)

    assert result.tasks["product_definition"].status == TaskStatus.FAILED
    # architecture depends on product_definition — it must be blocked, not run.
    arch = result.tasks["architecture"]
    assert arch.status == TaskStatus.BLOCKED, arch.status
    assert "product_definition" in (arch.error or "")
    assert result.status != MissionStatus.COMPLETED


@pytest.mark.asyncio
async def test_upstream_failure_blocks_all_descendants(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path / "missions"))
    mission_id = "mission_dag_upstream_failure_test"
    project = tmp_path / "project"
    project.mkdir()

    class _FailingResearch(_MockAgent):
        async def execute(self, state, task, event_bus=None):
            if task.id == "research":
                raise RuntimeError("research provider unavailable")
            return await super().execute(state, task, event_bus)

    registry = AgentRegistry()
    for role in AgentRole:
        registry.register(_FailingResearch(role))

    state = _build_mission_state(mission_id, "build a small utility", target_dir=str(project))
    result = await Coordinator(registry, EventBus(), MemorySystem()).run_mission(state)

    assert result.status == MissionStatus.FAILED
    assert result.tasks["research"].status == TaskStatus.FAILED
    assert result.tasks["product_definition"].status == TaskStatus.BLOCKED
    assert result.tasks["architecture"].status == TaskStatus.BLOCKED
    assert result.tasks["implementation"].status == TaskStatus.BLOCKED
    assert not (project / "mock_output.txt").exists()
