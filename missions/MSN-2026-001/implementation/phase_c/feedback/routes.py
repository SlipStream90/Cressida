import uuid
from datetime import datetime

from fastapi import APIRouter, Depends

from app.api.deps import verify_api_key
from app.models.feedback import FeedbackEvent
from app.models.reward import RewardModelInput, RewardModelOutput
from app.services.reward_service import update_style_scores, resolve_signals
from app.core.config import settings

router = APIRouter(prefix=f"{settings.api_prefix}/feedback", tags=["feedback"])


@router.post("/explicit")
async def submit_explicit_feedback(
    user_id: str,
    session_id: str,
    segment_id: str,
    variant_id: str,
    rating: int,
    api_key: str = Depends(verify_api_key),
):
    event = FeedbackEvent(
        event_id=str(uuid.uuid4()),
        user_id=user_id,
        session_id=session_id,
        segment_id=segment_id,
        variant_id=variant_id,
        event_type="explicit_rating",
        rating=rating,
    )
    signals = resolve_signals("explicit_rating", rating=rating)
    _store_feedback(event)
    return {"event_id": event.event_id, "status": "recorded"}


@router.post("/implicit")
async def submit_implicit_feedback(
    user_id: str,
    session_id: str,
    segment_id: str,
    variant_id: str,
    signal_type: str,
    signal_value: float = 0.0,
    api_key: str = Depends(verify_api_key),
):
    event = FeedbackEvent(
        event_id=str(uuid.uuid4()),
        user_id=user_id,
        session_id=session_id,
        segment_id=segment_id,
        variant_id=variant_id,
        event_type="implicit_signal",
        signal_type=signal_type,
        signal_value=signal_value,
    )
    _store_feedback(event)
    return {"event_id": event.event_id, "status": "recorded"}


def _store_feedback(event: FeedbackEvent) -> None:
    print(f"FEEDBACK: {event.event_id} | {event.event_type} | user={event.user_id}")
