from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentState(BaseModel):
    role: str
    status: str = "IDLE"
    current_task_id: str | None = None
    completed_tasks: list[str] = Field(default_factory=list)
    failed_tasks: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    last_active: datetime | None = None
    error_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def assign_task(self, task_id: str) -> None:
        self.status = "BUSY"
        self.current_task_id = task_id
        self.last_active = datetime.now()

    def complete_task(self, task_id: str) -> None:
        self.status = "IDLE"
        if task_id not in self.completed_tasks:
            self.completed_tasks.append(task_id)
        if self.current_task_id == task_id:
            self.current_task_id = None
        self.last_active = datetime.now()

    def fail_task(self, task_id: str) -> None:
        self.status = "IDLE"
        if task_id not in self.failed_tasks:
            self.failed_tasks.append(task_id)
        if self.current_task_id == task_id:
            self.current_task_id = None
        self.error_count += 1
        self.last_active = datetime.now()

    @property
    def is_available(self) -> bool:
        return self.status == "IDLE"

    model_config = {"frozen": False}
