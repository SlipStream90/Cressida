from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class EvaluationRecord(BaseModel):
    record_id: str
    task_id: str
    agent: str
    execution_time_s: float
    outcome: str = Field(description="success | failure")
    review_score: Optional[float] = None
    tests_passed: Optional[bool] = None
    architecture_compliance: float = 1.0
    human_feedback: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)

    model_config = {"from_attributes": True}
