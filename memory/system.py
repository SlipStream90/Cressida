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

        # Mirror into Obsidian as a subnode under the appropriate main branch, so
        # every stored memory joins the knowledge graph. Best-effort: a missing
        # or misconfigured vault must never break a local memory write.
        self._mirror_subnode(path, content, metadata)

    def _mirror_subnode(
        self,
        path: str | Path,
        content: str,
        metadata: dict[str, Any],
    ) -> None:
        try:
            from cressida.obsidian.bridge import get_bridge

            bridge = get_bridge()
            if bridge is None:
                return
            branch = metadata.get("branch") or self._infer_branch(str(path), metadata)
            title = metadata.get("title") or Path(str(path)).stem
            if metadata.get("mission_id") and title:
                title = f"{metadata['mission_id']} — {title}"
            bridge.store_subnode(
                branch=branch,
                title=title,
                content=content,
                tags=list(metadata.get("tags", [])),
                metadata=metadata,
            )
        except Exception:
            # Silent by design — memory persistence already succeeded on disk.
            pass

    @staticmethod
    def _infer_branch(path: str, metadata: dict[str, Any]) -> str:
        haystack = f"{path} {' '.join(str(t) for t in metadata.get('tags', []))}".lower()
        if "postmortem" in haystack or "post-mortem" in haystack:
            return "postmortems"
        if "escalat" in haystack:
            return "escalations"
        if "decision" in haystack or "adr" in haystack:
            return "decisions"
        if "log" in haystack:
            return "logs"
        if any(k in haystack for k in ("lesson", "pattern", "knowledge", "learn")):
            return "knowledge"
        return "mission"

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
