import csv
import io
import secrets

import pymysql
from flask import Blueprint, g, jsonify, make_response, request

from .auth import require_auth
from .db import get_db
from .errors import ApiError
from .localization import SUPPORTED_LOCALES

bp = Blueprint("households", __name__, url_prefix="/api")


def membership(db, user_id):
    with db.cursor() as cur:
        cur.execute(
            "SELECT m.household_id, m.role, h.name, h.invite_code "
            "FROM household_members m JOIN households h ON h.id = m.household_id "
            "WHERE m.user_id = %s", (user_id,))
        return cur.fetchone()


def household_payload(m):
    if not m:
        return None
    out = {"id": m["household_id"], "name": m["name"], "role": m["role"]}
    if m["role"] == "owner":  
        out["invite_code"] = m["invite_code"]
    return out


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "BAD_REQUEST", "Nội dung JSON không hợp lệ")
    return data


def require_household(db, hid):
    """BR3: hộ lấy từ bảng thành viên. Hộ khác trả 404 để không lộ sự tồn tại."""
    m = membership(db, g.user["id"])
    if not m or m["household_id"] != hid:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
    return m


def require_owner(m):
    if m["role"] != "owner":
        raise ApiError(403, "FORBIDDEN", "Chỉ Chủ hộ được thực hiện thao tác này")


def new_code():
    return secrets.token_hex(4).upper()


def _iter_household_export_rows(db, hid):
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, name, owner_user_id, invite_code, currency, created_at "
            "FROM households WHERE id = %s",
            (hid,),
        )
        household = cur.fetchone()
        if not household:
            raise ApiError(404, "NOT_FOUND", "Không tìm thấy")

        cur.execute(
            "SELECT u.id, u.display_name, u.email, m.role, m.joined_at "
            "FROM household_members m JOIN users u ON u.id = m.user_id "
            "WHERE m.household_id = %s ORDER BY m.joined_at, u.id",
            (hid,),
        )
        members = cur.fetchall()

        cur.execute(
            "SELECT id, household_id, name, icon, is_fixed FROM categories "
            "WHERE household_id IS NULL OR household_id = %s ORDER BY id",
            (hid,),
        )
        categories = cur.fetchall()

        cur.execute(
            "SELECT id, household_id, member_id, receipt_id, occurred_on, merchant, "
            "total_amount, category_id, status, source, note, created_at "
            "FROM transactions WHERE household_id = %s ORDER BY occurred_on, id",
            (hid,),
        )
        transactions = cur.fetchall()

        cur.execute(
            "SELECT ti.id, ti.transaction_id, ti.description, ti.quantity, ti.unit_price, "
            "ti.amount, ti.category_id, ti.confidence "
            "FROM transaction_items ti "
            "JOIN transactions t ON t.id = ti.transaction_id "
            "WHERE t.household_id = %s ORDER BY ti.id",
            (hid,),
        )
        transaction_items = cur.fetchall()

        cur.execute(
            "SELECT id, household_id, uploader_id, s3_key, content_sha256, status, "
            "ocr_confidence, merchant_raw, error_code, created_at, processed_at "
            "FROM receipts WHERE household_id = %s ORDER BY created_at, id",
            (hid,),
        )
        receipts = cur.fetchall()

        cur.execute(
            "SELECT id, household_id, period, income_estimate, savings_goal, source, "
            "status FROM budgets WHERE household_id = %s ORDER BY period, id",
            (hid,),
        )
        budgets = cur.fetchall()

        cur.execute(
            "SELECT bl.budget_id, bl.category_id, bl.amount FROM budget_lines bl "
            "JOIN budgets b ON b.id = bl.budget_id WHERE b.household_id = %s "
            "ORDER BY bl.budget_id, bl.category_id",
            (hid,),
        )
        budget_lines = cur.fetchall()

        cur.execute(
            "SELECT id, household_id, name, category_id, due_day, expected_amount, "
            "remind_days_before, active FROM recurring_bills WHERE household_id = %s "
            "ORDER BY due_day, id",
            (hid,),
        )
        recurring_bills = cur.fetchall()

    return {
        "household": household,
        "members": members,
        "categories": categories,
        "transactions": transactions,
        "transaction_items": transaction_items,
        "receipts": receipts,
        "budgets": budgets,
        "budget_lines": budget_lines,
        "recurring_bills": recurring_bills,
    }


def _series_to_csv_bytes(rows, fieldnames):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8-sig")


