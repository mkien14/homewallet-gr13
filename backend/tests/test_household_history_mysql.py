"""Household history acceptance using a dedicated, local MySQL test database."""
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from threading import Event
import uuid

import pytest

from app import households, storage, users
from app.db import connect
from app.errors import ApiError
from jobs.migrate import MIG, statements


@pytest.fixture
def history_mysql(app, monkeypatch):
    if os.getenv("HOMEWALLET_HISTORY_MYSQL") != "1":
        pytest.skip("Set HOMEWALLET_HISTORY_MYSQL=1 for isolated local MySQL tests")
    assert app.config["DB_HOST"] in ("localhost", "127.0.0.1"), "Local MySQL only"
    name = f"hw_history_{uuid.uuid4().hex}_test"
    assert re.fullmatch(r"hw_history_[0-9a-f]{32}_test", name)
    app.config["DB_NAME"] = name
    connection = connect(app.config, database=False)
    created = False
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4")
            created = True
            cursor.execute(f"USE `{name}`")
            for migration in sorted(MIG.glob("*.sql")):
                for statement in statements(migration.read_text(encoding="utf-8-sig")):
                    if statement.upper().startswith(("CREATE DATABASE", "USE ")):
                        continue
                    cursor.execute(statement)
        connection.commit()
        monkeypatch.setattr(users, "fetch_email", lambda token, claims, cfg: claims["sub"] + "@test.local")
        monkeypatch.setattr(storage, "delete_s3_objects", lambda keys: {"deleted": len(keys), "keys": keys})
        yield app.test_client(), connection
    finally:
        if created:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{name}`")
        connection.close()


def auth(make_token, sub):
    return {"Authorization": f"Bearer {make_token(sub=sub)}"}


def history(client, header):
    response = client.get("/api/me/household-history", headers=header)
    assert response.status_code == 200
    return response.get_json()["items"]


def test_history_is_private_and_survives_leave_removal_rejoin_and_dissolution(history_mysql, make_token):
    client, _ = history_mysql
    owner = auth(make_token, "owner")
    member = auth(make_token, "member")
    other = auth(make_token, "other")
    outsider = auth(make_token, "outsider")
    assert client.get("/api/me/household-history").status_code == 401
    created = client.post("/api/households", json={"name": "House A"}, headers=owner)
    assert created.status_code == 201
    house = created.get_json()
    hid = house["id"]
    for header in (member, other):
        assert client.post("/api/households/join", json={"invite_code": house["invite_code"]}, headers=header).status_code == 200
    assert history(client, member)[0]["end_reason"] is None
    assert history(client, outsider) == []
    assert client.get("/api/me/household-history?user_id=1", headers=outsider).get_json()["items"] == []

    assert client.delete(f"/api/households/{hid}/members/me", headers=member).status_code == 204
    member_history = history(client, member)
    assert len(member_history) == 1 and member_history[0]["end_reason"] == "left"
    assert member_history[0]["household_name"] == "House A"
    assert member_history[0]["ended_at"] and member_history[0]["joined_at"]
    assert client.post("/api/households/join", json={"invite_code": house["invite_code"]}, headers=member).status_code == 200
    member_id = client.get("/api/me", headers=member).get_json()["user"]["id"]
    assert client.delete(f"/api/households/{hid}/members/{member_id}", headers=owner).status_code == 204
    assert [item["end_reason"] for item in history(client, member)] == ["removed", "left"]
    assert client.post("/api/households/join", json={"invite_code": house["invite_code"]}, headers=member).status_code == 200
    assert client.post(f"/api/households/{hid}/delete", json={"confirm": True, "household_id": hid}, headers=member).status_code == 403
    result = client.post(f"/api/households/{hid}/delete", json={"confirm": True, "household_id": hid}, headers=owner)
    assert result.status_code == 200
    assert [item["end_reason"] for item in history(client, member)] == ["dissolved", "removed", "left"]
    assert [item["end_reason"] for item in history(client, owner)] == ["dissolved"]
    assert [item["end_reason"] for item in history(client, other)] == ["dissolved"]
    assert all("invite_code" not in item and "user_id" not in item for item in history(client, member))
    assert history(client, outsider) == []


def test_failed_history_and_failed_storage_do_not_end_membership(history_mysql, make_token, monkeypatch):
    client, _ = history_mysql
    owner = auth(make_token, "owner")
    member = auth(make_token, "member")
    house = client.post("/api/households", json={"name": "House B"}, headers=owner).get_json()
    hid = house["id"]
    assert client.post("/api/households/join", json={"invite_code": house["invite_code"]}, headers=member).status_code == 200
    original = households.record_membership_end
    def broken_history(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic database failure")
    monkeypatch.setattr(households, "record_membership_end", broken_history)
    storage_calls = []
    monkeypatch.setattr(storage, "delete_s3_objects", lambda keys: storage_calls.append(keys))
    with pytest.raises(RuntimeError):
        client.delete(f"/api/households/{hid}/members/me", headers=member)
    with pytest.raises(RuntimeError):
        client.post(f"/api/households/{hid}/delete", json={"confirm": True}, headers=owner)
    assert storage_calls == []  # A failed history write must precede S3 deletion.
    assert history(client, member)[0]["end_reason"] is None
    assert len(history(client, member)) == 1
    monkeypatch.setattr(households, "record_membership_end", original)
    monkeypatch.setattr(storage, "delete_s3_objects", lambda keys: (_ for _ in ()).throw(ApiError(502, "S3_DELETE_FAILED", "synthetic")))
    assert client.post(f"/api/households/{hid}/delete", json={"confirm": True}, headers=owner).status_code == 502
    assert history(client, owner)[0]["end_reason"] is None
    assert history(client, member)[0]["end_reason"] is None
    monkeypatch.setattr(storage, "delete_s3_objects", lambda keys: {"deleted": len(keys), "keys": keys})
    monkeypatch.setattr(households, "_delete_household_db", lambda db, hid: (_ for _ in ()).throw(RuntimeError("synthetic DB failure")))
    response = client.post(f"/api/households/{hid}/delete", json={"confirm": True}, headers=owner)
    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "HOUSEHOLD_DELETE_PARTIAL"
    assert len(history(client, owner)) == 1 and history(client, owner)[0]["end_reason"] is None
    assert len(history(client, member)) == 1 and history(client, member)[0]["end_reason"] is None


def test_join_cannot_race_with_household_dissolution(history_mysql, make_token, monkeypatch, app):
    client, _ = history_mysql
    owner = auth(make_token, "owner")
    late_member = auth(make_token, "late")
    house = client.post("/api/households", json={"name": "House C"}, headers=owner).get_json()
    assert client.get("/api/me", headers=late_member).status_code == 200
    locked = Event()
    release = Event()
    def wait_for_storage(keys):
        locked.set()
        assert release.wait(10)
        return {"deleted": len(keys), "keys": keys}
    monkeypatch.setattr(storage, "delete_s3_objects", wait_for_storage)
    def dissolve():
        return app.test_client().post(f"/api/households/{house['id']}/delete", json={"confirm": True}, headers=owner).status_code
    def join():
        return app.test_client().post("/api/households/join", json={"invite_code": house["invite_code"]}, headers=late_member).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        deletion = pool.submit(dissolve)
        try:
            assert locked.wait(5)
            joining = pool.submit(join)
            with pytest.raises(FutureTimeoutError):
                joining.result(timeout=.5)
        finally:
            release.set()
        assert deletion.result(timeout=10) == 200
        assert joining.result(timeout=10) == 404
    assert history(client, late_member) == []
    assert [item["end_reason"] for item in history(client, owner)] == ["dissolved"]
