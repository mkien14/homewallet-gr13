"""Production admission: public onboarding or closed scope; retain household 1."""
from flask import current_app

from .db import get_db
from .errors import ApiError
from .household_policy import household_admitted, public_registration


def require_approved_subject(claims):
    if current_app.config.get("APP_ENV") != "production":
        return
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
    if household_id is None and public_registration(current_app.config):
        return  # Verified Cognito identity may create its profile and onboard.
    if not household_admitted(current_app.config, household_id):
        raise ApiError(403, "PRODUCTION_ACCESS_RESTRICTED", "Tài khoản chưa thuộc phạm vi được mở sử dụng. Hãy liên hệ quản trị viên.")
