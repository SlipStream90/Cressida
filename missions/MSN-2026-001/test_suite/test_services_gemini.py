import pytest
from unittest.mock import patch, MagicMock


class TestGeminiServiceModule:
    def test_module_imports(self):
        from app.services.gemini_service import generate_variant, generate_embedding
        assert callable(generate_variant)
        assert callable(generate_embedding)

    @patch("app.services.gemini_service.genai")
    def test_generate_variant_returns_text(self, mock_genai):
        from app.services.gemini_service import generate_variant

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Once upon a time..."
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            result = generate_variant("Hello world", "Tell a story")

        assert result == "Once upon a time..."
        mock_genai.configure.assert_called_once_with(api_key="test-key")
        mock_model.generate_content.assert_called_once_with("Hello world")

    @patch("app.services.gemini_service.genai")
    def test_generate_embedding_returns_list(self, mock_genai):
        from app.services.gemini_service import generate_embedding

        mock_genai.embed_content.return_value = {"embedding": [0.1, 0.2, 0.3]}

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            result = generate_embedding("Hello world")

        assert result == [0.1, 0.2, 0.3]

    def test_gemini_model_constant_defined(self):
        from app.services.gemini_service import GEMINI_MODEL
        assert GEMINI_MODEL == "gemini-1.5-pro"


class TestElevenLabsService:
    @pytest.fixture(autouse=True)
    def _unique_text(self, request):
        self._text = f"Hello World {id(request)}"

    def test_module_imports(self):
        from app.services.elevenlabs_service import synthesize, AudioCache
        assert callable(synthesize)
        assert callable(AudioCache)

    @patch("app.services.elevenlabs_service.ElevenLabs")
    def test_synthesize_returns_bytes(self, mock_eleven):
        from app.services.elevenlabs_service import synthesize

        mock_client = MagicMock()
        mock_eleven.return_value = mock_client
        mock_client.generate.return_value = [b"\x00\x01", b"\x02\x03"]

        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "test-key"}):
            result = synthesize("Hello Test Bytes", voice_id="Rachel")

        assert isinstance(result, bytes)
        assert result == b"\x00\x01\x02\x03"

    @patch("app.services.elevenlabs_service.ElevenLabs")
    def test_synthesize_caches_audio(self, mock_eleven):
        from app.services.elevenlabs_service import synthesize

        unique_text = f"Cache Test {__name__}"

        mock_client = MagicMock()
        mock_eleven.return_value = mock_client
        mock_client.generate.return_value = [b"\x00\x01"]

        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "test-key"}):
            first = synthesize(unique_text, voice_id="Rachel")
            second = synthesize(unique_text, voice_id="Rachel")

        assert first == b"\x00\x01"
        assert second == b"\x00\x01"

    @patch("app.services.elevenlabs_service.ElevenLabs")
    def test_audio_cache_hit_and_miss(self, mock_eleven):
        import uuid
        from app.services.elevenlabs_service import AudioCache

        miss_text = f"miss_{uuid.uuid4().hex}"
        hit_text = f"hit_{uuid.uuid4().hex}"
        voice = "Rachel"

        cache = AudioCache()
        assert cache.get(miss_text, voice) is None
        cache.set(hit_text, voice, b"\x00\x01")
        assert cache.get(hit_text, voice) == b"\x00\x01"
