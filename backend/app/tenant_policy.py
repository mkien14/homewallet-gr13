"""Closed production rollout: admit only explicitly approved current households."""
from flask import current_app

from .db import get_db
from .errors import ApiError


def require_approved_subject(claims):
    if current_app.config.get("APP_ENV") != "production":
        return
    allowed = current_app.config.get("PRODUCTION_ALLOWED_HOUSEHOLD_IDS", set())
    # Resolve membership before get_or_create_user: rejected identities must not
    # create users or update data belonging to retained household 1.
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT m.household_id FROM household_members m "
            "JOIN users u ON u.id = m.user_id WHERE u.cognito_sub = %s",
            (claims["sub"],),
        )
        membership = cursor.fetchone()
    db.commit()
    household_id = membership["household_id"] if membership else None
    if household_id == 1 or household_id not in allowed:
        raise ApiError(403, "PRODUCTION_ACCESS_RESTRICTED", "Tài khoản chưa thuộc phạm vi được mở sử dụng. Hãy liên hệ quản trị viên.")
