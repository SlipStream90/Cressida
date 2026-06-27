SCORING_WEIGHTS = {
    "explicit_positive": 0.15,
    "explicit_negative": -0.10,
    "replay": 0.08,
    "skip": -0.06,
    "completion": 0.05,
    "pause_long": -0.03,
}

SIGNAL_MAP = {
    "rating_4": "explicit_positive",
    "rating_5": "explicit_positive",
    "rating_1": "explicit_negative",
    "rating_2": "explicit_negative",
    "replay": "replay",
    "skip": "skip",
    "completion": "completion",
    "pause_long": "pause_long",
}


def resolve_signals(event_type: str, rating: int | None = None, signal_type: str | None = None) -> list[str]:
    signals = []
    if event_type == "explicit_rating" and rating is not None:
        key = f"rating_{rating}"
        if key in SIGNAL_MAP:
            signals.append(SIGNAL_MAP[key])
    elif event_type == "implicit_signal" and signal_type:
        if signal_type in SIGNAL_MAP:
            signals.append(SIGNAL_MAP[signal_type])
        if signal_type == "pause":
            signals.append("pause_long")
    return signals


def update_style_scores(
    current: dict[str, float],
    selected_style: str,
    signals: list[str],
) -> dict[str, float]:
    updated = dict(current) if current else {
        "suspense": 0.2,
        "dialogue": 0.2,
        "emotional": 0.2,
        "fast_paced": 0.2,
        "descriptive": 0.2,
    }
    delta = sum(SCORING_WEIGHTS.get(s, 0.0) for s in signals)
    updated[selected_style] = max(0.0, updated.get(selected_style, 0.2) + delta)
    total = sum(updated.values())
    if total > 0:
        for k in updated:
            updated[k] /= total
    return updated
