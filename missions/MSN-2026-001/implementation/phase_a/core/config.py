from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "ECHO"
    app_version: str = "0.2.0"
    debug: bool = False
    cors_origins: list[str] = ["*"]
    api_prefix: str = "/v1"
    nim_api_key: str = ""
    nim_model: str = "meta/llama-3.3-70b-instruct"
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nim_embedding_model: str = "nvidia/nv-embedqa-e5-v5"
    magpie_tts_model: str = "magpie-tts-zeroshot"
    magpie_tts_voice: str = "default"
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
