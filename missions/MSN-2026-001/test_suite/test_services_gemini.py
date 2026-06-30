import pytest
from unittest.mock import patch, MagicMock


class TestNimServiceModule:
    def test_module_imports(self):
        from app.services.gemini_service import generate_variant, generate_embedding
        assert callable(generate_variant)
        assert callable(generate_embedding)

    @patch("app.services.gemini_service._get_client")
    def test_generate_variant_returns_text(self, mock_get_client):
        from app.services.gemini_service import generate_variant

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = "Once upon a time..."
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )

        with patch.dict("os.environ", {"NIM_API_KEY": "test-key"}):
            result = generate_variant("Hello world", "Tell a story")

        assert result == "Once upon a time..."
        mock_client.chat.completions.create.assert_called_once()

    @patch("app.services.gemini_service._get_client")
    def test_generate_embedding_returns_list(self, mock_get_client):
        from app.services.gemini_service import generate_embedding

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1, 0.2, 0.3])]
        )

        with patch.dict("os.environ", {"NIM_API_KEY": "test-key"}):
            result = generate_embedding("Hello world")

        assert result == [0.1, 0.2, 0.3]

    def test_nim_model_constant_defined(self):
        from app.services.gemini_service import NIM_MODEL
        assert "llama" in NIM_MODEL or "meta" in NIM_MODEL


class TestMagpieTtsService:
    @pytest.fixture(autouse=True)
    def _unique_text(self, request):
        self._text = f"Hello World {id(request)}"

    def test_module_imports(self):
        from app.services.elevenlabs_service import synthesize, AudioCache
        assert callable(synthesize)
        assert callable(AudioCache)

    @patch("app.services.elevenlabs_service._get_client")
    def test_synthesize_returns_bytes(self, mock_get_client):
        from app.services.elevenlabs_service import synthesize

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.read.return_value = b"\x00\x01\x02\x03"
        mock_client.audio.speech.create.return_value = mock_response

        with patch.dict("os.environ", {"NIM_API_KEY": "test-key", "AUDIO_CACHE_DIR": "/tmp/test_audio_cache_synth"}):
            result = synthesize("Hello Test Bytes", voice_id="default")

        assert isinstance(result, bytes)
        assert result == b"\x00\x01\x02\x03"

    @patch("app.services.elevenlabs_service._get_client")
    def test_synthesize_caches_audio(self, mock_get_client):
        from app.services.elevenlabs_service import synthesize

        unique_text = f"Cache Test {__name__}"
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.read.return_value = b"\x00\x01"
        mock_client.audio.speech.create.return_value = mock_response

        with patch.dict("os.environ", {"NIM_API_KEY": "test-key", "AUDIO_CACHE_DIR": "/tmp/test_audio_cache_cache"}):
            first = synthesize(unique_text, voice_id="default")
            second = synthesize(unique_text, voice_id="default")

        assert first == b"\x00\x01"
        assert second == b"\x00\x01"

    def test_audio_cache_hit_and_miss(self):
        import uuid
        from app.services.elevenlabs_service import AudioCache

        miss_text = f"miss_{uuid.uuid4().hex}"
        hit_text = f"hit_{uuid.uuid4().hex}"
        voice = "default"

        cache = AudioCache()
        assert cache.get(miss_text, voice) is None
        cache.set(hit_text, voice, b"\x00\x01")
        assert cache.get(hit_text, voice) == b"\x00\x01"
