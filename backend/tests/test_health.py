import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "CityScope API"}


def test_root() -> None:
    assert client.get("/").json() == {"name": "CityScope", "status": "running"}


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
)
def test_cors(origin: str) -> None:
    response = client.get("/api/v1/health", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin


def test_cors_rejects_unknown_origin() -> None:
    response = client.get("/api/v1/health", headers={"Origin": "https://unknown.example"})
    assert "access-control-allow-origin" not in response.headers
