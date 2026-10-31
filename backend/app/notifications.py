"""In-app notification APIs and the server-side Web Push delivery helpers."""

import base64
import hashlib
import json
import logging
import re
from urllib.parse import urlsplit

from flask import Blueprint, current_app, g, jsonify, request

from .auth import require_auth
from .db import get_db
from .errors import ApiError
from .households import json_body

bp = Blueprint("notifications", __name__, url_prefix="/api")
logger = logging.getLogger(__name__)

_PUSH_HOSTS = {
    "fcm.googleapis.com",
    "android.googleapis.com",
    "push.services.mozilla.com",
    "updates.push.services.mozilla.com",
    "web.push.apple.com",
    "notify.windows.com",
}
_PUSH_HOST_SUFFIXES = (".push.services.mozilla.com", ".notify.windows.com")
_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")
_MAX_ENDPOINT_LENGTH = 2048


def _decode_base64url(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _validated_subscription(data):
    if not isinstance(data, dict):
        raise ApiError(422, "VALIDATION", "Subscription không hợp lệ")
    if "subscription" in data:
        if set(data) != {"subscription"}:
            raise ApiError(422, "VALIDATION", "Subscription không hợp lệ")
    elif set(data) - {"endpoint", "keys", "expirationTime"}:
        raise ApiError(422, "VALIDATION", "Subscription không hợp lệ")
    subscription = data.get("subscription", data)
    if not isinstance(subscription, dict):
        raise ApiError(422, "VALIDATION", "Subscription không hợp lệ")
    if set(subscription) - {"endpoint", "keys", "expirationTime"}:
        raise ApiError(422, "VALIDATION", "Subscription không hợp lệ")

    endpoint = subscription.get("endpoint")
    keys = subscription.get("keys")
    if (
        not isinstance(endpoint, str)
        or not endpoint
        or len(endpoint) > _MAX_ENDPOINT_LENGTH
        or not isinstance(keys, dict)
    ):
        raise ApiError(422, "VALIDATION", "Thiếu endpoint hoặc keys của subscription")

    try:
        parsed = urlsplit(endpoint)
        hostname = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except ValueError as exc:
        raise ApiError(422, "VALIDATION", "Endpoint push không hợp lệ") from exc

    allowed_host = hostname in _PUSH_HOSTS or any(
        hostname.endswith(suffix) for suffix in _PUSH_HOST_SUFFIXES
    )
    if (
        parsed.scheme != "https"
        or not hostname
        or not allowed_host
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ApiError(422, "VALIDATION", "Endpoint push không được hỗ trợ")

    p256dh = keys.get("p256dh")
    auth = keys.get("auth")
    if (
        not isinstance(p256dh, str)
        or not isinstance(auth, str)
        or len(p256dh) > 128
        or len(auth) > 64
        or not _BASE64URL.fullmatch(p256dh)
        or not _BASE64URL.fullmatch(auth)
    ):
        raise ApiError(422, "VALIDATION", "Public keys của subscription không hợp lệ")
    try:
        public_key = _decode_base64url(p256dh.rstrip("="))
        auth_secret = _decode_base64url(auth.rstrip("="))
    except (ValueError, TypeError) as exc:
        raise ApiError(
            422, "VALIDATION", "Public keys của subscription không hợp lệ"
        ) from exc
    if len(public_key) != 65 or len(auth_secret) != 16:
        raise ApiError(422, "VALIDATION", "Public keys của subscription không hợp lệ")

    return endpoint, p256dh, auth


def _payload_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, (str, bytes, bytearray)):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _isoformat(value):
    if value is None:
        return None
    return value.isoformat(timespec="seconds") if hasattr(value, "hour") else value.isoformat()


@bp.get("/notifications")
@require_auth
def list_notifications():
    raw_limit = request.args.get("limit", "50")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError) as exc:
        raise ApiError(422, "VALIDATION", "limit phải là số nguyên từ 1 đến 100") from exc
    if not 1 <= limit <= 100:
        raise ApiError(422, "VALIDATION", "limit phải là số nguyên từ 1 đến 100")

    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, type, payload_json, created_at, read_at "
            "FROM notifications WHERE user_id = %s AND channel = 'in_app' "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (g.user["id"], limit),
        )
        rows = cur.fetchall()
    items = []
    for row in rows:
        payload = _payload_dict(row["payload_json"])
        items.append(
            {
                "id": row["id"],
                "type": row["type"],
                "title": payload.get("title", "Thông báo"),
                "body": payload.get("body", ""),
                "deep_link": payload.get("deep_link", "/"),
                "created_at": _isoformat(row["created_at"]),
                "read_at": _isoformat(row["read_at"]),
                "read": row["read_at"] is not None,
            }
        )
    return jsonify(items=items)


@bp.patch("/notifications/<int:notification_id>")
@require_auth
def mark_notification_read(notification_id):
    data = json_body()
    if set(data) != {"read"} or data["read"] is not True:
        raise ApiError(422, "VALIDATION", 'Body phải có dạng {"read": true}')

    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "UPDATE notifications SET read_at = COALESCE(read_at, CURRENT_TIMESTAMP) "
            "WHERE id = %s AND user_id = %s AND channel = 'in_app'",
            (notification_id, g.user["id"]),
        )
        cur.execute(
            "SELECT read_at FROM notifications "
            "WHERE id = %s AND user_id = %s AND channel = 'in_app'",
            (notification_id, g.user["id"]),
        )
        row = cur.fetchone()
    if not row:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy thông báo")
    db.commit()
    return jsonify(id=notification_id, read=True, read_at=_isoformat(row["read_at"]))


