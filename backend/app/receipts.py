import uuid

from flask import Blueprint, current_app, g, jsonify

from . import storage
from .auth import require_auth
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
        cur.execute("SELECT id, s3_key, status, error_code, created_at, processed_at "
                    "FROM receipts WHERE id = %s AND household_id = %s", (rid, m["household_id"]))
        row = cur.fetchone()
    if not row:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")  

    if row["status"] == "UPLOADING" and storage.object_exists(row["s3_key"]):
        with db.cursor() as cur:
            cur.execute("UPDATE receipts SET status = 'UPLOADED' WHERE id = %s AND status = 'UPLOADING'", (rid,))
        db.commit()
        row["status"] = "UPLOADED"
    return jsonify(serialize(row))