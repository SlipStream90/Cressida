import pytest
from unittest.mock import patch, MagicMock


class TestSessionModule:
    def test_module_imports(self):
        from app.services.session_adapter import (
            SessionStyleState, initialize_session_style,
            update_session_style, get_current_style
        )
        assert SessionStyleState
        assert callable(initialize_session_style)
        assert callable(update_session_style)
        assert callable(get_current_style)

    def test_session_style_state_defaults(self):
        from app.services.session_adapter import SessionStyleState
        state = SessionStyleState(
            user_id="u1", session_id="s1",
            initial_style="suspense", current_style="suspense",
            within_session_scores={"a": 0.5, "b": 0.5},
        )
        assert state.signals_received == 0
        assert state.user_id == "u1"
        assert state.current_style == "suspense"

    def test_session_style_state_roundtrip(self):
        from app.services.session_adapter import SessionStyleState
        state = SessionStyleState(
            user_id="u1", session_id="s1",
            initial_style="suspense", current_style="dialogue",
            within_session_scores={"suspense": 0.3, "dialogue": 0.7},
            signals_received=2,
        )
        d = state.to_dict()
        restored = SessionStyleState.from_dict(d)
        assert restored.user_id == "u1"
        assert restored.current_style == "dialogue"
        assert restored.signals_received == 2

    @patch("app.services.session_adapter._get_redis")
    def test_initialize_session_style(self, mock_get_redis):
        from app.services.session_adapter import initialize_session_style, SessionStyleState

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        state = initialize_session_style("u1", "s1", {
            "suspense": 0.5, "dialogue": 0.3, "emotional": 0.2
        })
        assert isinstance(state, SessionStyleState)
        assert state.initial_style == "suspense"
        assert mock_redis.setex.call_count == 1

    @patch("app.services.session_adapter._get_redis")
    def test_update_session_style_no_session(self, mock_get_redis):
        from app.services.session_adapter import update_session_style
        from app.models.feedback import FeedbackEvent

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        event = FeedbackEvent(
            event_id="e1", user_id="u1", session_id="s_none",
            segment_id="seg1", variant_id="v1",
            event_type="implicit_signal", signal_type="completion"
        )
        result = update_session_style("s_none", event)
        assert result is None

    @patch("app.services.session_adapter._get_redis")
    def test_get_current_style_no_session(self, mock_get_redis):
        from app.services.session_adapter import get_current_style

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        result = get_current_style("s_missing")
        assert result is None
