from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "ECHO"
    app_version: str = "0.2.0"
    debug: bool = False
    cors_origins: list[str] = ["*"]
    api_prefix: str = "/v1"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-pro"
    elevenlabs_api_key: str = ""
    elevenlabs_default_voice: str = "Rachel"
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_key: str = ""
    redis_url: str = ""
    faiss_index_dir: str = "echo/faiss_index"
    audio_cache_dir: str = "echo/audio_cache"

    @property
    def style_presets_path(self) -> Path:
        return Path(__file__).parent.parent / "config" / "style_presets.yaml"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
