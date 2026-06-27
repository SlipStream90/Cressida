from datetime import datetime
from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    user_id: str
    embedding: list[float] = Field(default_factory=list, description="768-dim from Gemini Embedding API")
    style_scores: dict[str, float] = Field(default_factory=dict, description="Current preference per style")
    preferred_voice: str = "Rachel"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    session_count: int = 0
    total_feedback_count: int = 0

    model_config = {"from_attributes": True}
