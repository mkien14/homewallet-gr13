import pytest

from app import cache, limits
from app.errors import ApiError


@pytest.fixture(autouse=True)
def isolated_clients(monkeypatch):
    monkeypatch.setattr(cache, "_clients", {})


def test_redis_client_keeps_tls_auth_resp2_and_no_command_replay():
    config = {
        "REDIS_HOST": "cache.invalid", "REDIS_PORT": 6379,
        "REDIS_AUTH_TOKEN": "unit-test-only", "REDIS_SSL_CA": "/test/ca.pem",
        "REDIS_SOCKET_TIMEOUT": 0.5,
    }
    client = cache._redis_client(config)
    options = client.connection_pool.connection_kwargs
    assert options["protocol"] == 2
    assert options["decode_responses"] is True
    assert options["ssl_cert_reqs"] == "required"
    assert options["ssl_check_hostname"] is True
    assert options["ssl_ca_certs"] == "/test/ca.pem"
    assert options["password"] == "unit-test-only"
    assert options["retry"].get_retries() == 0
    assert options["socket_timeout"] == options["socket_connect_timeout"] == 0.5
    assert cache._redis_client(config) is client


def test_cache_requires_both_host_and_password():
    assert cache._redis_client({"REDIS_HOST": "cache.invalid"}) is None
    assert cache._redis_client({"REDIS_AUTH_TOKEN": "unit-test-only"}) is None


def test_cache_connection_errors_are_misses(monkeypatch):
    class Unavailable:
        def get(self, _key):
            raise ConnectionError("test outage")

    monkeypatch.setattr(cache, "_redis_client", lambda _cfg: Unavailable())
    assert cache.get_dashboard(2, "2026-11", config={}) == (None, None)


def test_admission_store_failure_blocks_writes_but_allows_reads(app, monkeypatch):
    monkeypatch.setattr(limits, "_redis_client", lambda _cfg: None)
    app.config["RATE_LIMIT_ENABLED"] = True
    with app.test_request_context("/api/transactions", method="POST"):
        with pytest.raises(ApiError) as error:
            limits._admit([("test", "synthetic", 60, 2)], required=True)
        assert error.value.status == 503
        assert error.value.code == "QUOTA_UNAVAILABLE"
    with app.test_request_context("/api/dashboard"):
        limits._admit([("test", "synthetic", 60, 2)], required=False)
