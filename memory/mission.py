from __future__ import annotations

from typing import Any

from cressida.core.types import MissionState


class MissionMemory:
    def __init__(self) -> None:
        self._state: MissionState | None = None

    def set_state(self, state: MissionState) -> None:
        self._state = state

    def get_state(self) -> MissionState | None:
        return self._state

    def update_progress(self, **kwargs: Any) -> None:
        if self._state:
            for key, value in kwargs.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)

    def snapshot(self) -> dict[str, Any]:
        if self._state is None:
            return {}
        return {
            "mission_id": self._state.mission_id,
            "status": str(self._state.status),
            "objectives": list(self._state.objectives),
            "completed": list(self._state.completed_objectives),
            "pending": list(self._state.pending_objectives),
            "task_count": len(self._state.tasks),
        }
