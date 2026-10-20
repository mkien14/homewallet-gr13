import math
import json
import uuid
from datetime import date, timedelta

from flask import Blueprint, current_app, g, jsonify, request

from . import storage
from .auth import require_auth
from .cache import invalidate_dashboard
from .db import get_db
from .errors import ApiError
from .households import json_body, membership

bp = Blueprint("receipts", __name__, url_prefix="/api")

ALLOWED_TYPES = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}


def serialize(r):
    return {
        "id": r["id"],
        "status": r["status"],
        "error_code": r["error_code"],
        "created_at": r["created_at"].isoformat(),
        "processed_at": r["processed_at"].isoformat() if r["processed_at"] else None,
    }


def decode_warnings(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = json.loads(value)
    return value


def _parse_confirm_body(data):
    amount = data.get("total_amount")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise ApiError(422, "VALIDATION", "Tổng tiền phải là số nguyên dương")

    occurred_on = data.get("occurred_on")
    if not isinstance(occurred_on, str):
        raise ApiError(422, "VALIDATION", "Ngày giao dịch không hợp lệ")
    try:
        parsed_date = date.fromisoformat(occurred_on)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION", "Ngày giao dịch không hợp lệ") from exc
    if parsed_date.isoformat() != occurred_on:
        raise ApiError(422, "VALIDATION", "Ngày giao dịch không hợp lệ")
    if parsed_date > date.today() + timedelta(days=1):
        raise ApiError(422, "VALIDATION", "Ngày giao dịch không được ở quá một ngày trong tương lai")

    merchant = data.get("merchant")
    if merchant is not None and not isinstance(merchant, str):
        raise ApiError(422, "VALIDATION", "Tên cửa hàng không hợp lệ")

    category_id = data.get("category_id")
    if category_id is not None and (
        not isinstance(category_id, int) or isinstance(category_id, bool)
    ):
        raise ApiError(422, "VALIDATION", "Danh mục không hợp lệ")

    items = data.get("items")
    if items is not None and not isinstance(items, list):
        raise ApiError(422, "VALIDATION", "Danh sách mặt hàng không hợp lệ")
    for item in items or []:
        if not isinstance(item, dict):
            raise ApiError(422, "VALIDATION", "Mặt hàng không hợp lệ")
        item_amount = item.get("amount")
        if not isinstance(item_amount, int) or isinstance(item_amount, bool) or item_amount <= 0:
            raise ApiError(422, "VALIDATION", "Tiền mặt hàng phải là số nguyên dương")
        quantity = item.get("quantity")
        if quantity is not None and (
            not isinstance(quantity, (int, float)) or isinstance(quantity, bool)
            or (isinstance(quantity, float) and not math.isfinite(quantity))
            or quantity <= 0 or quantity > 9_999_999.999
        ):
            raise ApiError(422, "VALIDATION", "Số lượng mặt hàng không hợp lệ")
        unit_price = item.get("unit_price")
        if unit_price is not None and (
            not isinstance(unit_price, int) or isinstance(unit_price, bool) or unit_price < 0
        ):
            raise ApiError(422, "VALIDATION", "Đơn giá mặt hàng không hợp lệ")
        description = item.get("description")
        if description is not None and not isinstance(description, str):
            raise ApiError(422, "VALIDATION", "Mô tả mặt hàng không hợp lệ")
        item_category = item.get("category_id")
        if item_category is not None and (
            not isinstance(item_category, int) or isinstance(item_category, bool)
        ):
            raise ApiError(422, "VALIDATION", "Danh mục mặt hàng không hợp lệ")

    return {
        "occurred_on": parsed_date.isoformat(),
        "total_amount": amount,
        "merchant": merchant,
        "category_id": category_id,
        "items": items,
    }


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


def _transaction_payload(db, transaction_id):
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, occurred_on, merchant, total_amount, category_id, status "
            "FROM transactions WHERE id = %s",
            (transaction_id,),
        )
        transaction = cur.fetchone()
        if not transaction:
            raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
        cur.execute(
            "SELECT description, quantity, amount, category_id "
            "FROM transaction_items WHERE transaction_id = %s ORDER BY id",
            (transaction_id,),
        )
        items = cur.fetchall()
    transaction["occurred_on"] = transaction["occurred_on"].isoformat()
    transaction["items"] = _serialize_items(items)
    return transaction


