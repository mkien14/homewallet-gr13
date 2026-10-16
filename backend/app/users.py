from flask import current_app

from .cognito_profile import fetch_email
from .db import get_db
from .errors import ApiError

_SELECT = "SELECT id, email, display_name FROM users WHERE cognito_sub = %s"


def get_or_create_user(claims, token):
    db = get_db()
    sub = claims["sub"]
    with db.cursor() as cur:
        cur.execute(_SELECT, (sub,))
        row = cur.fetchone()
    db.commit()  
    if row:
        return row

    try:
        email = fetch_email(token, claims, current_app.config)
    except Exception:
        current_app.logger.exception("không lấy được hồ sơ từ Cognito")
        email = None
    if not email:
        raise ApiError(502, "PROFILE_UNAVAILABLE", "Không lấy được hồ sơ người dùng")

    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO users (cognito_sub, email, display_name) VALUES (%s, %s, %s) AS new "
            "ON DUPLICATE KEY UPDATE email = new.email",
            (sub, email, email.split("@")[0]),
        )
        cur.execute(_SELECT, (sub,))
        row = cur.fetchone()
    db.commit()
    return row