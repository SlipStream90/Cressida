from typing import Optional
from pydantic import BaseModel, Field


class NarrationVariant(BaseModel):
    variant_id: str
    segment_id: str
    style: str = Field(description="suspense | dialogue | emotional | fast_paced | descriptive")
    style_prompt_key: str = ""
    generated_text: str
    audio_url: Optional[str] = None
    generation_latency_ms: float = 0.0
    model_version: str = "gemini-1.5-pro"

    model_config = {"from_attributes": True}
