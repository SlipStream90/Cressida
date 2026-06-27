from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MissionStateModel(BaseModel):
    mission_id: str
    brief: str
    status: str = "PENDING"
    objectives: list[str] = Field(default_factory=list)
    completed_objectives: list[str] = Field(default_factory=list)
    failed_objectives: list[str] = Field(default_factory=list)
    blocked_objectives: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def complete_objective(self, objective_id: str) -> None:
        if objective_id in self.objectives and objective_id not in self.completed_objectives:
            self.completed_objectives.append(objective_id)
        if objective_id in self.failed_objectives:
            self.failed_objectives.remove(objective_id)
        if objective_id in self.blocked_objectives:
            self.blocked_objectives.remove(objective_id)
        self.updated_at = datetime.now()

    def fail_objective(self, objective_id: str) -> None:
        if objective_id not in self.failed_objectives:
            self.failed_objectives.append(objective_id)
        self.updated_at = datetime.now()

    def block_objective(self, objective_id: str) -> None:
        if objective_id not in self.blocked_objectives:
            self.blocked_objectives.append(objective_id)
        self.updated_at = datetime.now()

    @property
    def progress(self) -> float:
        if not self.objectives:
            return 0.0
        return len(self.completed_objectives) / len(self.objectives)

    @property
    def is_complete(self) -> bool:
        return len(self.completed_objectives) == len(self.objectives)

    model_config = {"frozen": False}
