import json
import os
from datetime import datetime
from typing import Optional

from app.models.feedback import FeedbackEvent
from app.services.reward_service import update_style_scores, resolve_signals, SCORING_WEIGHTS

import redis as redis_lib

SESSION_TTL = 3600


def _get_redis() -> redis_lib.Redis:
    return redis_lib.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))


class SessionStyleState:
    def __init__(
        self,
        user_id: str,
        session_id: str,
        initial_style: str,
        current_style: str,
        within_session_scores: dict[str, float],
        signals_received: int = 0,
        last_updated: Optional[str] = None,
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.initial_style = initial_style
        self.current_style = current_style
        self.within_session_scores = within_session_scores
        self.signals_received = signals_received
        self.last_updated = last_updated or datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "initial_style": self.initial_style,
            "current_style": self.current_style,
            "within_session_scores": self.within_session_scores,
            "signals_received": self.signals_received,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionStyleState":
        return cls(**data)


def initialize_session_style(
    user_id: str,
    session_id: str,
    base_style_scores: dict[str, float],
) -> SessionStyleState:
    if not base_style_scores:
        base_style_scores = {k: 0.2 for k in ["suspense", "dialogue", "emotional", "fast_paced", "descriptive"]}
    initial = max(base_style_scores, key=base_style_scores.get)
    state = SessionStyleState(
        user_id=user_id,
        session_id=session_id,
        initial_style=initial,
        current_style=initial,
        within_session_scores=dict(base_style_scores),
    )
    r = _get_redis()
    r.setex(f"session:{session_id}:style_state", SESSION_TTL, json.dumps(state.to_dict()))
    return state


def update_session_style(
    session_id: str,
    feedback_event: FeedbackEvent,
) -> Optional[SessionStyleState]:
    r = _get_redis()
    raw = r.get(f"session:{session_id}:style_state")
    if not raw:
        return None

    state = SessionStyleState.from_dict(json.loads(raw))
    selected_style = state.current_style

    if feedback_event.event_type == "implicit_signal":
        signals = resolve_signals("implicit_signal", signal_type=feedback_event.signal_type)
    elif feedback_event.event_type == "explicit_rating":
        signals = resolve_signals("explicit_rating", rating=feedback_event.rating)
    else:
        signals = []

    state.within_session_scores = update_style_scores(
        state.within_session_scores, selected_style, signals
    )
    state.current_style = max(state.within_session_scores, key=state.within_session_scores.get)
    state.signals_received += len(signals)
    state.last_updated = datetime.now().isoformat()

    r.setex(f"session:{session_id}:style_state", SESSION_TTL, json.dumps(state.to_dict()))
    return state


def get_current_style(session_id: str) -> Optional[str]:
    r = _get_redis()
    raw = r.get(f"session:{session_id}:style_state")
    if not raw:
        return None
    state = SessionStyleState.from_dict(json.loads(raw))
    return state.current_style
