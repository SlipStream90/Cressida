from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class StrategicMemory:
    def __init__(self, base_path: str | Path = "memory") -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._architecture: dict[str, Any] = self._load_json("architecture.json")
        self._decisions: list[dict[str, Any]] = self._load_json("decisions.json", [])
        self._patterns: list[dict[str, Any]] = self._load_json("learned_patterns.json", [])

    def _load_json(self, name: str, default: Any = None) -> Any:
        path = self.base_path / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return default if default is not None else {}

    def _save_json(self, name: str, data: Any) -> None:
        path = self.base_path / name
        path.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )

    def record_decision(
        self,
        decision_id: str,
        title: str,
        description: str,
        alternatives: list[str],
        chosen: str,
        rationale: str,
        author: str,
        tags: list[str] | None = None,
    ) -> None:
        record = {
            "id": decision_id,
            "title": title,
            "description": description,
            "alternatives": alternatives,
            "chosen": chosen,
            "rationale": rationale,
            "author": author,
            "timestamp": datetime.now().isoformat(),
            "tags": tags or [],
        }
        self._decisions.append(record)
        self._save_json("decisions.json", self._decisions)

    def record_pattern(self, pattern: str, context: str, success: bool) -> None:
        record = {
            "pattern": pattern,
            "context": context,
            "success": success,
            "timestamp": datetime.now().isoformat(),
        }
        self._patterns.append(record)
        self._save_json("learned_patterns.json", self._patterns)

    def update_architecture(self, key: str, value: Any) -> None:
        self._architecture[key] = value
        self._save_json("architecture.json", self._architecture)

    def get_architecture(self) -> dict[str, Any]:
        return dict(self._architecture)

    def get_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._decisions[-limit:])

    def get_patterns(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._patterns[-limit:])
