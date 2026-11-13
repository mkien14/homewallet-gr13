"""Shared Redis admission limits; never store tokens, email or raw IP addresses.

Limits are independent of the dashboard cache: expensive operations fail closed
if their quota cannot be checked. All windows in one request are admitted
atomically, across API tasks. Disabled by default outside production.
"""
import hashlib
import logging
import time

from flask import current_app, g, request

from .cache import _redis_client
from .errors import ApiError

logger = logging.getLogger(__name__)
_ADMIT = """
for i, key in ipairs(KEYS) do
  local count = tonumber(redis.call('GET', key) or '0')
  if count >= tonumber(ARGV[(i-1)*2+1]) then
    return {0, math.max(redis.call('TTL', key), 1)}
  end
end
for i, key in ipairs(KEYS) do
  local count = redis.call('INCR', key)
  if count == 1 then redis.call('EXPIRE', key, ARGV[(i-1)*2+2]) end
end
return {1, 0}
"""


def _admit(windows, *, required):
    cfg = current_app.config
    if not cfg.get("RATE_LIMIT_ENABLED"):
        return
    now = int(time.time())
    namespace = hashlib.sha256(
        f"{cfg.get('APP_ENV', 'dev')}:{cfg['DB_HOST']}:{cfg['DB_NAME']}".encode()
    ).hexdigest()[:16]
    keys, args = [], []
    for scope, subject, seconds, maximum in windows:
        if maximum < 1:
            raise RuntimeError("Admission limits must be positive")
        subject_hash = hashlib.sha256(str(subject).encode()).hexdigest()
        clock = now + 7 * 3600 if seconds == 86400 else now
        keys.append(f"homewallet:admission:v1:{{{namespace}}}:{scope}:{subject_hash}:{clock // seconds}")
        args.extend([maximum, seconds - clock % seconds + 5])
    try:
        redis = _redis_client(cfg)
        if redis is None:
            raise RuntimeError("Admission store is not configured")
        admitted, retry = redis.eval(_ADMIT, len(keys), *keys, *args)
    except Exception:
        logger.warning("admission store unavailable")
        if required:
            raise ApiError(503, "QUOTA_UNAVAILABLE", "Chưa kiểm tra được hạn mức. Hãy thử lại sau.") from None
        return
    if not int(admitted):
        g.retry_after = min(max(int(retry), 1), 86405)
        raise ApiError(429, "RATE_LIMITED", "Bạn đã đạt hạn mức. Hãy đợi rồi thử lại.")


def enforce_user_limit(subject):
    cfg = current_app.config
    write = request.method not in ("GET", "HEAD", "OPTIONS")
    windows = [("user-minute", subject, 60, cfg["API_REQUESTS_PER_MINUTE"])]
    if write:
        windows.append(("write-minute", subject, 60, cfg["API_WRITES_PER_MINUTE"]))
    _admit(windows, required=write)


def admit_costly_operation(operation, household_id):
    cfg = current_app.config
    limits = {
        "receipt": ("RECEIPTS_PER_USER_DAY", "RECEIPTS_PER_HOUSEHOLD_DAY", "RECEIPTS_GLOBAL_DAY"),
        "suggestion": ("AI_SUGGESTIONS_PER_USER_DAY", "AI_SUGGESTIONS_PER_HOUSEHOLD_DAY", "AI_SUGGESTIONS_GLOBAL_DAY"),
    }
    user_limit, household_limit, global_limit = limits[operation]
    _admit([
        (f"{operation}-user-day", g.user["id"], 86400, cfg[user_limit]),
        (f"{operation}-household-day", household_id, 86400, cfg[household_limit]),
        (f"{operation}-global-day", "all", 86400, cfg[global_limit]),
    ], required=True)
