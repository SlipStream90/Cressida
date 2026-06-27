import hashlib
import os
from pathlib import Path

from elevenlabs.client import ElevenLabs

AUDIO_CACHE_DIR = Path("echo/audio_cache")


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


def synthesize(text: str, voice_id: str = "Rachel") -> bytes:
    cache = AudioCache()
    cached = cache.get(text, voice_id)
    if cached:
        return cached
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    audio = client.generate(text=text, voice=voice_id)
    audio_bytes = b"".join(audio)
    cache.set(text, voice_id, audio_bytes)
    return audio_bytes
