import os
import uuid
from datetime import datetime

from app.models.story import StorySegment
from app.models.variant import NarrationVariant
from app.services.gemini_service import generate_embedding, generate_variant
from app.services.elevenlabs_service import synthesize
from app.services.reward_service import update_style_scores, resolve_signals
from app.services.vector_service import VectorService
from app.config.style_presets import load_presets

from .state import WorkflowState

vector_service = VectorService()


async def load_context(state: WorkflowState) -> WorkflowState:
    segment = _fetch_segment(state["segment_id"])
    return {
        **state,
        "segment_text": segment.text,
    }


async def retrieve_preference(state: WorkflowState) -> WorkflowState:
    user_id = state["user_id"]
    if vector_service.index_exists(user_id):
        embedding = generate_embedding(state["segment_text"])
        similar = vector_service.search_similar(user_id, embedding, top_k=3)
    return {
        **state,
        "style_scores": state.get("style_scores", {}),
    }


async def generate_variants(state: WorkflowState) -> WorkflowState:
    presets = load_presets()
    sorted_styles = sorted(
        state["style_scores"].items(), key=lambda x: x[1], reverse=True
    )
    top_styles = [s for s, _ in sorted_styles[:3]]

    variants: list[dict] = []
    for style_key in top_styles:
        if style_key not in presets:
            continue
        preset = presets[style_key]
        generated = generate_variant(state["segment_text"], preset["system_prompt"])
        variant = NarrationVariant(
            variant_id=str(uuid.uuid4()),
            segment_id=state["segment_id"],
            style=style_key,
            style_prompt_key=f"STYLE_{style_key.upper()}",
            generated_text=generated,
            model_version="meta/llama-3.3-70b-instruct",
        )
        variants.append(variant.model_dump())
    return {**state, "variants": variants}


async def select_best(state: WorkflowState) -> WorkflowState:
    variants = state.get("variants", [])
    if not variants:
        return {**state, "selected_variant": None}

    scores = state.get("style_scores", {})
    best = max(variants, key=lambda v: scores.get(v["style"], 0.2))
    return {**state, "selected_variant": best}


async def synthesize_audio(state: WorkflowState) -> WorkflowState:
    selected = state.get("selected_variant")
    if not selected:
        return state
    audio_bytes = synthesize(selected["generated_text"])
    audio_url = f"/audio/{uuid.uuid4()}.mp3"
    _save_audio(audio_url, audio_bytes)
    return {**state, "audio_url": audio_url}


async def collect_feedback(state: WorkflowState) -> WorkflowState:
    return {**state, "feedback_collected": True}


async def update_preference(state: WorkflowState) -> WorkflowState:
    selected = state.get("selected_variant")
    if not selected:
        return {**state, "preference_updated": True}
    signals = ["completion"]
    updated = update_style_scores(state.get("style_scores", {}), selected["style"], signals)
    return {**state, "style_scores": updated, "preference_updated": True}


async def complete(state: WorkflowState) -> WorkflowState:
    return state


def _fetch_segment(segment_id: str) -> StorySegment:
    return StorySegment(
        segment_id=segment_id,
        story_id="",
        segment_index=0,
        text="",
        word_count=0,
    )


def _save_audio(url: str, data: bytes) -> None:
    import hashlib
    from pathlib import Path
    cache_dir = Path("echo/audio_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.md5(url.encode()).hexdigest()
    (cache_dir / f"{h}.mp3").write_bytes(data)