def _delete_household_db(db, hid):
    with db.cursor() as cur:
        cur.execute("DELETE FROM household_members WHERE household_id = %s", (hid,))
        cur.execute("DELETE FROM recurring_bills WHERE household_id = %s", (hid,))
        cur.execute("DELETE FROM budget_lines WHERE budget_id IN (SELECT id FROM budgets WHERE household_id = %s)", (hid,))
        cur.execute("DELETE FROM budgets WHERE household_id = %s", (hid,))
        cur.execute("DELETE FROM transaction_items WHERE transaction_id IN (SELECT id FROM transactions WHERE household_id = %s)", (hid,))
        cur.execute("DELETE FROM transactions WHERE household_id = %s", (hid,))
        cur.execute("DELETE FROM receipts WHERE household_id = %s", (hid,))
        cur.execute("DELETE FROM categories WHERE household_id = %s", (hid,))
        cur.execute("DELETE FROM households WHERE id = %s", (hid,))
    db.commit()


@bp.get("/me")
@require_auth
def me():
    db = get_db()
    return jsonify(user=g.user, household=household_payload(membership(db, g.user["id"])))


@bp.patch("/me")
@require_auth
def update_me():
    data = json_body()
    if set(data) != {"preferred_locale"}:
        raise ApiError(422, "VALIDATION", "Chỉ hỗ trợ cập nhật preferred_locale")
    preferred_locale = data["preferred_locale"]
    if not isinstance(preferred_locale, str) or preferred_locale not in SUPPORTED_LOCALES:
        raise ApiError(422, "VALIDATION", "preferred_locale phải là vi hoặc en")

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "UPDATE users SET preferred_locale = %s WHERE id = %s",
                (preferred_locale, g.user["id"]),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    user = dict(g.user)
    user["preferred_locale"] = preferred_locale
    return jsonify(
        user=user,
        household=household_payload(membership(db, g.user["id"])),
    )


@bp.post("/households")
@require_auth
def create_household():
    db = get_db()
    name = str(json_body().get("name", "")).strip()
    if not 1 <= len(name) <= 100:
        raise ApiError(422, "VALIDATION", "Tên hộ phải từ 1 đến 100 ký tự")
    if membership(db, g.user["id"]):
        raise ApiError(409, "ALREADY_IN_HOUSEHOLD", "Bạn đã thuộc một hộ")

    for _ in range(5):
        try:
            with db.cursor() as cur:
                cur.execute("INSERT INTO households (name, owner_user_id, invite_code) VALUES (%s, %s, %s)",
                            (name, g.user["id"], new_code()))
                hid = cur.lastrowid
                cur.execute("INSERT INTO household_members (household_id, user_id, role) VALUES (%s, %s, 'owner')",
                            (hid, g.user["id"]))
            db.commit()
            return jsonify(household_payload(membership(db, g.user["id"]))), 201
        except pymysql.err.IntegrityError as e:
            db.rollback()
            if "invite_code" not in str(e):  
                raise ApiError(409, "ALREADY_IN_HOUSEHOLD", "Bạn đã thuộc một hộ")
    raise ApiError(500, "INTERNAL", "Không tạo được mã mời")


@bp.post("/households/join")
@require_auth
def join_household():
    db = get_db()
    code = str(json_body().get("invite_code", "")).strip().upper()
    if membership(db, g.user["id"]):
        raise ApiError(409, "ALREADY_IN_HOUSEHOLD", "Bạn đã thuộc một hộ")
    with db.cursor() as cur:
        cur.execute("SELECT id FROM households WHERE invite_code = %s", (code,))
        h = cur.fetchone()
    if not h:
        raise ApiError(404, "INVITE_NOT_FOUND", "Mã mời không đúng")
    try:
        with db.cursor() as cur:
            cur.execute("INSERT INTO household_members (household_id, user_id, role) VALUES (%s, %s, 'member')",
                        (h["id"], g.user["id"]))
        db.commit()
    except pymysql.err.IntegrityError:
        db.rollback()
        raise ApiError(409, "ALREADY_IN_HOUSEHOLD", "Bạn đã thuộc một hộ")
    return jsonify(household_payload(membership(db, g.user["id"])))


