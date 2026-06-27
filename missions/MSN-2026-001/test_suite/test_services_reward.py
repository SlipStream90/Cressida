import pytest
from app.services.reward_service import (
    resolve_signals,
    update_style_scores,
    SCORING_WEIGHTS,
    SIGNAL_MAP,
)


class TestResolveSignals:
    def test_explicit_rating_5(self):
        signals = resolve_signals("explicit_rating", rating=5)
        assert signals == ["explicit_positive"]

    def test_explicit_rating_4(self):
        signals = resolve_signals("explicit_rating", rating=4)
        assert signals == ["explicit_positive"]

    def test_explicit_rating_1(self):
        signals = resolve_signals("explicit_rating", rating=1)
        assert signals == ["explicit_negative"]

    def test_explicit_rating_2(self):
        signals = resolve_signals("explicit_rating", rating=2)
        assert signals == ["explicit_negative"]

    def test_explicit_rating_3_neutral(self):
        signals = resolve_signals("explicit_rating", rating=3)
        assert signals == []

    def test_implicit_replay(self):
        signals = resolve_signals("implicit_signal", signal_type="replay")
        assert signals == ["replay"]

    def test_implicit_skip(self):
        signals = resolve_signals("implicit_signal", signal_type="skip")
        assert signals == ["skip"]

    def test_implicit_completion(self):
        signals = resolve_signals("implicit_signal", signal_type="completion")
        assert signals == ["completion"]

    def test_implicit_pause_adds_pause_long(self):
        signals = resolve_signals("implicit_signal", signal_type="pause")
        assert "pause_long" in signals

    def test_unknown_signal(self):
        signals = resolve_signals("implicit_signal", signal_type="unknown")
        assert signals == []

    def test_no_args_returns_empty(self):
        signals = resolve_signals("explicit_rating")
        assert signals == []


class TestUpdateStyleScores:
    def test_empty_input_uses_defaults(self):
        result = update_style_scores({}, "suspense", ["completion"])
        for style in ["suspense", "dialogue", "emotional", "fast_paced", "descriptive"]:
            assert style in result

    def test_cold_start_uniform(self):
        empty = update_style_scores({}, "suspense", [])
        for style in ["suspense", "dialogue", "emotional", "fast_paced", "descriptive"]:
            assert empty[style] == pytest.approx(0.2, abs=0.01)

    def test_normalizes_to_one(self):
        result = update_style_scores(
            {"suspense": 0.5, "dialogue": 0.3, "emotional": 0.2},
            "suspense",
            ["explicit_positive"],
        )
        total = sum(result.values())
        assert abs(total - 1.0) < 0.001

    def test_positive_signal_increases_target(self):
        before = {"suspense": 0.4, "dialogue": 0.3, "emotional": 0.3}
        after = update_style_scores(before, "suspense", ["explicit_positive"])
        assert after["suspense"] > before["suspense"]

    def test_negative_signal_decreases_target(self):
        before = {"suspense": 0.4, "dialogue": 0.3, "emotional": 0.3}
        after = update_style_scores(before, "suspense", ["explicit_negative"])
        assert after["suspense"] < before["suspense"]

    def test_floor_at_zero(self):
        before = {"suspense": 0.01, "dialogue": 0.7, "emotional": 0.29}
        after = update_style_scores(before, "suspense", ["explicit_negative"])
        assert after["suspense"] >= 0.0

    def test_multiple_signals_accumulate(self):
        before = {"suspense": 0.4, "dialogue": 0.3, "emotional": 0.3}
        single = update_style_scores(dict(before), "suspense", ["completion"])
        multi = update_style_scores(dict(before), "suspense", ["completion", "replay"])
        assert multi["suspense"] > single["suspense"]

    def test_preserves_untouched_styles(self):
        before = {"suspense": 0.4, "dialogue": 0.3, "emotional": 0.3}
        after = update_style_scores(before, "suspense", ["explicit_positive"])
        for style in ["dialogue", "emotional"]:
            assert style in after

    def test_selected_style_not_in_scores(self):
        result = update_style_scores({"dialogue": 1.0}, "suspense", ["completion"])
        assert "suspense" in result


class TestRewardConstants:
    def test_scoring_weights_match_spec(self):
        assert SCORING_WEIGHTS["explicit_positive"] == 0.15
        assert SCORING_WEIGHTS["explicit_negative"] == -0.10
        assert SCORING_WEIGHTS["replay"] == 0.08
        assert SCORING_WEIGHTS["skip"] == -0.06
        assert SCORING_WEIGHTS["completion"] == 0.05
        assert SCORING_WEIGHTS["pause_long"] == -0.03

    def test_signal_map_completeness(self):
        expected = ["rating_4", "rating_5", "rating_1", "rating_2", "replay", "skip", "completion", "pause_long"]
        for k in expected:
            assert k in SIGNAL_MAP

    def test_scoring_weights_all_defined(self):
        required_signal_types = {"explicit_positive", "explicit_negative", "replay", "skip", "completion", "pause_long"}
        assert set(SCORING_WEIGHTS.keys()) == required_signal_types
