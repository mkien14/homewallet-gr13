from flask import g

from app import receipts


def test_delete_receipt_does_not_contact_s3(app, monkeypatch):
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query, params):
            self.queries.append((query, params))
        def fetchone(self): return {"status": "UPLOADED"}

    class DB:
        def __init__(self):
            self.cursor_instance = Cursor()
            self.cursor_instance.queries = []
            self.committed = False
        def cursor(self): return self.cursor_instance
        def commit(self): self.committed = True
        def rollback(self): raise AssertionError("unexpected rollback")

    db = DB()
    monkeypatch.setattr(receipts, "get_db", lambda: db)
    monkeypatch.setattr(receipts, "membership", lambda db, user_id: {"household_id": 7})
    with app.test_request_context():
        g.user = {"id": 1}
        result = receipts.delete_receipt.__wrapped__(12)
        assert result.get_json() == {"deleted": True}
    assert db.committed
    assert db.cursor_instance.queries[-1][1] == (12, 7)