@bp.get("/households/<int:hid>/members")
@require_auth
def list_members(hid):
    db = get_db()
    require_household(db, hid)
    with db.cursor() as cur:
        cur.execute(
            "SELECT u.id, u.display_name, u.email, m.role, m.joined_at "
            "FROM household_members m JOIN users u ON u.id = m.user_id "
            "WHERE m.household_id = %s ORDER BY m.joined_at, u.id", (hid,))
        rows = cur.fetchall()
    for r in rows:
        r["joined_at"] = r["joined_at"].isoformat()
    return jsonify(members=rows)


@bp.delete("/households/<int:hid>/members/<int:uid>")
@require_auth
def remove_member(hid, uid):
    db = get_db()
    require_owner(require_household(db, hid))
    with db.cursor() as cur:
        cur.execute("SELECT role FROM household_members WHERE household_id = %s AND user_id = %s", (hid, uid))
        target = cur.fetchone()
        if not target:
            raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
        if target["role"] == "owner":
            raise ApiError(422, "VALIDATION", "Không thể xóa Chủ hộ")
        cur.execute("DELETE FROM household_members WHERE household_id = %s AND user_id = %s", (hid, uid))
    db.commit()
    return "", 204


@bp.post("/households/<int:hid>/invite-code")
@require_auth
def rotate_invite_code(hid):
    db = get_db()
    require_owner(require_household(db, hid))
    for _ in range(5):
        code = new_code()
        try:
            with db.cursor() as cur:
                cur.execute("UPDATE households SET invite_code = %s WHERE id = %s", (code, hid))
            db.commit()
            return jsonify(invite_code=code)
        except pymysql.err.IntegrityError:
            db.rollback()
    raise ApiError(500, "INTERNAL", "Không tạo được mã mời")


@bp.get("/households/<int:hid>/export.csv")
@require_auth
def export_household_csv(hid):
    db = get_db()
    require_owner(require_household(db, hid))

    export = _iter_household_export_rows(db, hid)
    output = io.StringIO(newline="")
    for section_name, rows in (
        ("households", [export["household"]]),
        ("members", export["members"]),
        ("categories", export["categories"]),
        ("transactions", export["transactions"]),
        ("transaction_items", export["transaction_items"]),
        ("receipts", export["receipts"]),
        ("budgets", export["budgets"]),
        ("budget_lines", export["budget_lines"]),
        ("recurring_bills", export["recurring_bills"]),
    ):
        if not rows:
            continue
        output.write(f"[{section_name}]\n")
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: (value.isoformat() if hasattr(value, "isoformat") else value)
                for key, value in row.items()
            })
        output.write("\n")

    response = make_response(output.getvalue().encode("utf-8-sig"))
    response.headers["Content-Type"] = "text/csv; charset=utf-8-sig"
    response.headers["Content-Disposition"] = f'attachment; filename="household-{hid}.csv"'
    return response


@bp.post("/households/<int:hid>/delete")
@require_auth
def delete_household(hid):
    db = get_db()
    require_owner(require_household(db, hid))
    data = json_body()
    if data.get("confirm") is not True:
        raise ApiError(400, "CONFIRMATION_REQUIRED", "Cần xác nhận xóa vĩnh viễn hộ này")
    if data.get("household_id") not in (None, hid):
        raise ApiError(422, "VALIDATION", "household_id không khớp")

    with db.cursor() as cur:
        cur.execute(
            "SELECT s3_key FROM receipts WHERE household_id = %s AND s3_key IS NOT NULL ORDER BY id",
            (hid,),
        )
        receipt_keys = [row["s3_key"] for row in cur.fetchall()]

    try:
        from . import storage
        storage.delete_s3_objects(receipt_keys)
    except ApiError as exc:
        raise ApiError(
            502,
            "S3_DELETE_FAILED",
            "Xóa S3 thất bại; hộ chưa bị xóa. Kiểm tra bucket/versioning và thử lại sau.",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        raise ApiError(
            502,
            "S3_DELETE_FAILED",
            f"Không thể dọn sạch S3: {exc}",
        ) from exc

    try:
        _delete_household_db(db, hid)
    except Exception as exc:
        db.rollback()
        raise ApiError(
            500,
            "HOUSEHOLD_DELETE_PARTIAL",
            "Xóa S3 đã hoàn tất nhưng xóa DB thất bại. Hộ chưa bị xóa hoàn toàn; cần retry hoặc kiểm tra trạng thái dữ liệu.",
        ) from exc

    return jsonify({
        "deleted": True,
        "household_id": hid,
        "s3_deleted": len(receipt_keys),
        "status": "deleted",
    })
