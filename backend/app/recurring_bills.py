from flask import Blueprint, g, jsonify

from .auth import require_auth
from .db import get_db
from .errors import ApiError
from .households import json_body, membership, require_owner

bp = Blueprint("recurring_bills", __name__, url_prefix="/api")
FIELDS = (
    "id, household_id, name, category_id, due_day, expected_amount, "
    "remind_days_before, active"
)
ALLOWED_FIELDS = {
    "name",
    "category_id",
    "due_day",
    "expected_amount",
    "remind_days_before",
    "active",
}


def _household(db):
    household = membership(db, g.user["id"])
    if not household:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
    return household


def _bill_payload(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "category_id": row["category_id"],
        "due_day": row["due_day"],
        "expected_amount": (
            int(row["expected_amount"]) if row["expected_amount"] is not None else None
        ),
        "remind_days_before": row["remind_days_before"],
        "active": bool(row["active"]),
    }


def _parse_fields(data, *, partial=False):
    unknown = set(data) - ALLOWED_FIELDS
    if unknown:
        raise ApiError(422, "VALIDATION", "Trường hóa đơn định kỳ không được hỗ trợ")
    required = {"name", "due_day"}
    if not partial and not required <= set(data):
        raise ApiError(422, "VALIDATION", "Thiếu tên hóa đơn hoặc ngày đến hạn")
    if partial and not data:
        raise ApiError(422, "VALIDATION", "Cần ít nhất một trường để cập nhật")

    values = {}
    if "name" in data:
        name = data["name"]
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise ApiError(422, "VALIDATION", "Tên hóa đơn phải từ 1 đến 100 ký tự")
        values["name"] = name.strip()
    if "category_id" in data:
        category_id = data["category_id"]
        if category_id is not None and (
            not isinstance(category_id, int)
            or isinstance(category_id, bool)
            or category_id <= 0
        ):
            raise ApiError(422, "VALIDATION", "Danh mục không hợp lệ")
        values["category_id"] = category_id
    if "due_day" in data:
        due_day = data["due_day"]
        if (
            not isinstance(due_day, int)
            or isinstance(due_day, bool)
            or not 1 <= due_day <= 31
        ):
            raise ApiError(422, "VALIDATION", "due_day phải từ 1 đến 31")
        values["due_day"] = due_day
    if "expected_amount" in data:
        amount = data["expected_amount"]
        if amount is not None and (
            not isinstance(amount, int) or isinstance(amount, bool) or amount < 0
        ):
            raise ApiError(422, "VALIDATION", "expected_amount phải là số nguyên không âm")
        values["expected_amount"] = amount
    if "remind_days_before" in data:
        days = data["remind_days_before"]
        if not isinstance(days, int) or isinstance(days, bool) or not 0 <= days <= 30:
            raise ApiError(422, "VALIDATION", "remind_days_before phải từ 0 đến 30")
        values["remind_days_before"] = days
    if "active" in data:
        if not isinstance(data["active"], bool):
            raise ApiError(422, "VALIDATION", "active phải là boolean")
        values["active"] = data["active"]
    return values


def _validate_category(db, household_id, category_id):
    if category_id is None:
        return
    with db.cursor() as cur:
        cur.execute(
            "SELECT id FROM categories WHERE id = %s "
            "AND (household_id IS NULL OR household_id = %s)",
            (category_id, household_id),
        )
        if not cur.fetchone():
            raise ApiError(422, "VALIDATION", "Danh mục không hợp lệ")


def _get_bill(db, household_id, bill_id):
    with db.cursor() as cur:
        cur.execute(
            f"SELECT {FIELDS} FROM recurring_bills "
            "WHERE household_id = %s AND id = %s",
            (household_id, bill_id),
        )
        return cur.fetchone()


@bp.get("/recurring-bills")
@require_auth
def list_recurring_bills():
    db = get_db()
    household = _household(db)
    with db.cursor() as cur:
        cur.execute(
            f"SELECT {FIELDS} FROM recurring_bills "
            "WHERE household_id = %s ORDER BY due_day, id",
            (household["household_id"],),
        )
        items = [_bill_payload(row) for row in cur.fetchall()]
    return jsonify(items=items)


@bp.post("/recurring-bills")
@require_auth
def create_recurring_bill():
    db = get_db()
    household = _household(db)
    require_owner(household)
    data = json_body()
    values = _parse_fields(data)
    values.setdefault("category_id", None)
    values.setdefault("expected_amount", None)
    values.setdefault("remind_days_before", 3)
    values.setdefault("active", True)
    _validate_category(db, household["household_id"], values["category_id"])
    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO recurring_bills "
                "(household_id, name, category_id, due_day, expected_amount, "
                "remind_days_before, active) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    household["household_id"],
                    values["name"],
                    values["category_id"],
                    values["due_day"],
                    values["expected_amount"],
                    values["remind_days_before"],
                    values["active"],
                ),
            )
            bill_id = cur.lastrowid
        db.commit()
    except Exception:
        db.rollback()
        raise
    return jsonify(bill=_bill_payload(_get_bill(db, household["household_id"], bill_id))), 201


@bp.patch("/recurring-bills/<int:bill_id>")
@require_auth
def update_recurring_bill(bill_id):
    db = get_db()
    household = _household(db)
    require_owner(household)
    values = _parse_fields(json_body(), partial=True)
    if "category_id" in values:
        _validate_category(db, household["household_id"], values["category_id"])

    try:
        bill = _get_bill(db, household["household_id"], bill_id)
        if not bill:
            raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
        assignments = ", ".join(f"{field} = %s" for field in values)
        with db.cursor() as cur:
            cur.execute(
                f"UPDATE recurring_bills SET {assignments} "
                "WHERE id = %s AND household_id = %s",
                (*values.values(), bill_id, household["household_id"]),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return jsonify(bill=_bill_payload(_get_bill(db, household["household_id"], bill_id)))


@bp.delete("/recurring-bills/<int:bill_id>")
@require_auth
def delete_recurring_bill(bill_id):
    db = get_db()
    household = _household(db)
    require_owner(household)
    with db.cursor() as cur:
        cur.execute(
            "DELETE FROM recurring_bills WHERE id = %s AND household_id = %s",
            (bill_id, household["household_id"]),
        )
        deleted = cur.rowcount
    if not deleted:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
    db.commit()
    return "", 204
