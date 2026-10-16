import secrets

import pymysql
from flask import Blueprint, g, jsonify, request

from .auth import require_auth
from .db import get_db
from .errors import ApiError

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


@bp.get("/me")
@require_auth
def me():
    db = get_db()
    return jsonify(user=g.user, household=household_payload(membership(db, g.user["id"])))


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