def _serialize_items(items):
    for item in items:
        if item["quantity"] is not None:
            item["quantity"] = float(item["quantity"])
    return items


@bp.post("/receipts")
@require_auth
def create_receipt():
    cfg = current_app.config
    db = get_db()
    m = membership(db, g.user["id"])
    if not m:
        raise ApiError(403, "NO_HOUSEHOLD", "Bạn cần thuộc một hộ để tải hóa đơn")

    data = json_body()
    ctype = str(data.get("content_type", "")).lower()
    size = data.get("size")
    if ctype not in ALLOWED_TYPES:
        raise ApiError(422, "VALIDATION", "Chỉ nhận ảnh JPEG, PNG hoặc PDF")
    if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= cfg["MAX_RECEIPT_BYTES"]:
        mb = cfg["MAX_RECEIPT_BYTES"] // (1024 * 1024)
        raise ApiError(422, "VALIDATION", f"Kích thước tệp phải từ 1 byte đến {mb} MB")

    key = f"receipts/uploads/{m['household_id']}/{uuid.uuid4().hex}.{ALLOWED_TYPES[ctype]}"
    upload = storage.presign_upload(key, ctype)  

    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO receipts (household_id, uploader_id, s3_key, status) "
            "VALUES (%s, %s, %s, 'UPLOADING')",
            (m["household_id"], g.user["id"], key),
        )
        rid = cur.lastrowid
    db.commit()
    return jsonify(receipt={"id": rid, "status": "UPLOADING"}, upload=upload), 201


@bp.get("/receipts/<int:rid>")
@require_auth
def get_receipt(rid):
    db = get_db()
    m = membership(db, g.user["id"])
    if not m:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, s3_key, status, error_code, warnings, created_at, processed_at "
            "FROM receipts WHERE id = %s AND household_id = %s",
            (rid, m["household_id"]),
        )
        row = cur.fetchone()
    if not row:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")  

    if row["status"] == "UPLOADING" and storage.object_exists(row["s3_key"]):
        with db.cursor() as cur:
            cur.execute("UPDATE receipts SET status = 'UPLOADED' WHERE id = %s AND status = 'UPLOADING'", (rid,))
        db.commit()
        row["status"] = "UPLOADED"
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, occurred_on, merchant, total_amount, category_id "
            "FROM transactions WHERE receipt_id = %s",
            (rid,),
        )
        draft = cur.fetchone()
    if draft:
        with db.cursor() as cur:
            cur.execute(
                "SELECT description, quantity, amount, category_id "
                "FROM transaction_items WHERE transaction_id = %s ORDER BY id",
                (draft["id"],),
            )
            draft["items"] = _serialize_items(cur.fetchall())
        draft["transaction_id"] = draft.pop("id")
        draft["occurred_on"] = draft["occurred_on"].isoformat()
    result = serialize(row)
    result.update(
        warnings=decode_warnings(row["warnings"]),
        image_url=storage.presign_download(row["s3_key"]),
        created_at=row["created_at"].isoformat(),
        draft=draft,
    )
    return jsonify(result)


