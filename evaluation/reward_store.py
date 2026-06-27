from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cressida.core.events import Event, EventType


class RewardStore:
    def __init__(self, base_path: str | Path = "evaluations") -> None:
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._records: list[dict[str, Any]] = []

    def record(
        self,
        state: dict[str, Any],
        action: str,
        outcome: str,
        reward: float | None,
        agent: str,
        mission_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "state": state,
            "action": action,
            "outcome": outcome,
            "reward": reward,
            "agent": agent,
            "mission_id": mission_id,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        self._records.append(record)
        self._persist(mission_id, record)
        return record

    def handle_feedback_received(self, event: Event) -> None:
        if event.type != EventType.FEEDBACK_RECEIVED:
            return
        data = event.data
        record_data = data.get("record", {})
        self.record(
            state={"task_id": data.get("task_id", "")},
            action="agent_execution",
            outcome=record_data.get("outcome", "completed"),
            reward=data.get("score"),
            agent=record_data.get("agent", ""),
            mission_id=data.get("mission_id", ""),
            metadata={"comment": data.get("comment", "")},
        )

    def _persist(self, mission_id: str, record: dict[str, Any]) -> None:
        if mission_id:
            mission_dir = self._base_path / mission_id
            mission_dir.mkdir(parents=True, exist_ok=True)
            filepath = mission_dir / "reward_records.jsonl"
        else:
            filepath = self._base_path / "reward_records.jsonl"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def get_records(
        self,
        agent: str | None = None,
        mission_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        results = list(self._records)
        if agent:
            results = [r for r in results if r["agent"] == agent]
        if mission_id:
            results = [r for r in results if r["mission_id"] == mission_id]
        return results[-limit:]

    def get_all(self) -> list[dict[str, Any]]:
        return list(self._records)

    def get_all_for_mission(self, mission_id: str) -> list[dict[str, Any]]:
        filepath = self._base_path / mission_id / "reward_records.jsonl"
        if not filepath.exists():
            return []
        records = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def export_jsonl(self, path: str | Path | None = None) -> str:
        export_path = Path(path) if path else self._base_path / "reward_export.jsonl"
        with open(export_path, "w", encoding="utf-8") as f:
            for record in self._records:
                f.write(json.dumps(record) + "\n")
        return str(export_path)

    def clear(self) -> None:
        self._records.clear()
