from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["name"] == "ECHO"
    assert data["version"] == "0.2.0"


def test_health_check_has_uptime():
    response = client.get("/health")
    assert response.status_code == 200
    assert "uptime" in response.json()
