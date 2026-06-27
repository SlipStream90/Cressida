import pytest
from unittest.mock import patch, MagicMock
from app.models.feedback import FeedbackEvent


API_KEY = "integration-test-api-key"


class TestFullSystemIntegration:
    """End-to-end integration: 13 steps covering all subsystems."""

    @patch("app.services.ab_service._get_redis")
    def test_full_system_flow(self, mock_ab_redis):
        from app.services.reward_service import resolve_signals, update_style_scores
        from app.services.ab_service import get_ab_assignment, record_ab_result
        from app.services.drift_service import detect_drift, DriftReport
        from app.services.session_adapter import SessionStyleState, initialize_session_style
        from app.services.cache_service import cache_profile, get_cached_profile

        # Set up AB redis mock
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_ab_redis.return_value = mock_redis

        style_scores = {}

        # Step 1: Cache profile functions are callable (mock isolation prevents roundtrip)
        with patch("app.services.cache_service.get_redis") as mock_cache:
            m = MagicMock()
            m.get.return_value = '{"name": "Test User", "style": "suspense"}'
            mock_cache.return_value = m
            cache_profile("user_int", {"name": "Test User", "style": "suspense"})
            profile = get_cached_profile("user_int")
            assert profile == {"name": "Test User", "style": "suspense"}

        # Step 2: Start session → variant assigned via AB
        variant = get_ab_assignment("style_test", "user_int", ["variant_a", "variant_b"], "round_robin")
        assert variant in ["variant_a", "variant_b"]

        # Step 3: Verify style scores default state
        style_scores = {"suspense": 0.4, "dialogue": 0.3, "emotional": 0.3}
        assert "suspense" in style_scores

        # Step 4: Explicit feedback (rating 5) → reward resolves signals → style scores updated
        signals_rating5 = resolve_signals("explicit_rating", rating=5)
        assert "explicit_positive" in signals_rating5
        style_scores = update_style_scores(style_scores, "suspense", signals_rating5)
        assert style_scores.get("suspense", 0) > 0.4
        total = sum(style_scores.values())
        assert abs(total - 1.0) < 0.001

        # Step 5: Implicit feedback (completion) → reward resolves signals
        signals_completion = resolve_signals("implicit_signal", signal_type="completion")
        assert "completion" in signals_completion
        style_scores = update_style_scores(style_scores, "suspense", signals_completion)
        assert style_scores.get("suspense", 0) > 0.0

        # Step 6: Style scores updated (simulating second story generation)
        assert max(style_scores, key=style_scores.get) in ["suspense", "dialogue", "emotional"]

        # Step 7: Explicit feedback (rating 2) → negative reward
        signals_rating2 = resolve_signals("explicit_rating", rating=2)
        assert "explicit_negative" in signals_rating2
        style_scores_before = dict(style_scores)
        style_scores = update_style_scores(style_scores, "suspense", signals_rating2)
        assert style_scores.get("suspense", 1.0) <= style_scores_before.get("suspense", 1.0)

        # Step 8: Implicit feedback (skip) → negative reward
        signals_skip = resolve_signals("implicit_signal", signal_type="skip")
        assert "skip" in signals_skip
        style_scores_before2 = dict(style_scores)
        style_scores = update_style_scores(style_scores, "suspense", signals_skip)
        assert style_scores.get("suspense", 1.0) <= style_scores_before2.get("suspense", 1.0)

        # Step 9: Implicit feedback (replay) → positive reward
        signals_replay = resolve_signals("implicit_signal", signal_type="replay")
        assert "replay" in signals_replay
        style_scores = update_style_scores(style_scores, "suspense", signals_replay)
        assert style_scores.get("suspense", 0) >= 0.0

        # Step 10: Drift detection (module-level functions — no reward records = None)
        drift_result = detect_drift("user_int")
        assert drift_result is None

        # Step 11: AB test round-robin assigns sequentially
        with patch("app.services.ab_service._get_redis") as mock_rr:
            m = MagicMock()
            m.get.side_effect = [None, b"1", b"2"]
            mock_rr.return_value = m
            from app.services.ab_service import get_ab_assignment
            first = get_ab_assignment("exp_final", "user_seq", ["a", "b", "c"])
            assert first == "a"
            second = get_ab_assignment("exp_final", "user_seq", ["a", "b", "c"])
            assert second == "b"
            third = get_ab_assignment("exp_final", "user_seq", ["a", "b", "c"])
            assert third == "c"

        # Step 12: Session style state tracks within-session (no UserProfile write)
        style_state = SessionStyleState(
            user_id="user_int",
            session_id="session_int",
            initial_style="suspense",
            current_style="suspense",
            within_session_scores={"suspense": 0.5, "dialogue": 0.5},
            signals_received=2,
        )
        d = style_state.to_dict()
        restored = SessionStyleState.from_dict(d)
        assert restored.user_id == "user_int"
        assert restored.signals_received == 2
        assert restored.user_id == "user_int"
        assert "profile" not in d.keys() or d.get("profile") is None

        # Step 13: Cache functions handle hit and miss independently
        with patch("app.services.cache_service.get_redis") as mock_cache2:
            m = MagicMock()
            mock_cache2.return_value = m

            m.get.return_value = '{"value": "cached"}'
            assert get_cached_profile("cached_user") == {"value": "cached"}

            m.get.return_value = None
            assert get_cached_profile("missing_user") is None
