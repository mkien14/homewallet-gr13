from datetime import date, datetime

from flask import Blueprint, g, jsonify, request

from .auth import require_auth
from .db import get_db
from .errors import ApiError
from .households import json_body

bp = Blueprint("community", __name__, url_prefix="/api")
ADMIN_GROUP = "homewallet-dev-admins"
POST_TYPES = {"tip", "budget_template"}
POST_STATUSES = {"PENDING", "APPROVED", "HIDDEN"}


def _require_admin():
    # The browser may use this same claim to display admin controls, but only
    # this server-side check grants permission to read or change the queue.
    groups = g.claims.get("cognito:groups", [])
    if not isinstance(groups, list) or ADMIN_GROUP not in groups:
        raise ApiError(403, "FORBIDDEN", "Bạn không có quyền quản trị cộng đồng.")


def _query_status():
    status = request.args.get("status", "PENDING").upper()
    if status not in POST_STATUSES:
        raise ApiError(422, "VALIDATION", "Trạng thái bài viết không hợp lệ")
    return status


def _text(value, *, field, maximum, required=True):
    if not isinstance(value, str):
        raise ApiError(422, "VALIDATION", f"{field} không hợp lệ")
    value = value.strip()
    if (required and not value) or len(value) > maximum:
        raise ApiError(422, "VALIDATION", f"{field} phải có từ 1 đến {maximum} ký tự")
    return value


def _serialize(row):
    updated_at = row.get("updated_at")
    if isinstance(updated_at, (datetime, date)):
        row["updated_at"] = updated_at.isoformat()
    return row


def _list_posts(db, *, status=None):
    query = (
        "SELECT p.id, p.type, p.title, p.body, p.status, "
        "COALESCE(NULLIF(u.display_name, ''), u.email) AS author, p.updated_at "
        "FROM community_posts p JOIN users u ON u.id = p.author_id"
    )
    params = ()
    if status is not None:
        query += " WHERE p.status = %s"
        params = (status,)
    query += " ORDER BY p.updated_at DESC, p.id DESC"
    with db.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    return [_serialize(row) for row in rows]


@bp.get("/community/posts")
@require_auth
def list_approved_posts():
    # Public/community readers can never ask this endpoint for pending or
    # hidden content; status query parameters are intentionally ignored.
    return jsonify(items=_list_posts(get_db(), status="APPROVED"))


@bp.post("/community/posts")
@require_auth
def create_post():
    data = json_body()
    if set(data) != {"type", "title", "body"}:
        raise ApiError(422, "VALIDATION", "Trường dữ liệu bài viết không hợp lệ")
    post_type = data["type"]
    if not isinstance(post_type, str) or post_type not in POST_TYPES:
        raise ApiError(422, "VALIDATION", "Loại bài viết không hợp lệ")
    title = _text(data["title"], field="Tiêu đề", maximum=120)
    body = _text(data["body"], field="Nội dung", maximum=3000)

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO community_posts (author_id, type, title, body, status) "
                "VALUES (%s, %s, %s, %s, 'PENDING')",
                (g.user["id"], post_type, title, body),
            )
            post_id = cur.lastrowid
            cur.execute(
                "INSERT INTO audit_logs (actor_id, action, entity, entity_id) "
                "VALUES (%s, 'COMMUNITY_POST_CREATED', 'community_post', %s)",
                (g.user["id"], post_id),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    with db.cursor() as cur:
        cur.execute(
            "SELECT p.id, p.type, p.title, p.body, p.status, "
            "COALESCE(NULLIF(u.display_name, ''), u.email) AS author, p.updated_at "
            "FROM community_posts p JOIN users u ON u.id = p.author_id WHERE p.id = %s",
            (post_id,),
        )
        post = cur.fetchone()
    return jsonify(post=_serialize(post)), 201


@bp.get("/admin/community/posts")
@require_auth
def list_admin_posts():
    _require_admin()
    status = _query_status() if "status" in request.args else None
    return jsonify(items=_list_posts(get_db(), status=status))


@bp.patch("/admin/community/posts/<int:post_id>")
@require_auth
def update_admin_post(post_id):
    _require_admin()
    data = json_body()
    allowed = {"title", "body", "status"}
    if not data or set(data) - allowed:
        raise ApiError(422, "VALIDATION", "Trường cập nhật bài viết không hợp lệ")

    updates = {}
    if "title" in data:
        updates["title"] = _text(data["title"], field="Tiêu đề", maximum=120)
    if "body" in data:
        updates["body"] = _text(data["body"], field="Nội dung", maximum=3000)
    if "status" in data:
        status = data["status"]
        if not isinstance(status, str) or status not in POST_STATUSES:
            raise ApiError(422, "VALIDATION", "Trạng thái bài viết không hợp lệ")
        updates["status"] = status

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT id FROM community_posts WHERE id = %s FOR UPDATE", (post_id,)
            )
            if not cur.fetchone():
                raise ApiError(404, "NOT_FOUND", "Không tìm thấy bài viết")
            assignments = ", ".join(f"{field} = %s" for field in updates)
            cur.execute(
                f"UPDATE community_posts SET {assignments} WHERE id = %s",
                (*updates.values(), post_id),
            )
            cur.execute(
                "INSERT INTO audit_logs (actor_id, action, entity, entity_id) "
                "VALUES (%s, 'COMMUNITY_POST_UPDATED', 'community_post', %s)",
                (g.user["id"], post_id),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    with db.cursor() as cur:
        cur.execute(
            "SELECT p.id, p.type, p.title, p.body, p.status, "
            "COALESCE(NULLIF(u.display_name, ''), u.email) AS author, p.updated_at "
            "FROM community_posts p JOIN users u ON u.id = p.author_id WHERE p.id = %s",
            (post_id,),
        )
        post = cur.fetchone()
    return jsonify(post=_serialize(post))
