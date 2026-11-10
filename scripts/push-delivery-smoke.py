"""Validate one controlled browser subscription; --send delivers one test push.

Run inside the deployed backend container with its DB/VAPID environment.
Output contains IDs and delivery status only. It never creates notifications,
runs scheduled jobs, sends email, or writes to the database.
"""

import argparse
import contextlib
import io
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


# Also support running this file from a repository checkout.
script_path = globals().get("__file__")
if script_path:
    backend_dir = Path(script_path).resolve().parents[1] / "backend"
    if backend_dir.is_dir():
        sys.path.insert(0, str(backend_dir))


def emit(event, **fields):
    print(json.dumps({
        "event": event,
        "at_utc": datetime.now(timezone.utc).isoformat(),
        **fields,
    }), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument("--subscription-id", required=True, type=int)
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    if args.user_id <= 0 or args.subscription_id <= 0:
        parser.error("IDs must be positive")

    stage = "imports"
    db = None
    try:
        from app.config import load_config
        from app.db import connect
        from app.notifications import _validated_subscription
        from pywebpush import webpush

        logging.disable(logging.CRITICAL)
        config = load_config()
        stage = "configuration"
        if not config.get("VAPID_PRIVATE_KEY") or not config.get("VAPID_CLAIMS_SUB"):
            emit("PUSH_SMOKE_ABORTED", stage=stage, reason="missing_vapid_configuration")
            return 2

        stage = "target_lookup"
        db = connect(config)
        with db.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, endpoint, p256dh, auth "
                "FROM push_subscriptions "
                "WHERE id = %s AND user_id = %s AND status = 'ACTIVE'",
                (args.subscription_id, args.user_id),
            )
            target = cur.fetchone()
        if target is None:
            emit("PUSH_SMOKE_ABORTED", stage=stage, reason="active_owned_target_not_found")
            return 2

        stage = "target_validation"
        endpoint, p256dh, auth = _validated_subscription({
            "endpoint": target["endpoint"],
            "keys": {"p256dh": target["p256dh"], "auth": target["auth"]},
        })
        emit("PUSH_TARGET_VALIDATED", user_id=args.user_id,
             subscription_id=args.subscription_id, targets=1)
        if not args.send:
            return 0

        stage = "provider_send"
        payload = {"event_type": "budget_alert", "deep_link": "/notifications"}
        # Do not let dependency output expose endpoint/key material.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            response = webpush(
                subscription_info={
                    "endpoint": endpoint,
                    "keys": {"p256dh": p256dh, "auth": auth},
                },
                data=json.dumps(payload, separators=(",", ":")),
                vapid_private_key=config["VAPID_PRIVATE_KEY"],
                vapid_claims={"sub": config["VAPID_CLAIMS_SUB"]},
                ttl=60,
                timeout=5,
            )
        status = getattr(response, "status_code", None)
        accepted = isinstance(status, int) and 200 <= status < 300
        emit("PUSH_PROVIDER_ACCEPTED" if accepted else "PUSH_PROVIDER_UNCONFIRMED",
             user_id=args.user_id, subscription_id=args.subscription_id,
             provider_http_status=status, payload=payload,
             device_receipt="PENDING_USER_CONFIRMATION")
        return 0 if accepted else 3
    except Exception as exc:
        response = getattr(exc, "response", None)
        emit("PUSH_SMOKE_FAILED", stage=stage,
             error_type=type(exc).__name__,
             provider_http_status=getattr(response, "status_code", None))
        return 1
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
