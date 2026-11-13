"""Opt-in tests against a disposable, authenticated TLS Redis on loopback only."""
import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import redis
from flask import g

from app import cache, limits
from app.errors import ApiError


@pytest.fixture
def local_redis(app, monkeypatch):
    if os.getenv("HOMEWALLET_REDIS_ACCEPTANCE") != "1":
        pytest.skip("Run scripts/run-redis-acceptance.py for an isolated TLS server")
    host = os.environ["HOMEWALLET_REDIS_TLS_HOST"]
    if host not in {"localhost", "127.0.0.1"}:
        pytest.fail("Redis acceptance must only connect to its loopback fixture")
    assert redis.__version__ == "8.1.0"
    namespace = uuid.uuid4().hex
    config = {
        "REDIS_HOST": host,
        "REDIS_PORT": int(os.environ["HOMEWALLET_REDIS_TLS_PORT"]),
        "REDIS_AUTH_TOKEN": os.environ["HOMEWALLET_REDIS_TLS_PASSWORD"],
        "REDIS_SSL_CA": os.environ["HOMEWALLET_REDIS_TLS_CA"],
        "REDIS_SOCKET_TIMEOUT": 1.0,
        "RATE_LIMIT_ENABLED": True,
        "APP_ENV": "test", "DB_HOST": "localhost", "DB_NAME": namespace + "_test",
    }
    monkeypatch.setattr(cache, "_clients", {})
    monkeypatch.setattr(cache, "CACHE_PREFIX", "homewallet:test:" + namespace)
    app.config.update(config)
    client = cache._redis_client(config)
    assert client.ping() is True
    yield app, config, client
    admission_namespace = hashlib.sha256(
        f"test:localhost:{namespace}_test".encode()
    ).hexdigest()[:16]
    for pattern in (cache.CACHE_PREFIX + ":*", "homewallet:admission:v1:{" + admission_namespace + "}:*"):
        for key in client.scan_iter(match=pattern):
            client.delete(key)
    for owned_client in cache._clients.values():
        owned_client.close()


def test_tls_password_and_hostname_verification(local_redis):
    _app, config, client = local_redis
    assert client.ping() is True
    with pytest.raises(redis.exceptions.AuthenticationError):
        cache._redis_client(dict(config, REDIS_AUTH_TOKEN="incorrect-test-password")).ping()
    # The fixture certificate has DNS:localhost only; this must not be bypassed.
    with pytest.raises(redis.exceptions.ConnectionError):
        cache._redis_client(dict(config, REDIS_HOST="127.0.0.1")).ping()
    with pytest.raises(redis.exceptions.ConnectionError):
        cache._redis_client(dict(config, REDIS_SSL_CA=None)).ping()


def test_rejected_auth_is_cache_miss_and_blocks_required_admission(local_redis):
    app, config, _client = local_redis
    unavailable = dict(config, REDIS_AUTH_TOKEN="incorrect-test-password")
    assert cache.get_dashboard(42, "2026-11", config=unavailable) == (None, None)
    app.config.update(unavailable)
    with app.test_request_context("/api/transactions", method="POST"):
        with pytest.raises(ApiError) as error:
            limits._admit([("test", "synthetic", 60, 2)], required=True)
        assert error.value.status == 503
        assert error.value.code == "QUOTA_UNAVAILABLE"
    with app.test_request_context("/api/dashboard"):
        limits._admit([("test", "synthetic", 60, 2)], required=False)


def test_cache_roundtrip_filters_ttl_and_invalidation(local_redis):
    _app, config, client = local_redis
    household, period = 42, "2026-11"
    assert cache.get_dashboard(household, period, config=config) == (None, "0")
    payload = {"total": 120000, "label": "Ăn uống"}
    cache.set_dashboard(household, period, payload, "0", ttl=60, config=config)
    assert cache.get_dashboard(household, period, config=config) == (payload, "0")
    assert cache.get_dashboard(household, period, filters={"member": 2}, config=config) == (None, "0")
    assert cache.get_dashboard(household + 1, period, config=config) == (None, "0")
    key = cache._dashboard_key(household, period, None, "0")
    assert 0 < client.ttl(key) <= 60
    cache.invalidate_dashboard(household, config=config)
    assert cache.get_dashboard(household, period, config=config) == (None, "1")
    cache.set_dashboard(household, period, {"stale": True}, "0", config=config)
    assert cache.get_dashboard(household, period, config=config) == (None, "1")


def test_expired_or_corrupt_cache_is_a_miss(local_redis):
    _app, config, client = local_redis
    key = cache._dashboard_key(42, "2026-11", None, "0")
    client.set(key, "not-json", ex=60)
    assert cache.get_dashboard(42, "2026-11", config=config) == (None, None)
    client.set(key, "[]", ex=60)
    assert cache.get_dashboard(42, "2026-11", config=config) == (None, None)
    client.pexpire(key, 0)
    assert cache.get_dashboard(42, "2026-11", config=config) == (None, "0")


def test_rate_limit_lua_is_atomic_across_clients_and_windows(local_redis, monkeypatch):
    app, _config, _client = local_redis
    # Avoid a clock-window boundary while requests run concurrently.
    monkeypatch.setattr(limits.time, "time", lambda: 1794535205)

    def attempt(_index):
        with app.test_request_context("/api/transactions", method="POST"):
            try:
                limits._admit([
                    ("test-user", "synthetic", 60, 7),
                    ("test-global", "all", 60, 100),
                ], required=True)
                return True
            except ApiError as error:
                assert error.status == 429
                assert error.code == "RATE_LIMITED"
                assert 1 <= g.retry_after <= 65
                return False

    with ThreadPoolExecutor(max_workers=12) as pool:
        assert sum(pool.map(attempt, range(32))) == 7
    # Rejected requests must not consume the other window in the same Lua script.
    with app.test_request_context("/api/transactions", method="POST"):
        limits._admit([("test-global", "all", 60, 8)], required=True)
        with pytest.raises(ApiError) as error:
            limits._admit([("test-global", "all", 60, 8)], required=True)
        assert error.value.status == 429
