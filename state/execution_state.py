from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class NodeStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class TaskInfo(BaseModel):
    task_id: str
    status: NodeStatus = NodeStatus.PENDING
    agent: str = ""
    complexity: str = "M"
    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    retries: int = 0
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output_artifact: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionState(BaseModel):
    mission_id: str
    status: str = "PENDING"
    tasks: dict[str, TaskInfo] = Field(default_factory=dict)
    parallel_batches: list[list[str]] = Field(default_factory=list)
    critical_path: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_task(self, info: TaskInfo) -> None:
        self.tasks[info.task_id] = info
        self.updated_at = datetime.now()

    def get_ready_tasks(self) -> list[TaskInfo]:
        completed_ids = {
            tid for tid, t in self.tasks.items()
            if t.status == NodeStatus.COMPLETED
        }
        ready = []
        for task in self.tasks.values():
            if task.status != NodeStatus.PENDING:
                continue
            deps = set(task.dependencies)
            if deps.issubset(completed_ids):
                ready.append(task)
        return ready

    def mark_ready(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if task and task.status == NodeStatus.PENDING:
            task.status = NodeStatus.READY
            self.updated_at = datetime.now()

    def mark_in_progress(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if task:
            task.status = NodeStatus.IN_PROGRESS
            task.started_at = datetime.now()
            self.updated_at = datetime.now()

    def mark_completed(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if task:
            task.status = NodeStatus.COMPLETED
            task.completed_at = datetime.now()
            self.updated_at = datetime.now()

    def mark_failed(self, task_id: str, error: str) -> None:
        task = self.tasks.get(task_id)
        if task:
            task.status = NodeStatus.FAILED
            task.error = error
            self.updated_at = datetime.now()

    def mark_blocked(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if task:
            task.status = NodeStatus.BLOCKED
            self.updated_at = datetime.now()

    @property
    def progress(self) -> float:
        if not self.tasks:
            return 0.0
        completed = sum(1 for t in self.tasks.values() if t.status == NodeStatus.COMPLETED)
        return completed / len(self.tasks)

    @property
    def is_complete(self) -> bool:
        if not self.tasks:
            return False
        return all(t.status == NodeStatus.COMPLETED for t in self.tasks.values())

    model_config = {"frozen": False, "use_enum_values": True}
