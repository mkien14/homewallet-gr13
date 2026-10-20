import re
from datetime import date, timedelta

import pymysql
from flask import Blueprint, g, jsonify, request

from .auth import require_auth
from .cache import invalidate_dashboard
from .db import get_db
from .errors import ApiError
from .households import json_body, membership

bp = Blueprint("transactions", __name__, url_prefix="/api")
TRANSACTION_FIELDS = (
    "id, household_id, member_id, receipt_id, occurred_on, merchant, total_amount, "
    "category_id, status, source, note, created_at"
)


def _positive_int(value, message):
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ApiError(422, "VALIDATION", message)
    return value


def _parse_date(value):
    if not isinstance(value, str):
        raise ApiError(422, "VALIDATION", "Ngày giao dịch không hợp lệ")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION", "Ngày giao dịch không hợp lệ") from exc
    if parsed.isoformat() != value or parsed > date.today() + timedelta(days=1):
        raise ApiError(422, "VALIDATION", "Ngày giao dịch không hợp lệ")
    return parsed.isoformat()


def _validate_category(db, category_id, household_id):
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


def _serialize(row):
    for key in ("occurred_on", "created_at"):
        if row.get(key) is not None:
            row[key] = row[key].isoformat()
    return row


def _get_transaction(db, transaction_id, household_id, *, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    with db.cursor() as cur:
        cur.execute(
            f"SELECT {TRANSACTION_FIELDS} FROM transactions "
            f"WHERE id = %s AND household_id = %s{suffix}",
            (transaction_id, household_id),
        )
        row = cur.fetchone()
    if not row:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
    return row


def _body_values(data, *, partial=False):
    allowed = {"occurred_on", "total_amount", "category_id", "note"}
    if set(data) - allowed:
        raise ApiError(422, "VALIDATION", "Trường dữ liệu không được hỗ trợ")
    if not partial and not {"occurred_on", "total_amount", "category_id"} <= set(data):
        raise ApiError(422, "VALIDATION", "Thiếu thông tin giao dịch")
    values = {}
    if "occurred_on" in data:
        values["occurred_on"] = _parse_date(data["occurred_on"])
    if "total_amount" in data:
        values["total_amount"] = _positive_int(
            data["total_amount"], "Tổng tiền phải là số nguyên dương"
        )
    if "category_id" in data:
        category_id = data["category_id"]
        if category_id is not None:
            _positive_int(category_id, "Danh mục không hợp lệ")
        values["category_id"] = category_id
    if "note" in data:
        note = data["note"]
        if note is not None and (
            not isinstance(note, str) or len(note) > 500
        ):
            raise ApiError(422, "VALIDATION", "Ghi chú tối đa 500 ký tự")
        values["note"] = note
    if partial and not values:
        raise ApiError(422, "VALIDATION", "Không có trường nào để cập nhật")
    return values


def _load_idempotent(db, household_id, key):
    with db.cursor() as cur:
        cur.execute(
            f"SELECT {TRANSACTION_FIELDS} FROM transactions "
            "WHERE household_id = %s AND idempotency_key = %s",
            (household_id, key),
        )
        row = cur.fetchone()
    if not row:
        return None
    return _serialize(row)


@bp.get("/categories")
@require_auth
def list_categories():
    db = get_db()
    m = membership(db, g.user["id"])
    if not m:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, name, icon, is_fixed FROM categories "
            "WHERE household_id IS NULL OR household_id = %s ORDER BY id",
            (m["household_id"],),
        )
        categories = cur.fetchall()
    for category in categories:
        category["is_fixed"] = bool(category["is_fixed"])
    return jsonify(categories=categories)


@bp.post("/transactions")
@require_auth
def create_transaction():
    key = request.headers.get("Idempotency-Key", "")
    if not key or len(key) > 64 or not re.fullmatch(r"[\x21-\x7e]+", key):
        raise ApiError(422, "VALIDATION", "Idempotency-Key không hợp lệ")
    values = _body_values(json_body())

    db = get_db()
    m = membership(db, g.user["id"])
    if not m:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
    _validate_category(db, values["category_id"], m["household_id"])

    existing = _load_idempotent(db, m["household_id"], key)
    if existing:
        return jsonify(transaction=existing), 200

    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO transactions "
                "(household_id, member_id, occurred_on, total_amount, category_id, note, "
                "status, source, idempotency_key) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'CONFIRMED', 'MANUAL', %s)",
                (
                    m["household_id"],
                    g.user["id"],
                    values["occurred_on"],
                    values["total_amount"],
                    values["category_id"],
                    values.get("note"),
                    key,
                ),
            )
            transaction_id = cur.lastrowid
        db.commit()
    except pymysql.err.IntegrityError as exc:
        db.rollback()
        if exc.args and exc.args[0] == 1062:
            existing = _load_idempotent(db, m["household_id"], key)
            if existing:
                return jsonify(transaction=existing), 200
        raise
    except Exception:
        db.rollback()
        raise

    result = _serialize(
        _get_transaction(db, transaction_id, m["household_id"])
    )
    invalidate_dashboard(m["household_id"])
    return jsonify(transaction=result), 201


