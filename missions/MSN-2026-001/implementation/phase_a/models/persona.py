from pydantic import BaseModel, Field


class StylePreset(BaseModel):
    style_id: str
    name: str
    description: str
    system_prompt: str
    embedding: list[float] = Field(default_factory=list, description="768-dim style embedding from Gemini")
