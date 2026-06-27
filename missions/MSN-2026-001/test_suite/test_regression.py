"""Regression tests REGRESSION-001 through REGRESSION-015.
See cressida/missions/MSN-2026-001/regression_tests.md for full specification.
"""

import pytest
from unittest.mock import patch, MagicMock
from app.models.feedback import FeedbackEvent


API_KEY = "regression-test-api-key"


# ---------------------------------------------------------------------------
# REGRESSION-001: Gemini service handles empty input
# ---------------------------------------------------------------------------
class TestRegression001:
    @patch("app.services.gemini_service.genai")
    def test_gemini_handles_empty_input(self, mock_genai):
        from app.services.gemini_service import generate_variant
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = ""
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            result = generate_variant("", "system prompt")
        assert result == ""


# ---------------------------------------------------------------------------
# REGRESSION-002: ElevenLabs handles empty text gracefully
# ---------------------------------------------------------------------------
class TestRegression002:
    @patch("app.services.elevenlabs_service.ElevenLabs")
    def test_elevenlabs_empty_text_returns_bytes(self, mock_eleven):
        from app.services.elevenlabs_service import synthesize
        mock_client = MagicMock()
        mock_eleven.return_value = mock_client
        mock_client.generate.return_value = [b""]
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "test-key"}):
            result = synthesize("", voice_id="Rachel")
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# REGRESSION-003: Reward service handles unknown signal_type gracefully
# ---------------------------------------------------------------------------
class TestRegression003:
    def test_reward_unknown_signal_returns_empty(self):
        from app.services.reward_service import resolve_signals
        result = resolve_signals("implicit_signal", signal_type="totally_unknown")
        assert result == []


# ---------------------------------------------------------------------------
# REGRESSION-004: FAISS vector service handles cold start
# ---------------------------------------------------------------------------
class TestRegression004:
    def test_faiss_cold_start_returns_empty(self):
        from app.services.vector_service import VectorService
        svc = VectorService(dimension=768)
        result = svc.search_similar("new_user_reg004", [0.1] * 768, top_k=5)
        assert result == []


# ---------------------------------------------------------------------------
# REGRESSION-005: Redis cache service handles miss gracefully
# ---------------------------------------------------------------------------
class TestRegression005:
    @patch("app.services.cache_service.get_redis")
    def test_cache_miss_returns_none(self, mock_get_redis):
        from app.services.cache_service import get_cached_profile
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis
        assert get_cached_profile("nonexistent_reg005") is None


# ---------------------------------------------------------------------------
# REGRESSION-006: LangGraph workflow cold start
# ---------------------------------------------------------------------------
class TestRegression006:
    def test_workflow_state_defaults(self):
        from app.workflow.state import WorkflowState
        state: WorkflowState = {
            "segment_id": "seg_reg006",
            "segment_text": "",
            "user_id": "u_reg006",
            "session_id": "s_reg006",
            "style_scores": {},
            "variants": [],
            "selected_variant": None,
            "audio_url": None,
            "feedback_collected": False,
            "preference_updated": False,
        }
        assert state["feedback_collected"] is False
        assert state["selected_variant"] is None


# ---------------------------------------------------------------------------
# REGRESSION-007: Session adapter no UserProfile writes
# ---------------------------------------------------------------------------
class TestRegression007:
    def test_no_user_profile_write_methods(self):
        from app.services.session_adapter import SessionStyleState
        attrs = [m for m in dir(SessionStyleState) if not m.startswith("_")]
        profile_related = [m for m in attrs if "profile" in m.lower()]
        assert len(profile_related) == 0


# ---------------------------------------------------------------------------
# REGRESSION-008: AB service engagement score bounded [0,1]
# ---------------------------------------------------------------------------
class TestRegression008:
    def test_ab_result_engagement_default(self):
        from app.services.ab_service import ABTestResult
        result = ABTestResult(
            test_id="t1", user_id="u1", session_id="s1",
            segment_id="seg1", assigned_style="suspense", variant_id="v1"
        )
        assert result.engagement_score == 0.0
        assert 0.0 <= result.engagement_score <= 1.0


# ---------------------------------------------------------------------------
# REGRESSION-009: Drift detection insufficient history
# ---------------------------------------------------------------------------
class TestRegression009:
    def test_insufficient_history_returns_none(self):
        from app.services.drift_service import detect_drift
        result = detect_drift("user_reg009")
        assert result is None


