from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
H = {"X-API-Key": "test-key"}


def test_health_wired():
    r = client.get("/v1/health")
    assert r.status_code != 404


def test_sessions_wired():
    r = client.post("/v1/sessions/", json={}, headers=H)
    assert r.status_code != 404


def test_feedback_explicit_wired():
    r = client.post("/v1/feedback/explicit",
        json={}, headers=H)
    assert r.status_code != 404


def test_feedback_implicit_wired():
    r = client.post("/v1/feedback/implicit",
        json={}, headers=H)
    assert r.status_code != 404


def test_abtests_wired():
    r = client.get("/v1/abtests/", headers=H)
    assert r.status_code != 404


def test_analytics_wired():
    r = client.get(
        "/v1/analytics/users/test/style-history",
        headers=H)
    assert r.status_code != 404


def test_users_wired():
    r = client.get("/v1/users/", headers=H)
    assert r.status_code != 404


def test_stories_wired():
    r = client.get("/v1/stories/test", headers=H)
    assert r.status_code != 404


def test_variants_wired():
    r = client.get("/v1/variants/test", headers=H)
    assert r.status_code != 404
