import pytest

from app.main import create_app


@pytest.fixture
def client():
    return create_app().test_client()


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_ping(client):
    assert client.get("/api/ping").get_json() == {"message": "pong"}


def test_404_has_unified_error_format(client):
    r = client.get("/nope")
    body = r.get_json()
    assert r.status_code == 404
    assert set(body["error"]) == {"code", "message", "request_id"}


def test_request_id_header_present(client):
    assert client.get("/health").headers["X-Request-Id"]