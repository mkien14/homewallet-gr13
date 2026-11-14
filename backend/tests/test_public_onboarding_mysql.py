"""Public onboarding against the existing isolated local MySQL test fixture."""
from jobs.household_scope import approved_households
from jobs.weekly_report import _list_households
from app.db import get_db
from test_household_history_mysql import history_mysql  # Reuse isolated local schema fixture.


def test_public_signup_profile_create_join_isolation_and_retained_data(history_mysql, make_token):
    client, _ = history_mysql
    db_app = client.application
    def headers(subject):
        return {"Authorization": "Bearer " + make_token(sub=subject)}

    # Reserve household 1 before public mode, matching the retained live boundary.
    retained = client.post("/api/households", json={"name": "Retained fixture"}, headers=headers("retained")).get_json()
    assert retained["id"] == 1
    db_app.config.update(APP_ENV="production", PRODUCTION_PUBLIC_REGISTRATION=True, PRODUCTION_ALLOWED_HOUSEHOLD_IDS=set())
    fresh = client.get("/api/me", headers=headers("new-owner"))
    assert fresh.status_code == 200 and fresh.get_json()["household"] is None
    created = client.post("/api/households", json={"name": "Public fixture"}, headers=headers("new-owner"))
    assert created.status_code == 201
    household = created.get_json()
    assert household["id"] > 1 and household["role"] == "owner"
    joined = client.post("/api/households/join", json={"invite_code": household["invite_code"]}, headers=headers("new-member"))
    assert joined.status_code == 200 and joined.get_json()["role"] == "member"
    assert client.get(f"/api/households/{household['id']}/members", headers=headers("outsider")).status_code == 404
    assert client.get("/api/me", headers=headers("retained")).status_code == 403
    assert client.post("/api/households/join", json={"invite_code": retained["invite_code"]}, headers=headers("outsider")).status_code == 404
    assert client.delete(f"/api/households/{household['id']}/members/me", headers=headers("new-member")).status_code == 204
    assert client.get("/api/me", headers=headers("new-member")).get_json()["household"] is None
    assert client.post("/api/households/join", json={"invite_code": household["invite_code"]}, headers=headers("new-member")).status_code == 200
    with db_app.app_context():
        db = get_db()
        selected = _list_households(db, approved_households(db_app.config))
        assert selected and all(row["id"] > 1 for row in selected)
        with db.cursor() as cursor:
            cursor.execute("SELECT name FROM households WHERE id = 1")
            assert cursor.fetchone()["name"] == "Retained fixture"
            cursor.execute("SELECT COUNT(*) AS n FROM household_members WHERE household_id = 1")
            assert cursor.fetchone()["n"] == 1
