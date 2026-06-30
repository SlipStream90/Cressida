import hashlib
import os
import time
from pathlib import Path

from openai import OpenAI

AUDIO_CACHE_DIR = Path(os.environ.get("AUDIO_CACHE_DIR", "echo/audio_cache"))
NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
MAGPIE_TTS_MODEL = "magpie-tts-zeroshot"
MAGPIE_TTS_VOICE = "default"

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=os.environ.get("NIM_BASE_URL", NIM_BASE_URL),
            api_key=os.environ["NIM_API_KEY"],
        )
    return _client


class AudioCache:
    def __init__(self):
        AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, text: str, voice_id: str) -> Path:
        hash_key = hashlib.md5(f"{text}{voice_id}".encode()).hexdigest()
        return AUDIO_CACHE_DIR / f"{hash_key}.mp3"

    def get(self, text: str, voice_id: str) -> bytes | None:
        path = self._cache_path(text, voice_id)
        if path.exists():
            return path.read_bytes()
        return None

    def set(self, text: str, voice_id: str, audio: bytes) -> None:
        self._cache_path(text, voice_id).write_bytes(audio)


def synthesize(text: str, voice_id: str = None) -> bytes:
    if voice_id is None:
        voice_id = os.environ.get("MAGPIE_TTS_VOICE", MAGPIE_TTS_VOICE)
    cache = AudioCache()
    cached = cache.get(text, voice_id)
    if cached:
        return cached

    model = os.environ.get("MAGPIE_TTS_MODEL", MAGPIE_TTS_MODEL)
    last_error = None
    for attempt in range(3):
        try:
            client = _get_client()
            response = client.audio.speech.create(
                model=model,
                input=text,
                voice=voice_id,
                response_format="mp3",
            )
            audio_bytes = response.read()
            cache.set(text, voice_id, audio_bytes)
            return audio_bytes
        except Exception as e:
            last_error = e
            wait = 2 ** attempt
            print(f"Magpie TTS API error (attempt {attempt + 1}/3): {e}, retrying in {wait}s")
            time.sleep(wait)

    raise RuntimeError(f"Magpie TTS synthesis failed after 3 retries: {last_error}")
