from datetime import date

import pytest

from app.dashboard import _period_bounds
from app.db import get_db
from app.errors import ApiError


def auth(make_token, sub="sub-a"):
    return {"Authorization": f"Bearer {make_token(sub=sub)}"}


def create_household(client, make_token, sub="sub-a"):
    response = client.post(
        "/api/households",
        json={"name": f"Dashboard {sub}"},
        headers=auth(make_token, sub),
    )
    assert response.status_code == 201
    return response.get_json()


def insert_transaction(
    db_app, household_id, member_id, category_id, amount, occurred_on, status
):
    with db_app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO transactions "
                "(household_id, member_id, occurred_on, total_amount, category_id, status, source) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'MANUAL')",
                (household_id, member_id, occurred_on, amount, category_id, status),
            )
        db.commit()


def test_period_bounds_validate_month_and_handle_december():
    assert _period_bounds("2026-10") == (date(2026, 10, 1), date(2026, 11, 1))
    assert _period_bounds("2026-12") == (date(2026, 12, 1), date(2027, 1, 1))
    for invalid_period in ("2026-13", "0000-01", "9999-12"):
        with pytest.raises(ApiError) as error:
            _period_bounds(invalid_period)
        assert error.value.status == 422


def test_dashboard_aggregates_confirmed_transactions_by_category_member_and_week(
    db_app, make_token
):
    client = db_app.test_client()
    household = create_household(client, make_token)
    client.post(
        "/api/households/join",
        json={"invite_code": household["invite_code"]},
        headers=auth(make_token, "sub-b"),
    )
    with db_app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "SELECT id, display_name FROM users "
                "WHERE cognito_sub IN (%s, %s) ORDER BY cognito_sub",
                ("sub-a", "sub-b"),
            )
            members = cur.fetchall()
            member_ids = [row["id"] for row in members]
            display_names = [row["display_name"] for row in members]
            cur.execute("SELECT id FROM categories WHERE household_id IS NULL ORDER BY id LIMIT 2")
            category_ids = [row["id"] for row in cur.fetchall()]

    insert_transaction(
        db_app, household["id"], member_ids[0], category_ids[0], 120000,
        date(2026, 10, 5), "CONFIRMED",
    )
    insert_transaction(
        db_app, household["id"], member_ids[1], category_ids[1], 50000,
        date(2026, 10, 11), "CONFIRMED",
    )
    insert_transaction(
        db_app, household["id"], member_ids[1], category_ids[0], 30000,
        date(2026, 10, 12), "CONFIRMED",
    )
    insert_transaction(
        db_app, household["id"], member_ids[0], category_ids[0], 999999,
        date(2026, 10, 8), "DRAFT",
    )
    insert_transaction(
        db_app, household["id"], member_ids[0], category_ids[0], 777777,
        date(2026, 11, 1), "CONFIRMED",
    )

    response = client.get(
        "/api/dashboard?period=2026-10",
        headers=auth(make_token),
    )

    assert response.status_code == 200
    result = response.get_json()
    assert result["period"] == "2026-10"
    assert result["total"] == 200000
    assert result["by_category"] == [
        {"category_id": category_ids[0], "name": "Ăn uống", "amount": 150000},
        {"category_id": category_ids[1], "name": "Đi chợ, siêu thị", "amount": 50000},
    ]
    assert result["by_member"] == [
        {"user_id": member_ids[0], "display_name": display_names[0], "amount": 120000},
        {"user_id": member_ids[1], "display_name": display_names[1], "amount": 80000},
    ]
    assert result["by_week"] == [
        {"week_start": "2026-10-05", "amount": 170000},
        {"week_start": "2026-10-12", "amount": 30000},
    ]


def test_dashboard_is_household_scoped(db_app, make_token):
    client = db_app.test_client()
    household_a = create_household(client, make_token, "sub-a")
    household_b = create_household(client, make_token, "sub-b")
    with db_app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE cognito_sub = %s", ("sub-b",))
            member_id = cur.fetchone()["id"]
            cur.execute("SELECT id FROM categories WHERE household_id IS NULL ORDER BY id LIMIT 1")
            category_id = cur.fetchone()["id"]
    insert_transaction(
        db_app, household_b["id"], member_id, category_id, 12345,
        date(2026, 10, 10), "CONFIRMED",
    )

    response = client.get(
        "/api/dashboard?period=2026-10",
        headers=auth(make_token, "sub-a"),
    )

    assert household_a["id"] != household_b["id"]
    assert response.status_code == 200
    assert response.get_json()["total"] == 0
    assert response.get_json()["by_category"] == []


def test_dashboard_requires_membership_and_valid_period(db_app, make_token):
    client = db_app.test_client()
    no_household = client.get(
        "/api/dashboard?period=2026-10",
        headers=auth(make_token, "sub-a"),
    )
    assert no_household.status_code == 404

    create_household(client, make_token)
    invalid_period = client.get(
        "/api/dashboard?period=2026-13",
        headers=auth(make_token),
    )
    assert invalid_period.status_code == 422