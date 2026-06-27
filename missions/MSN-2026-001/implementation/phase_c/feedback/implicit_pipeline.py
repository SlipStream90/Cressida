from app.models.feedback import FeedbackEvent
from app.services.reward_service import update_style_scores, resolve_signals


def process_implicit_signal(
    event: FeedbackEvent,
    current_style_scores: dict[str, float],
    selected_style: str,
) -> dict[str, float]:
    signals = resolve_signals(
        event_type="implicit_signal",
        signal_type=event.signal_type,
    )
    if event.signal_type == "pause" and event.signal_value and event.signal_value > 30:
        signals.append("pause_long")

    updated = update_style_scores(current_style_scores, selected_style, signals)
    return updated


def disambiguate_signal(
    signal_type: str,
    signal_value: float,
    segment_duration_s: float,
) -> tuple[str, float]:
    mapping = {
        "replay": ("replay", 1.0),
        "skip": ("skip", 1.0),
        "completion": ("completion", signal_value / 100.0 if signal_value > 1 else signal_value),
    }
    if signal_type in mapping:
        return mapping[signal_type]

    if signal_type == "pause":
        if signal_value > 30:
            return ("pause_long", min(signal_value / 60.0, 5.0))
        return ("pause", 0.0)

    return ("unknown", 0.0)
