from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from cressida.core.events import Event, EventBus, EventType
from cressida.core.types import EvaluationRecord


class FeedbackCollector:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def submit_feedback(
        self,
        task_id: str,
        score: float,
        comment: str,
        agent: str = "",
        execution_time: float | None = None,
        outcome: str = "completed",
        tests_passed: bool | None = None,
        architecture_compliance: float | None = None,
    ) -> EvaluationRecord:
        record = EvaluationRecord(
            task_id=task_id,
            agent=agent,
            execution_time=execution_time,
            outcome=outcome,
            review_score=score,
            tests_passed=tests_passed,
            architecture_compliance=architecture_compliance,
            human_feedback=comment,
        )
        await self._event_bus.publish(Event(
            type=EventType.FEEDBACK_RECEIVED,
            data={
                "task_id": task_id,
                "score": score,
                "comment": comment,
                "record": {
                    "task_id": task_id,
                    "agent": agent,
                    "execution_time": execution_time,
                    "outcome": outcome,
                    "review_score": score,
                    "tests_passed": tests_passed,
                    "architecture_compliance": architecture_compliance,
                    "human_feedback": comment,
                },
            },
            source="feedback_collector",
        ))
        return record

    async def fill_null_feedback(self, evaluation_records: list[EvaluationRecord]) -> list[EvaluationRecord]:
        filled = []
        for rec in evaluation_records:
            if rec.human_feedback is None:
                filled.append(rec)
        return filled
