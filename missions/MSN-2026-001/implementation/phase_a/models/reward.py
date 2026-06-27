from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RewardModelInput(BaseModel):
    user_id: str
    session_id: str
    style_selected: str = Field(description="suspense | dialogue | emotional | fast_paced | descriptive")
    feedback_type: str = Field(description="explicit_rating | implicit_signal")
    feedback_value: Optional[int | float] = Field(default=None, description="rating (1-5) or signal magnitude")
    timestamp: datetime = Field(default_factory=datetime.now)


class RewardModelOutput(BaseModel):
    user_id: str
    updated_style_scores: dict[str, float]
    recommended_style: str
    confidence: float
    model_version: str = "weighted-scoring-v1"
