import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}
    assert "status" in data
    assert data["status"] == "ok"


def test_hello_endpoint():
    response = client.get("/hello/Alice")
    assert response.status_code == 200
    data = response.json()
    assert data == {"message": "Hello, Alice!"}
    assert "message" in data
    assert data["message"] == "Hello, Alice!"


def test_hello_endpoint_with_different_name():
    response = client.get("/hello/Bob")
    assert response.status_code == 200
    data = response.json()
    assert data == {"message": "Hello, Bob!"}