@bp.post("/push/subscriptions")
@require_auth
def create_push_subscription():
    endpoint, p256dh, auth = _validated_subscription(json_body())
    endpoint_hash = hashlib.sha256(endpoint.encode("utf-8")).digest()
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO push_subscriptions "
                "(user_id, endpoint, endpoint_hash, p256dh, auth) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id), "
                "user_id = VALUES(user_id), endpoint = VALUES(endpoint), "
                "p256dh = VALUES(p256dh), auth = VALUES(auth), "
                "status = 'ACTIVE', updated_at = CURRENT_TIMESTAMP",
                (g.user["id"], endpoint, endpoint_hash, p256dh, auth),
            )
            subscription_id = int(cur.lastrowid)
            created = cur.rowcount == 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return jsonify(subscription={"id": subscription_id}), 201 if created else 200


@bp.delete("/push/subscriptions/<int:subscription_id>")
@require_auth
def delete_push_subscription(subscription_id):
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "DELETE FROM push_subscriptions WHERE id = %s AND user_id = %s",
            (subscription_id, g.user["id"]),
        )
    db.commit()
    # Treat an already removed or another user's subscription as an idempotent unsubscribe.
    return "", 204


def create_household_notifications(
    db,
    household_id,
    *,
    event_key,
    event_type,
    title,
    body,
    deep_link,
    commit=True,
):
    """Insert one idempotent in-app notification per current household member."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT user_id FROM household_members WHERE household_id = %s ORDER BY user_id",
            (household_id,),
        )
        user_ids = [int(row["user_id"]) for row in cur.fetchall()]

    payload = json.dumps(
        {
            "title": title,
            "body": body,
            "deep_link": deep_link,
            "event_type": event_type,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    inserted_user_ids = []
    try:
        with db.cursor() as cur:
            for user_id in user_ids:
                cur.execute(
                    "INSERT INTO notifications "
                    "(user_id, type, channel, payload_json, event_key) "
                    "VALUES (%s, %s, 'in_app', %s, %s) "
                    "ON DUPLICATE KEY UPDATE id = id",
                    (user_id, event_type, payload, f"{event_key}:user:{user_id}"),
                )
                if cur.rowcount == 1:
                    inserted_user_ids.append(user_id)
        if commit:
            db.commit()
    except Exception:
        if commit:
            db.rollback()
        raise
    return inserted_user_ids


def send_push_to_users(db, user_ids, *, event_type, deep_link, config=None):
    """Deliver a minimal push payload; best-effort per subscription."""
    config = config or current_app.config
    private_key = config.get("VAPID_PRIVATE_KEY")
    vapid_subject = config.get("VAPID_CLAIMS_SUB")
    if not user_ids or not private_key or not vapid_subject:
        return {
            "configured": bool(private_key and vapid_subject),
            "sent": 0,
            "failed": 0,
            "expired": 0,
        }

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.exception("Web Push dependency is unavailable")
        return {"configured": True, "sent": 0, "failed": 1, "expired": 0}

    payload = json.dumps(
        {"event_type": event_type, "deep_link": deep_link},
        separators=(",", ":"),
    )
    stats = {"configured": True, "sent": 0, "failed": 0, "expired": 0}
    expired_ids = []
    for user_id in sorted(set(user_ids)):
        with db.cursor() as cur:
            cur.execute(
                "SELECT id, endpoint, p256dh, auth "
                "FROM push_subscriptions WHERE user_id = %s AND status = 'ACTIVE' "
                "ORDER BY id",
                (user_id,),
            )
            subscriptions = cur.fetchall()
        for subscription in subscriptions:
            try:
                webpush(
                    subscription_info={
                        "endpoint": subscription["endpoint"],
                        "keys": {
                            "p256dh": subscription["p256dh"],
                            "auth": subscription["auth"],
                        },
                    },
                    data=payload,
                    vapid_private_key=private_key,
                    vapid_claims={"sub": vapid_subject},
                    ttl=60,
                    timeout=5,
                )
                stats["sent"] += 1
            except WebPushException as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in (404, 410):
                    expired_ids.append(subscription["id"])
                    stats["expired"] += 1
                else:
                    stats["failed"] += 1
                    logger.warning("Web Push delivery failed (status=%s)", status)
            except Exception as exc:
                stats["failed"] += 1
                logger.warning("Web Push delivery failed (%s)", type(exc).__name__)

    if expired_ids:
        try:
            with db.cursor() as cur:
                cur.executemany(
                    "UPDATE push_subscriptions SET status = 'EXPIRED', endpoint = '', "
                    "p256dh = '', auth = '', updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    [(value,) for value in expired_ids],
                )
            db.commit()
        except Exception:
            db.rollback()
            stats["failed"] += len(expired_ids)
            logger.exception("Could not remove expired Web Push subscriptions")
    return stats