@bp.get("/transactions")
@require_auth
def list_transactions():
    db = get_db()
    m = membership(db, g.user["id"])
    if not m:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")

    period = request.args.get("period", date.today().strftime("%Y-%m"))
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        raise ApiError(422, "VALIDATION", "Kỳ giao dịch phải có dạng YYYY-MM")
    period_start = date.fromisoformat(f"{period}-01")
    next_period = (
        date(period_start.year + 1, 1, 1)
        if period_start.month == 12
        else date(period_start.year, period_start.month + 1, 1)
    )

    try:
        limit = int(request.args.get("limit", "50"))
        cursor_id = int(request.args["cursor"]) if request.args.get("cursor") else None
        member_id = int(request.args["member_id"]) if request.args.get("member_id") else None
        category_id = (
            int(request.args["category_id"]) if request.args.get("category_id") else None
        )
    except ValueError as exc:
        raise ApiError(422, "VALIDATION", "Tham số lọc không hợp lệ") from exc
    if (
        not 1 <= limit <= 100
        or (cursor_id is not None and cursor_id <= 0)
        or (member_id is not None and member_id <= 0)
        or (category_id is not None and category_id <= 0)
    ):
        raise ApiError(422, "VALIDATION", "Tham số lọc không hợp lệ")

    query = (
        f"SELECT {TRANSACTION_FIELDS} FROM transactions "
        "WHERE household_id = %s AND occurred_on >= %s AND occurred_on < %s"
    )
    params = [m["household_id"], period_start, next_period]
    if member_id is not None:
        query += " AND member_id = %s"
        params.append(member_id)
    if category_id is not None:
        query += " AND category_id = %s"
        params.append(category_id)
    if cursor_id is not None:
        query += " AND id < %s"
        params.append(cursor_id)
    query += " ORDER BY id DESC LIMIT %s"
    params.append(limit + 1)
    with db.cursor() as cur:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

    has_more = len(rows) > limit
    rows = [_serialize(row) for row in rows[:limit]]
    next_cursor = str(rows[-1]["id"]) if has_more and rows else None
    return jsonify(items=rows, next_cursor=next_cursor)


@bp.patch("/transactions/<int:transaction_id>")
@require_auth
def update_transaction(transaction_id):
    values = _body_values(json_body(), partial=True)
    db = get_db()
    m = membership(db, g.user["id"])
    if not m:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")

    try:
        row = _get_transaction(
            db, transaction_id, m["household_id"], lock=True
        )
        if row["member_id"] != g.user["id"] and m["role"] != "owner":
            raise ApiError(403, "FORBIDDEN", "Bạn không có quyền sửa giao dịch này")
        if row["receipt_id"] is not None and row["status"] == "DRAFT":
            raise ApiError(409, "DRAFT_REQUIRES_RECEIPT_CONFIRMATION",
                           "Hãy xác nhận bản nháp qua hóa đơn")
        if "category_id" in values:
            _validate_category(db, values["category_id"], m["household_id"])

        assignments = ", ".join(f"{field} = %s" for field in values)
        with db.cursor() as cur:
            cur.execute(
                f"UPDATE transactions SET {assignments} WHERE id = %s",
                (*values.values(), transaction_id),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    result = _serialize(_get_transaction(db, transaction_id, m["household_id"]))
    invalidate_dashboard(m["household_id"])
    return jsonify(transaction=result)


@bp.delete("/transactions/<int:transaction_id>")
@require_auth
def delete_transaction(transaction_id):
    db = get_db()
    m = membership(db, g.user["id"])
    if not m:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")

    try:
        row = _get_transaction(
            db, transaction_id, m["household_id"], lock=True
        )
        if row["member_id"] != g.user["id"] and m["role"] != "owner":
            raise ApiError(403, "FORBIDDEN", "Bạn không có quyền xóa giao dịch này")
        if row["receipt_id"] is not None and row["status"] == "DRAFT":
            raise ApiError(409, "DRAFT_REQUIRES_RECEIPT_CONFIRMATION",
                           "Hãy xử lý bản nháp qua hóa đơn")
        with db.cursor() as cur:
            cur.execute("DELETE FROM transactions WHERE id = %s", (transaction_id,))
        db.commit()
    except Exception:
        db.rollback()
        raise

    invalidate_dashboard(m["household_id"])
    return "", 204
