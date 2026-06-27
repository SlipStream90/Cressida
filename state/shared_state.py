from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .mission_state import MissionStateModel
from .execution_state import ExecutionState
from .agent_state import AgentState


class SharedState(BaseModel):
    mission: MissionStateModel = Field(default_factory=lambda: MissionStateModel(mission_id="", brief=""))
    execution: ExecutionState = Field(default_factory=lambda: ExecutionState(mission_id=""))
    agents: dict[str, AgentState] = Field(default_factory=dict)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    global_context: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.now)

    def get_agent(self, role: str) -> AgentState:
        if role not in self.agents:
            self.agents[role] = AgentState(role=role)
        return self.agents[role]

    def record_message(self, sender: str, recipient: str, subject: str, body: str) -> None:
        self.messages.append({
            "sender": sender,
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "timestamp": datetime.now().isoformat(),
        })
        self.updated_at = datetime.now()

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump()

    model_config = {"frozen": False}
