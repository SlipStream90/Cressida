import pytest
from unittest.mock import patch, MagicMock


class TestDriftModule:
    def test_module_imports(self):
        from app.services.drift_service import compute_style_trajectory, detect_drift
        from app.services.drift_service import apply_drift_acceleration, DriftReport
        assert callable(compute_style_trajectory)
        assert callable(detect_drift)
        assert callable(apply_drift_acceleration)

    def test_drift_report_creation(self):
        from app.services.drift_service import DriftReport
        report = DriftReport(
            user_id="u1",
            previous_dominant_style="suspense",
            emerging_dominant_style="dialogue",
            drift_confidence=0.8,
            sessions_analyzed=10,
            recommendation="accelerate"
        )
        assert report.user_id == "u1"
        assert report.recommendation == "accelerate"

    def test_detect_drift_insufficient_history(self):
        from app.services.drift_service import detect_drift
        result = detect_drift("user_insufficient")
        assert result is None

    def test_compute_trajectory_empty(self):
        from app.services.drift_service import compute_style_trajectory
        trajectory = compute_style_trajectory("user_empty_traj")
        assert isinstance(trajectory, dict)
        assert "suspense" in trajectory

    def test_apply_drift_acceleration(self):
        from app.services.drift_service import apply_drift_acceleration, DriftReport
        report = DriftReport(
            user_id="u_accel",
            previous_dominant_style="suspense",
            emerging_dominant_style="dialogue",
            drift_confidence=0.9,
            sessions_analyzed=10,
            recommendation="accelerate"
        )
        apply_drift_acceleration("u_accel", report)
        assert True

    def test_drift_report_to_dict(self):
        from app.services.drift_service import DriftReport
        report = DriftReport(
            user_id="u1",
            previous_dominant_style="suspense",
            emerging_dominant_style="dialogue",
            drift_confidence=0.8,
            sessions_analyzed=10,
            recommendation="monitor"
        )
        d = report.to_dict()
        assert d["user_id"] == "u1"
        assert d["recommendation"] == "monitor"
