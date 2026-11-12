import pytest

from app.main import create_app


@pytest.fixture
def client():
    return create_app().test_client()


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_readiness_success_cached_and_closed(monkeypatch):
    from unittest.mock import MagicMock
    db = MagicMock()
    connect = MagicMock(return_value=db)
    monkeypatch.setattr("app.readiness.connect", connect)
    client = create_app().test_client()
    assert client.get("/ready").status_code == 200
    response = client.get("/api/ready")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    connect.assert_called_once()
    assert connect.call_args.kwargs == {"probe": True}
    db.cursor.return_value.__enter__.return_value.execute.assert_called_once_with("SELECT 1")
    db.close.assert_called_once()


def test_readiness_failure_is_private_and_liveness_survives(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("secret password and hostname")
    monkeypatch.setattr("app.readiness.connect", fail)
    client = create_app().test_client()
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.get_json() == {"status": "unavailable"}
    assert client.get("/health").status_code == 200


def test_readiness_recovers_after_cache_expiry(monkeypatch):
    from unittest.mock import MagicMock
    from app.readiness import Readiness
    clock = [100.0]
    monkeypatch.setattr("app.readiness.time.monotonic", lambda: clock[0])
    connect = MagicMock(side_effect=[RuntimeError("offline"), MagicMock()])
    monkeypatch.setattr("app.readiness.connect", connect)
    probe = Readiness()
    assert not probe.check({})
    assert not probe.check({})
    clock[0] += 11
    assert probe.check({})
    assert connect.call_count == 2


def test_concurrent_readiness_fails_closed_without_opening_more_connections(monkeypatch):
    from unittest.mock import MagicMock
    from app.readiness import Readiness
    connect = MagicMock()
    monkeypatch.setattr("app.readiness.connect", connect)
    probe = Readiness()
    probe._lock.acquire()
    try:
        assert not probe.check({})
        connect.assert_not_called()
    finally:
        probe._lock.release()


def test_ping(client):
    assert client.get("/api/ping").get_json() == {"message": "pong"}


def test_404_has_unified_error_format(client):
    r = client.get("/nope")
    body = r.get_json()
    assert r.status_code == 404
    assert set(body["error"]) == {"code", "message", "request_id"}


def test_request_id_header_present(client):
    assert client.get("/health").headers["X-Request-Id"]
