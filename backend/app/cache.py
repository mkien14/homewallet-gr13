import hashlib
import json
import logging

import redis
from flask import current_app, has_app_context
from redis.backoff import NoBackoff
from redis.retry import Retry

from .config import load_config

logger = logging.getLogger(__name__)
_clients = {}
CACHE_PREFIX = "homewallet:dashboard:v1"
DEFAULT_TTL = 300


def _redis_client(config=None):
    cfg = config if config is not None else _runtime_config()
    host = cfg.get("REDIS_HOST")
    token = cfg.get("REDIS_AUTH_TOKEN")
    if not host or not token:
        return None

    port = cfg.get("REDIS_PORT", 6379)
    username = cfg.get("REDIS_USERNAME") or None
    ca_cert = cfg.get("REDIS_SSL_CA") or None
    timeout = cfg.get("REDIS_SOCKET_TIMEOUT", 0.5)
    identity = (host, port, username, token, ca_cert, timeout)
    client = _clients.get(identity)
    if client is None:
        options = {
            "host": host,
            "port": port,
            "username": username,
            "password": token,
            "ssl": True,
            "ssl_cert_reqs": "required",
            "ssl_check_hostname": True,
            "socket_connect_timeout": timeout,
            "socket_timeout": timeout,
            "decode_responses": True,
            # Keep the existing wire protocol when upgrading redis-py to 8.x.
            # Never replay INCR/EVAL after a lost reply: admission mutates counters.
            "protocol": 2,
            "retry": Retry(NoBackoff(), 0),
        }
        if ca_cert:
            options["ssl_ca_certs"] = ca_cert
        client = _clients[identity] = redis.Redis(**options)
    return client


def _runtime_config():
    return current_app.config if has_app_context() else load_config()


def _generation_key(household_id):
    return f"{CACHE_PREFIX}:household:{household_id}:generation"


def _dashboard_key(household_id, period, filters, generation):
    canonical_filters = json.dumps(filters or {}, sort_keys=True, separators=(",", ":"))
    filter_hash = hashlib.sha256(canonical_filters.encode("utf-8")).hexdigest()[:16]
    return (
        f"{CACHE_PREFIX}:household:{household_id}:generation:{generation}:"
        f"period:{period}:filters:{filter_hash}"
    )


def get_dashboard(household_id, period, *, filters=None, config=None):
    """Return (cached payload, generation); a missing/unavailable cache is a cache miss."""
    cfg = config if config is not None else _runtime_config()
    client = _redis_client(cfg)
    if client is None:
        return None, None
    try:
        generation_key = _generation_key(household_id)
        generation = client.get(generation_key) or "0"
        value = client.get(_dashboard_key(household_id, period, filters, generation))
        if (client.get(generation_key) or "0") != generation:
            return None, None
        if value is None:
            return None, generation
        payload = json.loads(value)
        if not isinstance(payload, dict):
            raise ValueError("dashboard cache payload must be an object")
        return payload, generation
    except Exception:
        logger.warning("dashboard cache read failed; using MySQL")
        return None, None


def set_dashboard(
    household_id,
    period,
    payload,
    generation,
    *,
    filters=None,
    ttl=None,
    config=None,
):
    """Cache a query result only if its household generation has not changed."""
    if generation is None:
        return
    cfg = config if config is not None else _runtime_config()
    client = _redis_client(cfg)
    if client is None:
        return
    try:
        generation_key = _generation_key(household_id)
        current_generation = client.get(generation_key) or "0"
        if current_generation != generation:
            return
        client.set(
            _dashboard_key(household_id, period, filters, generation),
            json.dumps(payload, separators=(",", ":")),
            ex=ttl or cfg.get("DASHBOARD_CACHE_TTL", DEFAULT_TTL),
        )
    except Exception:
        logger.warning("dashboard cache write failed; MySQL remains authoritative")


def invalidate_dashboard(household_id, *, config=None):
    """Advance the household cache generation; old entries expire by TTL."""
    client = _redis_client(config)
    if client is None:
        return
    try:
        client.incr(_generation_key(household_id))
    except Exception:
        logger.warning("dashboard cache invalidation failed; MySQL remains authoritative")
