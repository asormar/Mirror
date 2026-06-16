from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "environment" in body


def test_openapi_lists_routes() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    paths = spec["paths"]
    expected = {
        "/api/v1/auth/signup",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/me",
        "/api/v1/entities",
        "/api/v1/subscriptions",
    }
    assert expected.issubset(paths.keys()), f"missing={expected - paths.keys()}"


def test_signup_validates_body() -> None:
    response = client.post("/api/v1/auth/signup", json={})
    assert response.status_code == 422


def test_signup_rejects_short_password() -> None:
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": "x@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_login_validates_body() -> None:
    response = client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422


def test_me_requires_token() -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401


def test_subscriptions_require_token() -> None:
    response = client.get("/api/v1/subscriptions")
    assert response.status_code == 401
