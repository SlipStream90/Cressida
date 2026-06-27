from app.models.variant import NarrationVariant


def select_best_variant(
    variants: list[NarrationVariant],
    style_scores: dict[str, float],
) -> tuple[NarrationVariant | None, float]:
    if not variants:
        return None, 0.0

    best = max(
        variants,
        key=lambda v: style_scores.get(v.style, 0.2),
    )
    confidence = style_scores.get(best.style, 0.2)
    return best, confidence


def select_by_highest_score(
    variants: list[dict],
    style_scores: dict[str, float],
) -> tuple[dict | None, float]:
    if not variants:
        return None, 0.0

    best = max(
        variants,
        key=lambda v: style_scores.get(v.get("style", ""), 0.2),
    )
    confidence = style_scores.get(best.get("style", ""), 0.2)
    return best, confidence
