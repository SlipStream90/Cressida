from pydantic import BaseModel, Field


class StorySegment(BaseModel):
    segment_id: str
    story_id: str
    segment_index: int
    text: str = Field(description="150-300 words")
    word_count: int
    features: dict[str, float] = Field(default_factory=dict, description="pacing, suspense, dialogue_density, emotional_tone, description_length")

    model_config = {"from_attributes": True}
