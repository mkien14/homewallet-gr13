"""Request-level authorization tests; no external database or AWS required."""
import pytest

from app import households, users


class MemoryDb:
    def __init__(self):
        self.members = {
            1: {"household_id": 12, "role": "owner", "name": "A", "invite_code": "AAAA"},
            2: {"household_id": 12, "role": "member", "name": "A", "invite_code": "AAAA"},
            3: {"household_id": 12, "role": "member", "name": "A", "invite_code": "AAAA"},
            4: {"household_id": 13, "role": "member", "name": "B", "invite_code": "BBBB"},
        }
        self.transactions = [{"household_id": 12, "member_id": 2, "amount": 50000}]
        self.receipts = [{"household_id": 12, "uploader_id": 2}]
        self.commits = 0
        self.rollbacks = 0
        self.race = False
        self.history = []
        self.pending_history = []

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.commits += 1
        self.history.extend(self.pending_history)
        self.pending_history.clear()

    def rollback(self):
        self.rollbacks += 1
        self.pending_history.clear()


class Cursor:
    def __init__(self, db):
        self.db = db
        self.result = None
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.rowcount = 0
        if sql.startswith("SELECT m.household_id"):
            self.result = self.db.members.get(params[0])
        elif sql.startswith("SELECT id FROM households"):
            self.result = {"id": params[0]} if any(m["household_id"] == params[0] for m in self.db.members.values()) else None
        elif sql.startswith("SELECT role FROM household_members"):
            hid, uid = params
            record = self.db.members.get(uid)
            self.result = record if record and record["household_id"] == hid else None
        elif sql.startswith("INSERT INTO household_membership_history"):
            reason, hid, uid = params
            record = self.db.members.get(uid)
            if record and record["household_id"] == hid:
                self.db.pending_history.append((uid, hid, reason))
                self.rowcount = 1
        elif sql.startswith("DELETE FROM household_members"):
            hid, uid = params
            record = self.db.members.get(uid)
            if record and record["household_id"] == hid and ("role = 'member'" not in sql or record["role"] == "member") and not self.db.race:
                del self.db.members[uid]
                self.rowcount = 1
        else:
            raise AssertionError(f"Unexpected query: {sql}")

    def fetchone(self):
        return self.result


@pytest.fixture
def scenario(app, monkeypatch, make_token):
    db = MemoryDb()
    monkeypatch.setattr(households, "get_db", lambda: db)
    monkeypatch.setattr(users, "get_or_create_user", lambda claims, _token: {
        "id": int(claims["sub"]), "email": f'{claims["sub"]}@test.local', "display_name": "Test",
    })
    def headers(uid):
        return {"Authorization": f"Bearer {make_token(sub=str(uid))}"}
    return app.test_client(), db, headers


def test_member_leaves_only_self_and_keeps_household_data(scenario):
    client, db, headers = scenario
    assert client.delete("/api/households/12/members/me", headers=headers(2)).status_code == 204
    assert db.commits == 1
    assert db.history == [(2, 12, "left")]
    assert client.get("/api/me", headers=headers(2)).get_json()["household"] is None
    assert client.get("/api/households/12/members", headers=headers(2)).status_code == 404
    assert {1, 3, 4} == set(db.members)
    assert db.transactions == [{"household_id": 12, "member_id": 2, "amount": 50000}]
    assert db.receipts == [{"household_id": 12, "uploader_id": 2}]
    assert client.delete("/api/households/12/members/me", headers=headers(2)).status_code == 404


def test_only_member_of_current_household_can_leave(scenario):
    client, db, headers = scenario
    assert client.delete("/api/households/12/members/me").status_code == 401
    assert client.delete("/api/households/12/members/me", headers=headers(1)).status_code == 403
    assert client.delete("/api/households/12/members/me", headers=headers(4)).status_code == 404
    assert client.delete("/api/households/12/members/3", headers=headers(2)).status_code == 403
    assert client.delete("/api/households/12/members/1", headers=headers(1)).status_code == 422
    assert client.delete("/api/households/12/members/3", headers=headers(1)).status_code == 204
    assert 1 in db.members and 2 in db.members and 3 not in db.members


def test_membership_race_returns_conflict_without_removing_anyone(scenario):
    client, db, headers = scenario
    db.race = True
    assert client.delete("/api/households/12/members/me", headers=headers(2)).status_code == 409
    assert 2 in db.members
    assert db.history == []
    assert db.commits == 0
    assert db.rollbacks == 1
