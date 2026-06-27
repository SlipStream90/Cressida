import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.feedback import FeedbackEvent
from app.models.reward import RewardModelInput, RewardModelOutput
from app.models.user import UserProfile
from app.models.variant import NarrationVariant
from app.models.story import StorySegment
from app.models.persona import StylePreset
from app.models.evaluation import EvaluationRecord
from app.services.reward_service import (
    resolve_signals,
    update_style_scores,
    SCORING_WEIGHTS,
    SIGNAL_MAP,
)
from app.core.config import settings


client = TestClient(app)


# ---------------------------------------------------------------------------
# Health endpoint (existing, keep passing)
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["name"] == "ECHO"
        assert data["version"] == "0.2.0"

    def test_health_check_has_uptime(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert "uptime" in response.json()


# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------

class TestUserProfileModel:
    def test_default_style_scores(self):
        user = UserProfile(user_id="u1")
        assert user.style_scores == {}

    def test_full_construction(self):
        user = UserProfile(
            user_id="u1",
            embedding=[0.1] * 768,
            style_scores={"suspense": 0.4, "dialogue": 0.3},
            preferred_voice="Rachel",
        )
        assert user.user_id == "u1"
        assert len(user.embedding) == 768
        assert user.style_scores["suspense"] == 0.4
        assert user.preferred_voice == "Rachel"

    def test_session_count_defaults(self):
        user = UserProfile(user_id="u1")
        assert user.session_count == 0
        assert user.total_feedback_count == 0


class TestNarrationVariantModel:
    def test_minimal_construction(self):
        v = NarrationVariant(
            variant_id="v1",
            segment_id="s1",
            style="suspense",
            generated_text="Once upon a time...",
        )
        assert v.variant_id == "v1"
        assert v.style == "suspense"
        assert v.audio_url is None
        assert v.model_version == "gemini-1.5-pro"

    def test_audio_url_optional(self):
        v = NarrationVariant(
            variant_id="v1",
            segment_id="s1",
            style="emotional",
            generated_text="Hello",
            audio_url="/audio/abc.mp3",
        )
        assert v.audio_url == "/audio/abc.mp3"

    def test_no_blend_weights_field(self):
        v = NarrationVariant(
            variant_id="v1",
            segment_id="s1",
            style="descriptive",
            generated_text="Text",
        )
        assert not hasattr(v, "blend_weights")


class TestFeedbackEventModel:
    def test_explicit_rating(self):
        event = FeedbackEvent(
            event_id="e1",
            user_id="u1",
            session_id="s1",
            segment_id="seg1",
            variant_id="v1",
            event_type="explicit_rating",
            rating=4,
        )
        assert event.event_type == "explicit_rating"
        assert event.rating == 4
        assert event.signal_type is None

    def test_implicit_signal(self):
        event = FeedbackEvent(
            event_id="e2",
            user_id="u1",
            session_id="s1",
            segment_id="seg1",
            variant_id="v1",
            event_type="implicit_signal",
            signal_type="replay",
            signal_value=1.0,
        )
        assert event.event_type == "implicit_signal"
        assert event.signal_type == "replay"
        assert event.signal_value == 1.0

    def test_rating_validation(self):
        with pytest.raises(ValueError):
            FeedbackEvent(
                event_id="e3",
                user_id="u1",
                session_id="s1",
                segment_id="seg1",
                variant_id="v1",
                event_type="explicit_rating",
                rating=6,
            )

    def test_client_ts_present(self):
        event = FeedbackEvent(
            event_id="e4",
            user_id="u1",
            session_id="s1",
            segment_id="seg1",
            variant_id="v1",
            event_type="implicit_signal",
            signal_type="completion",
        )
        assert event.client_ts is not None


class TestStorySegmentModel:
    def test_minimal_construction(self):
        seg = StorySegment(
            segment_id="seg1",
            story_id="story1",
            segment_index=0,
            text="Hello world",
            word_count=2,
        )
        assert seg.segment_id == "seg1"
        assert seg.word_count == 2

    def test_features_dict(self):
        seg = StorySegment(
            segment_id="seg1",
            story_id="story1",
            segment_index=0,
            text="Hello world",
            word_count=2,
            features={"tokens": 2},
        )
        assert seg.features["tokens"] == 2


class TestStylePresetModel:
    def test_minimal_construction(self):
        preset = StylePreset(
            style_id="suspense",
            name="Suspenseful",
            description="Builds tension",
            system_prompt="Tell this story with suspense",
        )
        assert preset.style_id == "suspense"
        assert preset.system_prompt is not None

    def test_embedding_optional(self):
        preset = StylePreset(
            style_id="emotional",
            name="Emotional",
            description="Heartfelt",
            system_prompt="Tell this story emotionally",
        )
        assert preset.embedding is None or preset.embedding == []


class TestRewardModelInput:
    def test_minimal_construction(self):
        inp = RewardModelInput(
            user_id="u1",
            session_id="s1",
            style_selected="suspense",
            feedback_type="explicit_rating",
            feedback_value=4,
        )
        assert inp.user_id == "u1"
        assert inp.style_selected == "suspense"
        assert inp.feedback_value == 4

    def test_feedback_value_optional(self):
        inp = RewardModelInput(
            user_id="u1",
            session_id="s1",
            style_selected="emotional",
            feedback_type="implicit_signal",
        )
        assert inp.feedback_value is None

    def test_no_highdim_fields(self):
        inp = RewardModelInput(
            user_id="u1",
            session_id="s1",
            style_selected="descriptive",
            feedback_type="explicit_rating",
            feedback_value=5,
        )
        assert not hasattr(inp, "user_profile")
        assert not hasattr(inp, "story_features")
        assert not hasattr(inp, "variant_features")


class TestRewardModelOutput:
    def test_minimal_construction(self):
        out = RewardModelOutput(
            user_id="u1",
            updated_style_scores={"suspense": 0.5, "dialogue": 0.5},
            recommended_style="suspense",
            confidence=0.5,
        )
        assert out.model_version == "weighted-scoring-v1"
        assert out.recommended_style == "suspense"


class TestEvaluationRecord:
    def test_minimal_construction(self):
        rec = EvaluationRecord(
            record_id="rec1",
            task_id="T-A-002",
            agent="BRANCH",
            execution_time_s=1.5,
            outcome="success",
            review_score=8,
            architecture_compliance=1.0,
        )
        assert rec.architecture_compliance == 1.0

    def test_human_feedback_optional(self):
        rec = EvaluationRecord(
            record_id="rec2",
            task_id="T-A-003",
            agent="BOOTHROYD",
            execution_time_s=2.0,
            outcome="success",
            review_score=10,
            architecture_compliance=1.0,
            human_feedback="All migrations correct",
        )
        assert rec.human_feedback == "All migrations correct"


# ---------------------------------------------------------------------------
# Service logic
# ---------------------------------------------------------------------------

class TestRewardService:
    def test_resolve_signals_explicit_positive(self):
        signals = resolve_signals("explicit_rating", rating=5)
        assert "explicit_positive" in signals

    def test_resolve_signals_explicit_negative(self):
        signals = resolve_signals("explicit_rating", rating=1)
        assert "explicit_negative" in signals

    def test_resolve_signals_neutral_rating(self):
        signals = resolve_signals("explicit_rating", rating=3)
        assert signals == []

    def test_resolve_signals_implicit_completion(self):
        signals = resolve_signals("implicit_signal", signal_type="completion")
        assert "completion" in signals

    def test_resolve_signals_implicit_replay(self):
        signals = resolve_signals("implicit_signal", signal_type="replay")
        assert "replay" in signals

    def test_resolve_signals_implicit_skip(self):
        signals = resolve_signals("implicit_signal", signal_type="skip")
        assert "skip" in signals

    def test_resolve_signals_pause_adds_pause_long(self):
        signals = resolve_signals("implicit_signal", signal_type="pause")
        assert "pause_long" in signals

    def test_resolve_signals_unknown(self):
        signals = resolve_signals("implicit_signal", signal_type="unknown_type")
        assert signals == []

    def test_update_style_scores_empty_input(self):
        result = update_style_scores({}, "suspense", ["completion"])
        assert "suspense" in result
        assert all(k in result for k in ["suspense", "dialogue", "emotional", "fast_paced", "descriptive"])

    def test_update_style_scores_normalizes_to_one(self):
        result = update_style_scores(
            {"suspense": 0.5, "dialogue": 0.3, "emotional": 0.2},
            "suspense",
            ["explicit_positive"],
        )
        total = sum(result.values())
        assert abs(total - 1.0) < 0.001

    def test_update_style_scores_clamps_negative(self):
        result = update_style_scores(
            {"suspense": 0.05, "dialogue": 0.7, "emotional": 0.25},
            "suspense",
            ["explicit_negative"],
        )
        assert result["suspense"] >= 0.0

    def test_scoring_weights_consistency(self):
        assert SCORING_WEIGHTS["explicit_positive"] == 0.15
        assert SCORING_WEIGHTS["explicit_negative"] == -0.10
        assert SCORING_WEIGHTS["replay"] == 0.08
        assert SCORING_WEIGHTS["skip"] == -0.06
        assert SCORING_WEIGHTS["completion"] == 0.05
        assert SCORING_WEIGHTS["pause_long"] == -0.03

    def test_signal_map_completeness(self):
        expected_keys = ["rating_4", "rating_5", "rating_1", "rating_2", "replay", "skip", "completion", "pause_long"]
        for k in expected_keys:
            assert k in SIGNAL_MAP, f"Missing SIGNAL_MAP key: {k}"


# ---------------------------------------------------------------------------
# Config / settings
# ---------------------------------------------------------------------------

class TestSettings:
    def test_default_values(self):
        assert settings.app_name == "ECHO"
        assert settings.api_prefix == "/v1"

    def test_api_prefix_format(self):
        assert settings.api_prefix.startswith("/")

    def test_faiss_index_dir_default(self):
        assert settings.faiss_index_dir == "faiss_index"

    def test_audio_cache_dir_default(self):
        assert settings.audio_cache_dir == "audio_cache"