@bp.get("/receipts")
@require_auth
def list_receipts():
    db = get_db()
    m = membership(db, g.user["id"])
    if not m:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")

    status = request.args.get("status")
    limit_value = request.args.get("limit", "50")
    cursor_value = request.args.get("cursor")
    try:
        limit = int(limit_value)
        cursor_id = int(cursor_value) if cursor_value else None
    except ValueError as exc:
        raise ApiError(422, "VALIDATION", "Tham số phân trang không hợp lệ") from exc
    if not 1 <= limit <= 100 or (cursor_id is not None and cursor_id <= 0):
        raise ApiError(422, "VALIDATION", "Tham số phân trang không hợp lệ")

    statuses = {"UPLOADING", "UPLOADED", "PROCESSING", "DRAFT_READY",
                "NEEDS_REVIEW", "CONFIRMED", "FAILED"}
    if status and status not in statuses:
        raise ApiError(422, "VALIDATION", "Trạng thái hóa đơn không hợp lệ")

    query = (
        "SELECT r.id, r.status, COALESCE(t.merchant, r.merchant_raw) AS merchant, "
        "r.created_at, r.warnings, "
        "t.total_amount, t.occurred_on "
        "FROM receipts r LEFT JOIN transactions t ON t.receipt_id = r.id "
        "WHERE r.household_id = %s"
    )
    params = [m["household_id"]]
    if status:
        query += " AND r.status = %s"
        params.append(status)
    if cursor_id is not None:
        query += " AND r.id < %s"
        params.append(cursor_id)
    query += " ORDER BY r.id DESC LIMIT %s"
    params.append(limit + 1)
    with db.cursor() as cur:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]
    items = []
    for row in rows:
        items.append({
            "id": row["id"],
            "status": row["status"],
            "merchant": row["merchant"],
            "total_amount": row["total_amount"],
            "occurred_on": row["occurred_on"].isoformat() if row["occurred_on"] else None,
            "created_at": row["created_at"].isoformat(),
            "warnings": decode_warnings(row["warnings"]),
        })
    next_cursor = str(rows[-1]["id"]) if has_more and rows else None
    return jsonify(items=items, next_cursor=next_cursor)


@bp.post("/receipts/<int:rid>/confirm")
@require_auth
def confirm_receipt(rid):
    body = _parse_confirm_body(json_body())
    db = get_db()
    m = membership(db, g.user["id"])
    if not m:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")

    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT id, household_id, status FROM receipts "
                "WHERE id = %s AND household_id = %s FOR UPDATE",
                (rid, m["household_id"]),
            )
            receipt = cur.fetchone()
            if not receipt:
                raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
            if receipt["status"] == "CONFIRMED":
                raise ApiError(409, "ALREADY_CONFIRMED", "Hóa đơn đã được xác nhận")
            if receipt["status"] not in ("DRAFT_READY", "NEEDS_REVIEW"):
                raise ApiError(409, "DRAFT_NOT_READY", "Hóa đơn chưa có bản nháp để xác nhận")

            cur.execute(
                "SELECT id, status FROM transactions WHERE receipt_id = %s FOR UPDATE",
                (rid,),
            )
            transaction = cur.fetchone()
            if not transaction or transaction["status"] != "DRAFT":
                raise ApiError(409, "DRAFT_NOT_FOUND", "Không tìm thấy bản nháp")

            _validate_category(db, body["category_id"], m["household_id"])
            for item in body["items"] or []:
                _validate_category(db, item.get("category_id"), m["household_id"])

            cur.execute(
                "UPDATE transactions SET occurred_on = %s, merchant = %s, total_amount = %s, "
                "category_id = %s, status = 'CONFIRMED' WHERE id = %s AND status = 'DRAFT'",
                (
                    body["occurred_on"],
                    body["merchant"],
                    body["total_amount"],
                    body["category_id"],
                    transaction["id"],
                ),
            )
            if body["items"] is not None:
                cur.execute(
                    "DELETE FROM transaction_items WHERE transaction_id = %s",
                    (transaction["id"],),
                )
                if body["items"]:
                    cur.executemany(
                        "INSERT INTO transaction_items "
                        "(transaction_id, description, quantity, unit_price, amount, category_id) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        [
                            (
                                transaction["id"],
                                item.get("description"),
                                item.get("quantity"),
                                item.get("unit_price"),
                                item["amount"],
                                item.get("category_id"),
                            )
                            for item in body["items"]
                        ],
                    )
            cur.execute(
                "UPDATE receipts SET status = 'CONFIRMED' WHERE id = %s",
                (rid,),
            )
            result = _transaction_payload(db, transaction["id"])
        db.commit()
    except Exception:
        db.rollback()
        raise

    invalidate_dashboard(m["household_id"])
    return jsonify(transaction=result)