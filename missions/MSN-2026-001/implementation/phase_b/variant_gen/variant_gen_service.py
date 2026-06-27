import uuid

from app.config.style_presets import load_presets
from app.models.variant import NarrationVariant
from app.services.gemini_service import generate_variant


def generate_variants_for_user(
    segment_text: str,
    segment_id: str,
    style_scores: dict[str, float],
    num_variants: int = 3,
) -> list[NarrationVariant]:
    presets = load_presets()
    sorted_styles = sorted(
        style_scores.items(), key=lambda x: x[1], reverse=True
    )
    top_styles = [s for s, _ in sorted_styles[:num_variants]]

    variants: list[NarrationVariant] = []
    for style_key in top_styles:
        if style_key not in presets:
            continue
        preset = presets[style_key]
        generated = generate_variant(segment_text, preset["system_prompt"])
        variant = NarrationVariant(
            variant_id=str(uuid.uuid4()),
            segment_id=segment_id,
            style=style_key,
            style_prompt_key=f"STYLE_{style_key.upper()}",
            generated_text=generated,
            model_version="gemini-1.5-pro",
        )
        variants.append(variant)

    return variants
