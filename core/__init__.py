from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class AgentRole(enum.StrEnum):
    M = "M"
    R = "R"
    BOND = "BOND"
    INTELLIGENCE = "INTELLIGENCE"
    LEITER = "LEITER"
    Q = "Q"
    TANNER = "TANNER"
    BRANCH = "BRANCH"
    ROOK = "ROOK"
    BOOTHROYD = "BOOTHROYD"
    MONEYPENNY = "MONEYPENNY"
    REVIEW = "REVIEW"


class MissionStatus(enum.StrEnum):
    PENDING = "PENDING"
    RESEARCHING = "RESEARCHING"
    PLANNING = "PLANNING"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskStatus(enum.StrEnum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class Priority(enum.IntEnum):
    LOWEST = 0
    LOW = 25
    MEDIUM = 50
    HIGH = 75
    CRITICAL = 100


@dataclass
class ArchitectureDecision:
    id: str
    title: str
    description: str
    alternatives: list[str]
    chosen: str
    rationale: str
    author: AgentRole
    timestamp: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)


@dataclass
class Task:
    id: str
    name: str
    description: str
    agent: AgentRole | None = None
    depends_on: list[str] = field(default_factory=list)
    priority: Priority = Priority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    output: Any = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def execution_time(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class AgentAssignment:
    agent: AgentRole
    task_id: str
    assigned_at: datetime = field(default_factory=datetime.now)


@dataclass
class EvaluationRecord:
    task_id: str
    agent: AgentRole
    execution_time: float | None
    outcome: str
    review_score: float | None
    tests_passed: bool | None
    architecture_compliance: float | None
    human_feedback: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RLHFRecord:
    state: dict[str, Any]
    action: str
    outcome: str
    reward: float | None
    agent: AgentRole
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ReviewReport:
    reviewer: AgentRole
    target_task_id: str
    score: float
    findings: list[str]
    recommendations: list[str]
    approved: bool
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AgentMessage:
    sender: AgentRole
    recipient: AgentRole
    subject: str
    body: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MissionState:
    mission_id: str
    brief: str
    status: MissionStatus = MissionStatus.PENDING
    objectives: list[str] = field(default_factory=list)
    completed_objectives: list[str] = field(default_factory=list)
    pending_objectives: list[str] = field(default_factory=list)
    tasks: dict[str, Task] = field(default_factory=dict)
    agent_assignments: dict[str, AgentAssignment] = field(default_factory=dict)
    architecture_decisions: list[ArchitectureDecision] = field(default_factory=list)
    review_reports: list[ReviewReport] = field(default_factory=list)
    evaluation_metrics: list[EvaluationRecord] = field(default_factory=list)
    messages: list[AgentMessage] = field(default_factory=list)
    rlhf_records: list[RLHFRecord] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_task(self, task: Task) -> None:
        self.tasks[task.id] = task
        self.pending_objectives.append(task.id)
        self.updated_at = datetime.now()

    def complete_task(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            if task_id in self.pending_objectives:
                self.pending_objectives.remove(task_id)
            self.completed_objectives.append(task_id)
            self.updated_at = datetime.now()

    def fail_task(self, task_id: str, error: str) -> None:
        task = self.tasks.get(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.error = error
            self.updated_at = datetime.now()
