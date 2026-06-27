import pytest
from unittest.mock import patch, MagicMock


API_KEY = "test-api-key-12345"


@pytest.fixture
def client():
    with patch.dict("os.environ", {"API_KEY": API_KEY}):
        from fastapi.testclient import TestClient
        from app.main import app
        yield TestClient(app)


class TestFeedbackRoutes:
    def test_submit_explicit_feedback(self, client):
        response = client.post(
            "/v1/feedback/explicit",
            params={
                "user_id": "user_1",
                "session_id": "session_1",
                "segment_id": "seg_1",
                "variant_id": "var_1",
                "rating": 5,
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "recorded"

    def test_submit_implicit_feedback(self, client):
        response = client.post(
            "/v1/feedback/implicit",
            params={
                "user_id": "user_1",
                "session_id": "session_1",
                "segment_id": "seg_1",
                "variant_id": "var_1",
                "signal_type": "completion",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "recorded"

    def test_submit_implicit_pause_with_value(self, client):
        response = client.post(
            "/v1/feedback/implicit",
            params={
                "user_id": "user_1",
                "session_id": "session_1",
                "segment_id": "seg_1",
                "variant_id": "var_1",
                "signal_type": "pause",
                "signal_value": 45.0,
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200

    def test_feedback_requires_api_key(self, client):
        response = client.post(
            "/v1/feedback/explicit",
            params={
                "user_id": "user_1",
                "session_id": "session_1",
                "segment_id": "seg_1",
                "variant_id": "var_1",
                "rating": 5,
            },
        )
        assert response.status_code == 401

    def test_feedback_empty_api_key(self, client):
        response = client.post(
            "/v1/feedback/explicit",
            params={
                "user_id": "user_1",
                "session_id": "session_1",
                "segment_id": "seg_1",
                "variant_id": "var_1",
                "rating": 5,
            },
            headers={"X-API-Key": ""},
        )
        assert response.status_code == 401
