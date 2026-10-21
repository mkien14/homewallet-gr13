import re
from datetime import date

from flask import Blueprint, g, jsonify, request

from .auth import require_auth
from .db import get_db
from .errors import ApiError
from .households import membership

bp = Blueprint("dashboard", __name__, url_prefix="/api")


def _period_bounds(period):
    if not isinstance(period, str) or not re.fullmatch(
        r"\d{4}-(0[1-9]|1[0-2])", period
    ):
        raise ApiError(422, "VALIDATION", "Kỳ báo cáo phải có dạng YYYY-MM")
    try:
        start = date.fromisoformat(f"{period}-01")
        end = (
            date(start.year + 1, 1, 1)
            if start.month == 12
            else date(start.year, start.month + 1, 1)
        )
    except ValueError as exc:
        raise ApiError(422, "VALIDATION", "Kỳ báo cáo không hợp lệ") from exc
    return start, end


@bp.get("/dashboard")
@require_auth
def get_dashboard():
    period = request.args.get("period")
    start, end = _period_bounds(period)

    db = get_db()
    household = membership(db, g.user["id"])
    if not household:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
    household_id = household["household_id"]

    with db.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(total_amount), 0) AS total "
            "FROM transactions "
            "WHERE household_id = %s AND status = 'CONFIRMED' "
            "AND occurred_on >= %s AND occurred_on < %s",
            (household_id, start, end),
        )
        total = int(cur.fetchone()["total"])

        cur.execute(
            "SELECT c.id AS category_id, c.name, SUM(t.total_amount) AS amount "
            "FROM transactions t LEFT JOIN categories c ON c.id = t.category_id "
            "WHERE t.household_id = %s AND t.status = 'CONFIRMED' "
            "AND t.occurred_on >= %s AND t.occurred_on < %s "
            "GROUP BY c.id, c.name ORDER BY c.id",
            (household_id, start, end),
        )
        by_category = [
            {
                "category_id": row["category_id"],
                "name": row["name"],
                "amount": int(row["amount"]),
            }
            for row in cur.fetchall()
        ]

        cur.execute(
            "SELECT u.id AS user_id, u.display_name, SUM(t.total_amount) AS amount "
            "FROM transactions t JOIN users u ON u.id = t.member_id "
            "WHERE t.household_id = %s AND t.status = 'CONFIRMED' "
            "AND t.occurred_on >= %s AND t.occurred_on < %s "
            "GROUP BY u.id, u.display_name ORDER BY u.id",
            (household_id, start, end),
        )
        by_member = [
            {
                "user_id": row["user_id"],
                "display_name": row["display_name"],
                "amount": int(row["amount"]),
            }
            for row in cur.fetchall()
        ]

        cur.execute(
            "SELECT DATE_SUB(t.occurred_on, INTERVAL WEEKDAY(t.occurred_on) DAY) "
            "AS week_start, SUM(t.total_amount) AS amount "
            "FROM transactions t "
            "WHERE t.household_id = %s AND t.status = 'CONFIRMED' "
            "AND t.occurred_on >= %s AND t.occurred_on < %s "
            "GROUP BY week_start ORDER BY week_start",
            (household_id, start, end),
        )
        by_week = [
            {
                "week_start": row["week_start"].isoformat(),
                "amount": int(row["amount"]),
            }
            for row in cur.fetchall()
        ]

    return jsonify(
        period=period,
        total=total,
        by_category=by_category,
        by_member=by_member,
        by_week=by_week,
    )