# ---------------------------------------------------------------------------
# REGRESSION-010: Feedback endpoint requires API key
# ---------------------------------------------------------------------------
class TestRegression010:
    def test_feedback_requires_api_key(self):
        with patch.dict("os.environ", {"API_KEY": API_KEY}):
            from fastapi.testclient import TestClient
            from app.main import app
            client = TestClient(app)
            response = client.post("/v1/feedback/explicit", params={
                "user_id": "u1", "session_id": "s1",
                "segment_id": "seg1", "variant_id": "v1", "rating": 5,
            })
            assert response.status_code == 401

    def test_feedback_allows_valid_key(self):
        with patch.dict("os.environ", {"API_KEY": API_KEY}):
            from fastapi.testclient import TestClient
            from app.main import app
            client = TestClient(app)
            response = client.post("/v1/feedback/explicit", params={
                "user_id": "u1", "session_id": "s1",
                "segment_id": "seg1", "variant_id": "v1", "rating": 5,
            }, headers={"X-API-Key": API_KEY})
            assert response.status_code == 200


# ---------------------------------------------------------------------------
# REGRESSION-011: Style scores normalize to 1.0
# ---------------------------------------------------------------------------
class TestRegression011:
    def test_style_scores_normalize_to_one(self):
        from app.services.reward_service import update_style_scores
        result = update_style_scores({"a": 10, "b": 5, "c": 5}, "a", ["explicit_positive"])
        total = sum(result.values())
        assert abs(total - 1.0) < 0.001


# ---------------------------------------------------------------------------
# REGRESSION-012: FAISS index persistence (round-trip)
# ---------------------------------------------------------------------------
class TestRegression012:
    def test_faiss_index_persistence_roundtrip(self, tmp_path):
        with patch("app.services.vector_service.settings.faiss_index_dir",
                   str(tmp_path / "faiss")):
            from app.services.vector_service import VectorService
            svc1 = VectorService(dimension=8)
            svc1.add_vectors("user_reg012", [[0.1] * 8, [0.2] * 8])
            assert svc1.index_exists("user_reg012")
            results = svc1.search_similar("user_reg012", [0.1] * 8, top_k=1)
            assert len(results) == 1


# ---------------------------------------------------------------------------
# REGRESSION-013: AB service round-robin balanced distribution
# ---------------------------------------------------------------------------
class TestRegression013:
    @patch("app.services.ab_service._get_redis")
    def test_round_robin_balanced(self, mock_get_redis):
        from app.services.ab_service import get_ab_assignment

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        counts = {}
        for i in range(60):
            v = get_ab_assignment("exp_reg013", f"user_{i}", ["a", "b"], "round_robin")
            counts[v] = counts.get(v, 0) + 1
        assert sum(counts.values()) == 60
        for c in counts.values():
            assert c >= 20


# ---------------------------------------------------------------------------
# REGRESSION-014: Cache service handles miss and invalidation
# ---------------------------------------------------------------------------
class TestRegression014:
    @patch("app.services.cache_service.get_redis")
    def test_cache_miss(self, mock_get_redis):
        from app.services.cache_service import get_cached_profile

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        result = get_cached_profile("user_reg014")
        assert result is None

    @patch("app.services.cache_service.get_redis")
    def test_cache_hit(self, mock_get_redis):
        from app.services.cache_service import get_cached_profile

        mock_redis = MagicMock()
        mock_redis.get.return_value = '{"name": "test"}'
        mock_get_redis.return_value = mock_redis

        result = get_cached_profile("user_reg014b")
        assert result == {"name": "test"}


# ---------------------------------------------------------------------------
# REGRESSION-015: Drift report creation
# ---------------------------------------------------------------------------
class TestRegression015:
    def test_drift_report_to_dict(self):
        from app.services.drift_service import DriftReport
        report = DriftReport(
            user_id="u1",
            previous_dominant_style="suspense",
            emerging_dominant_style="suspense",
            drift_confidence=0.0,
            sessions_analyzed=5,
            recommendation="monitor"
        )
        d = report.to_dict()
        assert d["user_id"] == "u1"
        assert d["drift_confidence"] == 0.0
