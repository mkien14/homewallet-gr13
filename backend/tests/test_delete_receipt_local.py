from flask import g

from app import receipts


def test_delete_receipt_removes_s3_object_before_database_rows(app, monkeypatch):
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query, params):
            self.queries.append((query, params))
        def fetchone(self): return {"s3_key": "receipts/uploads/7/test.jpg"}

    class DB:
        def __init__(self):
            self.cursor_instance = Cursor()
            self.cursor_instance.queries = []
            self.committed = False
        def cursor(self): return self.cursor_instance
        def commit(self): self.committed = True
        def rollback(self): raise AssertionError("unexpected rollback")

    db = DB()
    events = []
    monkeypatch.setattr(receipts, "get_db", lambda: db)
    monkeypatch.setattr(receipts, "membership", lambda db, user_id: {"household_id": 7})
    monkeypatch.setattr(
        receipts.storage,
        "delete_s3_objects",
        lambda keys: events.append(("s3", keys)) or {"deleted": 1, "keys": keys},
    )
    original_execute = db.cursor_instance.execute

    def execute(query, params):
        events.append(("db", query))
        original_execute(query, params)

    db.cursor_instance.execute = execute
    with app.test_request_context():
        g.user = {"id": 1}
        result = receipts.delete_receipt.__wrapped__(12)
        assert result.get_json() == {"deleted": True}
    assert db.committed
    assert events[0][0] == "db"
    assert events[1] == ("s3", ["receipts/uploads/7/test.jpg"])
    assert events[2][0] == "db"
    assert db.cursor_instance.queries[-1][1] == (12, 7)
