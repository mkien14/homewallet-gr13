from datetime import date

import pytest

from app import transactions
from app.db import get_db


def auth(make_token, sub):
    return {"Authorization": f"Bearer {make_token(sub=sub)}"}


def create_household(client, make_token, sub="sub-a"):
    response = client.post(
        "/api/households",
        json={"name": f"Household {sub}"},
        headers=auth(make_token, sub),
    )
    assert response.status_code == 201
    return response.get_json()


def post_transaction(client, make_token, sub="sub-a", key="tx-key-1", **overrides):
    body = {
        "occurred_on": date.today().isoformat(),
        "total_amount": 125000,
        "category_id": 1,
        "note": "Groceries",
    }
    body.update(overrides)
    return client.post(
        "/api/transactions",
        json=body,
        headers={**auth(make_token, sub), "Idempotency-Key": key},
    )


def test_create_transaction_and_idempotent_retry(db_app, make_token, monkeypatch):
    client = db_app.test_client()
    household = create_household(client, make_token)
    invalidated = []
    monkeypatch.setattr(transactions, "invalidate_dashboard", invalidated.append)

    first = post_transaction(client, make_token)
    repeated = post_transaction(
        client, make_token, total_amount=90000, note="Retry with same key"
    )

    assert first.status_code == 201
    transaction = first.get_json()["transaction"]
    assert transaction["household_id"] == household["id"]
    assert transaction["status"] == "CONFIRMED"
    assert transaction["source"] == "MANUAL"
    assert transaction["total_amount"] == 125000
    assert repeated.status_code == 200
    assert repeated.get_json()["transaction"]["id"] == transaction["id"]
    assert repeated.get_json()["transaction"]["total_amount"] == 125000
    assert invalidated == [household["id"]]
    with db_app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS count FROM transactions WHERE idempotency_key = %s",
                ("tx-key-1",),
            )
            assert cur.fetchone()["count"] == 1


@pytest.mark.parametrize(
    "body, headers",
    [
        ({"occurred_on": date.today().isoformat(), "total_amount": 0, "category_id": 1},
         {"Idempotency-Key": "valid"}),
        ({"occurred_on": "2026-99-99", "total_amount": 10, "category_id": 1},
         {"Idempotency-Key": "valid"}),
        ({"occurred_on": date.today().isoformat(), "total_amount": True, "category_id": 1},
         {"Idempotency-Key": "valid"}),
        ({"occurred_on": date.today().isoformat(), "total_amount": 10, "category_id": 999999},
         {"Idempotency-Key": "valid"}),
        ({"occurred_on": date.today().isoformat(), "total_amount": 10, "category_id": 1},
         {}),
    ],
)
def test_create_transaction_validation(db_app, make_token, body, headers):
    client = db_app.test_client()
    create_household(client, make_token)

    response = client.post(
        "/api/transactions",
        json=body,
        headers={**auth(make_token, "sub-a"), **headers},
    )

    assert response.status_code == 422


def test_list_transactions_filters_and_paginates(db_app, make_token):
    client = db_app.test_client()
    create_household(client, make_token)
    first = post_transaction(client, make_token, key="list-1").get_json()["transaction"]
    second = post_transaction(client, make_token, key="list-2", category_id=None).get_json()["transaction"]
    third = post_transaction(client, make_token, key="list-3").get_json()["transaction"]

    response = client.get(
        f"/api/transactions?period={date.today():%Y-%m}&category_id=1&limit=1",
        headers=auth(make_token, "sub-a"),
    )
    body = response.get_json()
    assert response.status_code == 200
    assert [item["id"] for item in body["items"]] == [third["id"]]
    assert body["next_cursor"] == str(third["id"])

    next_page = client.get(
        f"/api/transactions?period={date.today():%Y-%m}&category_id=1&limit=1"
        f"&cursor={body['next_cursor']}",
        headers=auth(make_token, "sub-a"),
    ).get_json()
    assert [item["id"] for item in next_page["items"]] == [first["id"]]
    assert next_page["next_cursor"] is None
    assert second["id"] not in [item["id"] for item in body["items"] + next_page["items"]]


