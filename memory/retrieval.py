from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class MemoryRetrieval:
    def __init__(self, knowledge_path: str | Path = "knowledge", missions_path: str | Path = "missions") -> None:
        self._knowledge_path = Path(knowledge_path)
        self._missions_path = Path(missions_path)

    def query(
        self,
        task_type: str = "",
        agent_name: str = "",
        keywords: list[str] | None = None,
        top_k: int = 5,
        include_mission_id: str = "",
    ) -> list[dict[str, Any]]:
        keywords = keywords or []
        chunks: list[dict[str, Any]] = []
        search_paths = [self._knowledge_path]
        if include_mission_id:
            mission_path = self._missions_path / include_mission_id
            if mission_path.exists():
                search_paths.append(mission_path)
        for base in search_paths:
            for path in base.rglob("*"):
                if path.is_file() and path.suffix in (".md", ".json", ".yaml", ".txt"):
                    chunks.extend(self._chunk_file(path, base))

        scored = []
        for chunk in chunks:
            score = self._score_chunk(chunk, task_type, agent_name, keywords)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:top_k]]

    def keyword_query(
        self,
        keywords: list[str],
        top_k: int = 5,
        include_mission_id: str = "",
    ) -> list[dict[str, Any]]:
        return self.query(keywords=keywords, top_k=top_k, include_mission_id=include_mission_id)

    def semantic_query(
        self,
        keywords: list[str],
        top_k: int = 5,
        include_mission_id: str = "",
    ) -> list[dict[str, Any]]:
        return self.keyword_query(keywords, top_k, include_mission_id)

    def _chunk_file(self, path: Path, base: Path) -> list[dict[str, Any]]:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return []
        rel = path.relative_to(base)
        rel_str = str(rel.as_posix())
        now = datetime.now()
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        age_hours = (now - mtime).total_seconds() / 3600
        chunks = []
        sections = re.split(r"\n(?=#+\s)", text)
        for i, section in enumerate(sections):
            if not section.strip():
                continue
            chunks.append({
                "content": section.strip()[:2000],
                "source": rel_str,
                "section_index": i,
                "age_hours": age_hours,
                "path": str(path),
            })
        return chunks

    def _score_chunk(self, chunk: dict[str, Any], task_type: str, agent_name: str, keywords: list[str]) -> float:
        score = 0.0
        content_lower = chunk["content"].lower()
        source_lower = chunk["source"].lower()
        if task_type and task_type.lower() in content_lower:
            score += 3.0
        if agent_name and agent_name.lower() in content_lower:
            score += 2.0
        if agent_name and agent_name.lower() in source_lower:
            score += 1.0
        for kw in keywords:
            kw_lower = kw.lower()
            count = content_lower.count(kw_lower)
            score += count * 1.0
            if kw_lower in source_lower:
                score += 0.5
        recency_bonus = max(0.0, 5.0 - chunk["age_hours"] / 24.0) * 0.2
        score += recency_bonus
        return score
