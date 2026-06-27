from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class FeedbackEvent(BaseModel):
    event_id: str
    user_id: str
    session_id: str
    segment_id: str
    variant_id: str
    event_type: str = Field(description="explicit_rating | implicit_signal")
    rating: Optional[int] = Field(default=None, ge=1, le=5, description="1-5 for explicit")
    signal_type: Optional[str] = Field(default=None, description="replay | skip | pause | completion")
    signal_value: Optional[float] = Field(default=None, description="pause duration, completion %, etc.")
    timestamp: datetime = Field(default_factory=datetime.now)
    client_ts: datetime = Field(default_factory=datetime.now, description="Client-side timestamp")

    model_config = {"from_attributes": True}
