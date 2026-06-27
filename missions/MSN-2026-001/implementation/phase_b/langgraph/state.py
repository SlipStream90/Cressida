from typing import TypedDict, Optional


class WorkflowState(TypedDict):
    segment_id: str
    segment_text: str
    user_id: str
    session_id: str
    style_scores: dict[str, float]
    variants: list[dict]
    selected_variant: Optional[dict]
    audio_url: Optional[str]
    feedback_collected: bool
    preference_updated: bool
