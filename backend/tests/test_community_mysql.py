"""D2 SQL/transaction evidence against an isolated MySQL 8.4 database.

Opt in with HOMEWALLET_COMMUNITY_MYSQL=1. Connection/schema errors then FAIL,
never skip. Each test creates and drops only its own random local database.
"""

import os
import importlib.util
from pathlib import Path
import re
import uuid

import pytest

from app import community, users
from app.db import connect, get_db
from jobs.migrate import MIG, statements


@pytest.fixture
def community_mysql(app, monkeypatch):
    if os.getenv("HOMEWALLET_COMMUNITY_MYSQL") != "1":
        pytest.skip("Set HOMEWALLET_COMMUNITY_MYSQL=1 to run isolated MySQL D2 tests")
    assert app.config["DB_HOST"] in ("localhost", "127.0.0.1"), "Local MySQL only"
    name = f"hw_d2_{uuid.uuid4().hex}_test"
    assert re.fullmatch(r"hw_d2_[0-9a-f]{32}_test", name)
    app.config["DB_NAME"] = name
    connection = connect(app.config, database=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4")
            cursor.execute(f"USE `{name}`")
            for migration in sorted(MIG.glob("*.sql")):
                for statement in statements(migration.read_text(encoding="utf-8-sig")):
                    # 001 contains production DB selection; never execute it in tests.
                    if statement.upper().startswith(("CREATE DATABASE", "USE ")):
                        continue
                    cursor.execute(statement)
        connection.commit()
        monkeypatch.setattr(users, "fetch_email", lambda token, claims, cfg: claims["sub"] + "@test.local")
        yield app.test_client(), connection
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{name}`")
        connection.close()


def auth(make_token, sub="member", admin=False):
    claims = {"sub": sub}
    if admin:
        claims["cognito:groups"] = ["other-group", community.ADMIN_GROUP]
    return {"Authorization": f"Bearer {make_token(**claims)}"}


def rows(connection, sql, params=()):
    connection.commit()  # Fresh snapshot after an API transaction commits.
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def create(client, header, **overrides):
    response = client.post("/api/community/posts", headers=header, json={
        "type": "tip", "title": "  Save energy  ", "body": "  Turn off unused lights.  ",
        **overrides,
    })
    assert response.status_code == 201, response.get_json()
    return response.get_json()["post"]


def test_moderation_lifecycle_visibility_and_private_audit(community_mysql, make_token):
    client, connection = community_mysql
    member = auth(make_token)
    admin = auth(make_token, "moderator", admin=True)
    post = create(client, member)
    assert post["status"] == "PENDING"
    assert post["title"] == "Save energy"
    assert post["body"] == "Turn off unused lights."
    assert set(post) == {"id", "type", "title", "body", "status", "author", "updated_at"}
    post_id = post["id"]
    path = f"/api/admin/community/posts/{post_id}"

    for suffix in ("", "?status=PENDING", "?status=HIDDEN", "?status=ALL"):
        assert client.get("/api/community/posts" + suffix, headers=member).get_json() == {"items": []}
    assert client.get("/api/admin/community/posts", headers=member).status_code == 403
    assert client.patch(path, headers=member, json={"status": "APPROVED"}).status_code == 403
    assert client.get("/api/admin/community/posts?status=pending", headers=admin).get_json()["items"] == [post]

    for patch in ({"status": "APPROVED"}, {"title": "Edited tip", "body": "Edited text"},
                  {"status": "HIDDEN"}, {"status": "PENDING"}, {"status": "APPROVED"}):
        response = client.patch(path, headers=admin, json=patch)
        assert response.status_code == 200
        updated = response.get_json()["post"]
        for field, value in patch.items():
            assert updated[field] == value
        feed = client.get("/api/community/posts", headers=member).get_json()["items"]
        assert feed == ([updated] if updated["status"] == "APPROVED" else [])

    audit = rows(connection, "SELECT * FROM audit_logs ORDER BY id")
    assert len(audit) == 6  # Denied requests and reads never append an action.
    ids = {row["cognito_sub"]: row["id"] for row in rows(connection, "SELECT id, cognito_sub FROM users")}
    for index, entry in enumerate(audit):
        assert set(entry) == {"id", "actor_id", "action", "entity", "entity_id", "at"}
        assert entry["actor_id"] == ids["member" if index == 0 else "moderator"]
        assert entry["action"] == ("COMMUNITY_POST_CREATED" if index == 0 else "COMMUNITY_POST_UPDATED")
        assert entry["entity"] == "community_post" and entry["entity_id"] == post_id
        assert entry["at"] is not None


def test_types_boundaries_filters_order_and_author_privacy(community_mysql, make_token):
    client, connection = community_mysql
    member, admin = auth(make_token), auth(make_token, "moderator", admin=True)
    first = create(client, member, type="budget_template", title="x" * 120, body="y" * 3000)
    second = create(client, member)
    third = create(client, admin)
    assert third["status"] == "PENDING"  # Even admins submit through moderation.
    for post, status in ((first, "APPROVED"), (second, "HIDDEN")):
        assert client.patch(f"/api/admin/community/posts/{post['id']}", headers=admin,
                            json={"status": status}).status_code == 200
    with connection.cursor() as cursor:
        cursor.execute("UPDATE community_posts SET updated_at = '2026-11-01 00:00:00'")
        cursor.execute("UPDATE users SET display_name = '   '")
    connection.commit()
    all_posts = client.get("/api/admin/community/posts", headers=admin).get_json()["items"]
    assert [post["id"] for post in all_posts] == [third["id"], second["id"], first["id"]]
    assert all(post["author"] is None for post in all_posts)
    for status, expected in (("PENDING", third), ("APPROVED", first), ("HIDDEN", second)):
        response = client.get(f"/api/admin/community/posts?status={status}", headers=admin)
        assert [post["id"] for post in response.get_json()["items"]] == [expected["id"]]
        assert "@test.local" not in response.get_data(as_text=True)
    response = client.get("/api/community/posts", headers=member)
    assert response.get_json()["items"][0]["author"] is None
    assert "@test.local" not in response.get_data(as_text=True)
    changed = client.patch(f"/api/admin/community/posts/{first['id']}", headers=admin,
                           json={"body": "New text"})
    assert changed.get_json()["post"]["author"] is None
    assert create(client, member)["author"] is None


def test_missing_post_and_invalid_patch_do_not_write_audit(community_mysql, make_token):
    client, connection = community_mysql
    admin = auth(make_token, "moderator", admin=True)
    response = client.patch("/api/admin/community/posts/9999", headers=admin,
                            json={"status": "APPROVED"})
    assert response.status_code == 404
    assert rows(connection, "SELECT * FROM audit_logs") == ()
    post = create(client, auth(make_token))
    response = client.patch(f"/api/admin/community/posts/{post['id']}", headers=admin,
                            json={"title": "Must not persist", "status": "INVALID"})
    assert response.status_code == 422
    assert rows(connection, "SELECT title FROM community_posts")[0]["title"] == post["title"]
    assert len(rows(connection, "SELECT * FROM audit_logs")) == 1


@pytest.mark.parametrize("operation", ["create", "update"])
def test_audit_failure_rolls_back_post_in_mysql(community_mysql, make_token, monkeypatch, operation):
    client, connection = community_mysql
    member, admin = auth(make_token), auth(make_token, "moderator", admin=True)
    post = create(client, member)
    before_posts = rows(connection, "SELECT * FROM community_posts")
    before_audit = rows(connection, "SELECT * FROM audit_logs")

    class BrokenAuditCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def __enter__(self):
            self.cursor.__enter__()
            return self

        def __exit__(self, *args):
            return self.cursor.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.cursor, name)

        def execute(self, query, params=None):
            if query.startswith("INSERT INTO audit_logs"):
                raise RuntimeError("Injected audit failure")
            return self.cursor.execute(query, params)

    class BrokenAuditDB:
        def __init__(self, db):
            self.db = db

        def cursor(self):
            return BrokenAuditCursor(self.db.cursor())

        def __getattr__(self, name):
            return getattr(self.db, name)

    monkeypatch.setattr(community, "get_db", lambda: BrokenAuditDB(get_db()))
    with pytest.raises(RuntimeError, match="Injected audit failure"):
        if operation == "create":
            create(client, member)
        else:
            client.patch(f"/api/admin/community/posts/{post['id']}", headers=admin,
                         json={"title": "Must roll back", "status": "APPROVED"})
    assert rows(connection, "SELECT * FROM community_posts") == before_posts
    assert rows(connection, "SELECT * FROM audit_logs") == before_audit


def test_dev_evidence_runner_against_real_api_and_mysql(community_mysql, make_token):
    client, connection = community_mysql
    script = Path(__file__).resolve().parents[2] / "scripts" / "verify-d2-community.py"
    spec = importlib.util.spec_from_file_location("verify_d2", script)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    tokens = {"member": auth(make_token), "admin": auth(make_token, "moderator", admin=True)}

    def call(method, path, role=None, body=None):
        response = client.open(path, method=method, json=body, headers=tokens.get(role, {}))
        return response.status_code, response.get_json(), response.headers.get("X-Request-Id")

    evidence = runner.run_checks(call)
    assert evidence["status"] == "PASS", evidence
    assert evidence["audit_status"] == "PENDING_DB_VERIFICATION"
    assert len(evidence["cases"]) == 16
    assert rows(connection, "SELECT status FROM community_posts")[0]["status"] == "HIDDEN"
    assert len(rows(connection, "SELECT * FROM audit_logs")) == 5
