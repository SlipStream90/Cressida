from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cressida.core.types import AgentRole, EvaluationRecord


class EvaluationRecords:
    def __init__(self, base_path: str | Path = "evaluations") -> None:
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._records: list[EvaluationRecord] = []

    def add(self, record: EvaluationRecord) -> None:
        self._records.append(record)

    def create_and_add(
        self,
        task_id: str,
        agent: AgentRole,
        execution_time: float | None,
        outcome: str,
        review_score: float | None = None,
        tests_passed: bool | None = None,
        architecture_compliance: float | None = None,
        human_feedback: str | None = None,
    ) -> EvaluationRecord:
        record = EvaluationRecord(
            task_id=task_id,
            agent=agent,
            execution_time=execution_time,
            outcome=outcome,
            review_score=review_score,
            tests_passed=tests_passed,
            architecture_compliance=architecture_compliance,
            human_feedback=human_feedback,
        )
        self.add(record)
        return record

    def get_by_agent(self, agent: AgentRole) -> list[EvaluationRecord]:
        return [r for r in self._records if r.agent == agent]

    def get_by_outcome(self, outcome: str) -> list[EvaluationRecord]:
        return [r for r in self._records if r.outcome == outcome]

    def get_all(self) -> list[EvaluationRecord]:
        return list(self._records)

    def save_mission(self, mission_id: str) -> str:
        mission_dir = self._base_path / mission_id
        mission_dir.mkdir(parents=True, exist_ok=True)
        filepath = mission_dir / "evaluation_records.json"
        data = [
            {
                "task_id": r.task_id,
                "agent": str(r.agent),
                "execution_time": r.execution_time,
                "outcome": r.outcome,
                "review_score": r.review_score,
                "tests_passed": r.tests_passed,
                "architecture_compliance": r.architecture_compliance,
                "human_feedback": r.human_feedback,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in self._records
        ]
        filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return str(filepath)

    def clear(self) -> None:
        self._records.clear()
