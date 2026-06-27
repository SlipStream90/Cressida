import pytest
from unittest.mock import patch, MagicMock
from app.models.feedback import FeedbackEvent


class TestABModule:
    def test_module_imports(self):
        from app.services.ab_service import get_ab_assignment, record_ab_result
        from app.services.ab_service import update_ab_result_with_feedback
        from app.services.ab_service import get_ab_results_summary
        from app.services.ab_service import ABTestConfig, ABTestResult
        assert callable(get_ab_assignment)
        assert callable(record_ab_result)
        assert callable(update_ab_result_with_feedback)
        assert callable(get_ab_results_summary)

    def test_ab_test_config_creation(self):
        from app.services.ab_service import ABTestConfig
        config = ABTestConfig(
            test_id="t1", name="Test 1",
            styles_under_test=["suspense", "dialogue"],
            assignment_strategy="round_robin"
        )
        assert config.test_id == "t1"
        assert config.active is True

    def test_ab_test_result_creation(self):
        from app.services.ab_service import ABTestResult
        result = ABTestResult(
            test_id="t1", user_id="u1", session_id="s1",
            segment_id="seg1", assigned_style="suspense", variant_id="v1"
        )
        assert result.engagement_score == 0.0
        assert result.completion is False

    @patch("app.services.ab_service._get_redis")
    def test_round_robin_distribution(self, mock_get_redis):
        from app.services.ab_service import get_ab_assignment

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        results = {}
        for i in range(30):
            variant = get_ab_assignment("rr_test", f"user_{i}", ["variant_a", "variant_b", "variant_c"])
            results[variant] = results.get(variant, 0) + 1

        total = sum(results.values())
        assert total == 30
        for v in results:
            assert results[v] >= 5

    @patch("app.services.ab_service._get_redis")
    def test_assign_increments_round_robin(self, mock_get_redis):
        from app.services.ab_service import get_ab_assignment

        mock_redis = MagicMock()
        mock_redis.get.side_effect = [None, b"1", b"2"]
        mock_get_redis.return_value = mock_redis

        first = get_ab_assignment("rr_inc", "user_seq", ["a", "b", "c"])
        assert first == "a"
        second = get_ab_assignment("rr_inc", "user_seq", ["a", "b", "c"])
        assert second == "b"
        third = get_ab_assignment("rr_inc", "user_seq", ["a", "b", "c"])
        assert third == "c"

    def test_record_ab_result(self):
        from app.services.ab_service import record_ab_result
        result = record_ab_result("t1", "u1", "s1", "seg1", "suspense", "v1")
        assert result.test_id == "t1"
        assert result.user_id == "u1"

    def test_update_with_feedback(self):
        from app.services.ab_service import record_ab_result, update_ab_result_with_feedback

        result = record_ab_result("t_fb1", "u_fb1", "s_fb1", "seg_fb1", "suspense", "v_fb1")
        event = FeedbackEvent(
            event_id="e_fb1", user_id="u_fb1", session_id="s_fb1",
            segment_id="seg_fb1", variant_id="v_fb1",
            event_type="explicit_rating", rating=4
        )
        update_ab_result_with_feedback("t_fb1", "s_fb1", "v_fb1", event)
        assert result.explicit_rating is not None

    def test_summary(self):
        from app.services.ab_service import record_ab_result, get_ab_results_summary

        for u in ["u1", "u2", "u3"]:
            record_ab_result("summary_test", u, f"s_{u}", "seg1", "suspense", "v1")
        summary = get_ab_results_summary("summary_test")
        assert "suspense" in summary
        assert summary["suspense"]["sample_count"] == 3

    @patch("app.services.ab_service._get_redis")
    def test_weighted_assignment(self, mock_get_redis):
        from app.services.ab_service import get_ab_assignment

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        variant = get_ab_assignment(
            "weighted_test", "user_w", ["a", "b"],
            assignment_strategy="weighted",
            style_scores={"a": 0.9, "b": 0.1}
        )
        assert variant in ["a", "b"]
