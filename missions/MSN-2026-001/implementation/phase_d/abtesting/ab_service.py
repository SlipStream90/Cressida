import json
import os
import random
import uuid
from datetime import datetime
from typing import Optional

from app.models.feedback import FeedbackEvent

import redis as redis_lib


def _get_redis() -> redis_lib.Redis:
    return redis_lib.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))


class ABTestConfig:
    def __init__(
        self,
        test_id: str,
        name: str,
        styles_under_test: list[str],
        assignment_strategy: str,
        active: bool = True,
        created_at: Optional[str] = None,
    ):
        self.test_id = test_id
        self.name = name
        self.styles_under_test = styles_under_test
        self.assignment_strategy = assignment_strategy
        self.active = active
        self.created_at = created_at or datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "name": self.name,
            "styles_under_test": self.styles_under_test,
            "assignment_strategy": self.assignment_strategy,
            "active": self.active,
            "created_at": self.created_at,
        }


class ABTestResult:
    def __init__(
        self,
        test_id: str,
        user_id: str,
        session_id: str,
        segment_id: str,
        assigned_style: str,
        variant_id: str,
        explicit_rating: Optional[float] = None,
        implicit_signals: Optional[list[str]] = None,
        completion: bool = False,
        engagement_score: float = 0.0,
        recorded_at: Optional[str] = None,
    ):
        self.test_id = test_id
        self.user_id = user_id
        self.session_id = session_id
        self.segment_id = segment_id
        self.assigned_style = assigned_style
        self.variant_id = variant_id
        self.explicit_rating = explicit_rating
        self.implicit_signals = implicit_signals or []
        self.completion = completion
        self.engagement_score = engagement_score
        self.recorded_at = recorded_at or datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "segment_id": self.segment_id,
            "assigned_style": self.assigned_style,
            "variant_id": self.variant_id,
            "explicit_rating": self.explicit_rating,
            "implicit_signals": self.implicit_signals,
            "completion": self.completion,
            "engagement_score": self.engagement_score,
            "recorded_at": self.recorded_at,
        }


_stores: dict[str, list] = {}


def get_ab_assignment(
    test_id: str,
    user_id: str,
    available_styles: list[str],
    assignment_strategy: str = "round_robin",
    style_scores: Optional[dict[str, float]] = None,
) -> str:
    r = _get_redis()

    if assignment_strategy == "round_robin":
        key = f"abtest:{test_id}:user:{user_id}:index"
        idx = int(r.get(key) or 0)
        assigned = available_styles[idx % len(available_styles)]
        r.setex(key, 86400, str(idx + 1))
        return assigned

    if assignment_strategy == "weighted" and style_scores:
        weights = []
        for s in available_styles:
            w = style_scores.get(s, 0.2)
            w = max(w, 0.1)
            weights.append(w)
        total = sum(weights)
        weights = [w / total for w in weights]
        return random.choices(available_styles, weights=weights, k=1)[0]

    return random.choice(available_styles)


def record_ab_result(
    test_id: str,
    user_id: str,
    session_id: str,
    segment_id: str,
    assigned_style: str,
    variant_id: str,
) -> ABTestResult:
    result = ABTestResult(
        test_id=test_id,
        user_id=user_id,
        session_id=session_id,
        segment_id=segment_id,
        assigned_style=assigned_style,
        variant_id=variant_id,
    )
    _stores.setdefault("ab_results", []).append(result)
    return result


def update_ab_result_with_feedback(
    test_id: str,
    session_id: str,
    variant_id: str,
    feedback_event: FeedbackEvent,
) -> None:
    results = _stores.get("ab_results", [])
    for result in results:
        if (
            result.test_id == test_id
            and result.session_id == session_id
            and result.variant_id == variant_id
        ):
            score = 0.0
            if feedback_event.event_type == "explicit_rating" and feedback_event.rating:
                result.explicit_rating = float(feedback_event.rating)
                score += 0.6 * (feedback_event.rating / 5.0)
            if feedback_event.signal_type == "completion":
                result.completion = True
                score += 0.3
            if feedback_event.signal_type == "replay":
                result.implicit_signals.append("replay")
                score += 0.1
            if feedback_event.signal_type == "skip":
                result.implicit_signals.append("skip")
                score -= 0.2
            if feedback_event.signal_type == "pause":
                result.implicit_signals.append("pause")
                if feedback_event.signal_value and feedback_event.signal_value > 30:
                    score -= 0.1
            result.engagement_score = max(0.0, min(1.0, score))
            break


def get_ab_results_summary(test_id: str) -> dict:
    results = _stores.get("ab_results", [])
    filtered = [r for r in results if r.test_id == test_id]
    by_style: dict[str, list[ABTestResult]] = {}
    for r in filtered:
        by_style.setdefault(r.assigned_style, []).append(r)

    summary = {}
    for style, items in by_style.items():
        ratings = [i.explicit_rating for i in items if i.explicit_rating is not None]
        completions = sum(1 for i in items if i.completion)
        summary[style] = {
            "sample_count": len(items),
            "avg_engagement_score": sum(i.engagement_score for i in items) / len(items) if items else 0.0,
            "completion_rate": completions / len(items) if items else 0.0,
            "avg_explicit_rating": sum(ratings) / len(ratings) if ratings else None,
        }
    return summary
