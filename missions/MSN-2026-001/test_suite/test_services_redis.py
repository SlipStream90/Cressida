import pytest
from unittest.mock import patch, MagicMock


class TestRedisModule:
    def test_module_imports(self):
        from app.services.cache_service import get_redis, cache_profile, get_cached_profile
        from app.services.cache_service import cache_variant, get_cached_variant
        from app.services.cache_service import cache_audio, get_cached_audio
        from app.services.cache_service import RedisKeys, TTL
        assert callable(get_redis)
        assert callable(cache_profile)
        assert callable(get_cached_profile)
        assert callable(cache_variant)
        assert callable(get_cached_variant)
        assert callable(cache_audio)
        assert callable(get_cached_audio)
        assert RedisKeys.SESSION is not None
        assert len(TTL) > 0

    @patch("app.services.cache_service.get_redis")
    def test_cache_profile_roundtrip(self, mock_get_redis):
        from app.services.cache_service import cache_profile, get_cached_profile

        mock_redis = MagicMock()
        mock_redis.get.return_value = '{"name": "Test"}'
        mock_get_redis.return_value = mock_redis

        profile = {"name": "Test"}
        cache_profile("user_1", profile)
        result = get_cached_profile("user_1")

        assert result == {"name": "Test"}

    @patch("app.services.cache_service.get_redis")
    def test_cache_profile_miss(self, mock_get_redis):
        from app.services.cache_service import get_cached_profile

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        result = get_cached_profile("nonexistent")
        assert result is None

    @patch("app.services.cache_service.get_redis")
    def test_cache_variant_roundtrip(self, mock_get_redis):
        from app.services.cache_service import cache_variant, get_cached_variant

        mock_redis = MagicMock()
        mock_redis.get.return_value = '{"style": "suspense"}'
        mock_get_redis.return_value = mock_redis

        cache_variant("seg_1", "suspense", {"style": "suspense"})
        result = get_cached_variant("seg_1", "suspense")

        assert result == {"style": "suspense"}

    @patch("app.services.cache_service.get_redis")
    def test_cache_variant_miss(self, mock_get_redis):
        from app.services.cache_service import get_cached_variant

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        result = get_cached_variant("seg_miss", "suspense")
        assert result is None

    @patch("app.services.cache_service.get_redis")
    def test_cache_audio_roundtrip(self, mock_get_redis):
        from app.services.cache_service import cache_audio, get_cached_audio

        mock_redis = MagicMock()
        mock_redis.get.return_value = b"\x00\x01\x02"
        mock_get_redis.return_value = mock_redis

        audio = b"\x00\x01\x02"
        cache_audio("Hello", "Rachel", audio)
        result = get_cached_audio("Hello", "Rachel")

        assert result == b"\x00\x01\x02"

    @patch("app.services.cache_service.get_redis")
    def test_cache_audio_miss(self, mock_get_redis):
        from app.services.cache_service import get_cached_audio

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        result = get_cached_audio("Missing", "Voice")
        assert result is None
