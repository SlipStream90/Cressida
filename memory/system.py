from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from cressida.memory.agent import AgentMemory
from cressida.memory.mission import MissionMemory
from cressida.memory.retrieval import MemoryRetrieval
from cressida.memory.strategic import StrategicMemory


class MemorySystem:
    def __init__(self, base_path: str | Path = "memory") -> None:
        self.strategic = StrategicMemory(base_path)
        self.mission = MissionMemory()
        self.agent = AgentMemory()
        self.retrieval = MemoryRetrieval()
        self._base_path = Path(base_path)

    def write(
        self,
        path: str | Path,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        metadata = metadata or {}
        resolved = self._base_path / path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        record = [
            f"<!-- {metadata.get('timestamp', datetime.now().isoformat())} -->",
            f"<!-- mission_id: {metadata.get('mission_id', '')} -->",
            f"<!-- agent: {metadata.get('agent', '')} -->",
            f"<!-- task_id: {metadata.get('task_id', '')} -->",
            f"<!-- tags: {','.join(metadata.get('tags', []))} -->",
            "",
            content,
        ]
        resolved.write_text("\n".join(record), encoding="utf-8")

    def query(
        self,
        task_type: str = "",
        keywords: list[str] | None = None,
        top_k: int = 5,
        include_mission_id: str = "",
    ) -> list[dict[str, Any]]:
        return self.retrieval.query(
            task_type=task_type,
            keywords=keywords or [],
            top_k=top_k,
            include_mission_id=include_mission_id,
        )