def test_list_transactions_rejects_invalid_query(db_app, make_token):
    client = db_app.test_client()
    create_household(client, make_token)
    response = client.get(
        "/api/transactions?period=2026-13&limit=101",
        headers=auth(make_token, "sub-a"),
    )
    assert response.status_code == 422


def test_patch_and_delete_allow_creator_or_household_owner(db_app, make_token, monkeypatch):
    client = db_app.test_client()
    household = create_household(client, make_token)
    create_household(client, make_token, "sub-c")
    client.post(
        "/api/households/join",
        json={"invite_code": household["invite_code"]},
        headers=auth(make_token, "sub-b"),
    )
    transaction = post_transaction(
        client, make_token, sub="sub-b", key="member-created"
    ).get_json()["transaction"]
    invalidated = []
    monkeypatch.setattr(transactions, "invalidate_dashboard", invalidated.append)

    forbidden = client.patch(
        f"/api/transactions/{transaction['id']}",
        json={"note": "not allowed"},
        headers=auth(make_token, "sub-c"),
    )
    assert forbidden.status_code == 404
    assert client.get(
        f"/api/transactions?period={date.today():%Y-%m}",
        headers=auth(make_token, "sub-c"),
    ).get_json()["items"] == []
    cross_household_delete = client.delete(
        f"/api/transactions/{transaction['id']}",
        headers=auth(make_token, "sub-c"),
    )
    assert cross_household_delete.status_code == 404
    forbidden_member = client.patch(
        f"/api/transactions/{transaction['id']}",
        json={"note": "not allowed"},
        headers=auth(make_token, "sub-a"),
    )
    assert forbidden_member.status_code == 200  # the household owner may edit
    assert forbidden_member.get_json()["transaction"]["note"] == "not allowed"

    deleted = client.delete(
        f"/api/transactions/{transaction['id']}",
        headers=auth(make_token, "sub-a"),
    )
    assert deleted.status_code == 204
    missing = client.delete(
        f"/api/transactions/{transaction['id']}",
        headers=auth(make_token, "sub-a"),
    )
    assert missing.status_code == 404
    assert invalidated == [household["id"], household["id"]]


def test_creator_can_edit_but_unrelated_member_cannot(db_app, make_token):
    client = db_app.test_client()
    household = create_household(client, make_token)
    client.post(
        "/api/households/join",
        json={"invite_code": household["invite_code"]},
        headers=auth(make_token, "sub-b"),
    )
    client.post(
        "/api/households/join",
        json={"invite_code": household["invite_code"]},
        headers=auth(make_token, "sub-c"),
    )
    transaction = post_transaction(
        client, make_token, sub="sub-b", key="creator-edit"
    ).get_json()["transaction"]

    unrelated = client.patch(
        f"/api/transactions/{transaction['id']}",
        json={"note": "unauthorized"},
        headers=auth(make_token, "sub-c"),
    )
    creator = client.patch(
        f"/api/transactions/{transaction['id']}",
        json={"note": "creator update"},
        headers=auth(make_token, "sub-b"),
    )

    assert unrelated.status_code == 403
    assert creator.status_code == 200
    assert creator.get_json()["transaction"]["note"] == "creator update"


def test_categories_are_household_scoped(db_app, make_token):
    client = db_app.test_client()
    household = create_household(client, make_token)
    response = client.get("/api/categories", headers=auth(make_token, "sub-a"))

    assert response.status_code == 200
    categories = response.get_json()["categories"]
    assert categories
    assert all(isinstance(category["is_fixed"], bool) for category in categories)

    with db_app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO categories (household_id, name, icon) VALUES (%s, %s, %s)",
                (household["id"], "Household test category", "home"),
            )
        db.commit()
    response = client.get("/api/categories", headers=auth(make_token, "sub-a"))
    assert any(
        category["name"] == "Household test category"
        for category in response.get_json()["categories"]
    )
    with db_app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "DELETE FROM categories WHERE household_id = %s AND name = %s",
                (household["id"], "Household test category"),
            )
        db.commit()
