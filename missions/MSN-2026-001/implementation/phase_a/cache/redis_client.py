import hashlib
import json
import os
from typing import Optional

import redis as redis_lib


class RedisKeys:
    SESSION = "session:{session_id}"
    PROFILE_CACHE = "profile:{user_id}:cache"
    VARIANT = "variant:{segment_id}:{style}"
    AUDIO = "audio:{text_hash}:{voice}"
    CHECKPOINT = "checkpoint:{thread_id}"
    SESSION_STYLE = "session:{session_id}:style_state"
    ABTEST_INDEX = "abtest:{test_id}:user:{user_id}:index"


TTL = {
    "session": 3600,
    "profile_cache": 300,
    "variant": 600,
    "audio": 86400,
    "checkpoint": 86400,
    "session_style": 3600,
    "abtest_index": 86400,
}


def get_redis() -> redis_lib.Redis:
    return redis_lib.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))


def cache_profile(user_id: str, profile: dict) -> None:
    r = get_redis()
    key = RedisKeys.PROFILE_CACHE.format(user_id=user_id)
    r.setex(key, TTL["profile_cache"], json.dumps(profile))


def get_cached_profile(user_id: str) -> Optional[dict]:
    r = get_redis()
    key = RedisKeys.PROFILE_CACHE.format(user_id=user_id)
    raw = r.get(key)
    return json.loads(raw) if raw else None


def cache_variant(segment_id: str, style: str, variant: dict) -> None:
    r = get_redis()
    key = RedisKeys.VARIANT.format(segment_id=segment_id, style=style)
    r.setex(key, TTL["variant"], json.dumps(variant))


def get_cached_variant(segment_id: str, style: str) -> Optional[dict]:
    r = get_redis()
    key = RedisKeys.VARIANT.format(segment_id=segment_id, style=style)
    raw = r.get(key)
    return json.loads(raw) if raw else None


def cache_audio(text: str, voice: str, audio_bytes: bytes) -> None:
    r = get_redis()
    text_hash = hashlib.md5(text.encode()).hexdigest()
    key = RedisKeys.AUDIO.format(text_hash=text_hash, voice=voice)
    r.setex(key, TTL["audio"], audio_bytes)


def get_cached_audio(text: str, voice: str) -> Optional[bytes]:
    r = get_redis()
    text_hash = hashlib.md5(text.encode()).hexdigest()
    key = RedisKeys.AUDIO.format(text_hash=text_hash, voice=voice)
    raw = r.get(key)
    return raw if raw else None
