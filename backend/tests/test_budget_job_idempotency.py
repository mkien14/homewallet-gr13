from datetime import date

import pymysql
import pytest

from app.budget_suggestions import BudgetSuggestionError, _parse_allocations
from jobs import recurring_alerts


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.rows = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        query = " ".join(query.split())
        self.rows = []
        self.rowcount = 0
        if query.startswith("SELECT b.household_id"):
            self.db.queries.append((query, params))
            self.rows = list(self.db.budget_rows)
        elif query.startswith("INSERT INTO alert_state"):
            key = tuple(params)
            if key in self.db.alert_state:
                raise pymysql.err.IntegrityError(1062, "duplicate alert state")
            self.db.alert_state.add(key)
        elif query.startswith("UPDATE alert_state SET sent_at"):
            self.db.updated_alerts.append(tuple(params))
        else:
            raise AssertionError(f"Unexpected SQL: {query}")

    def fetchall(self):
        return self.rows


class FakeDb:
    def __init__(self, budget_rows):
        self.budget_rows = budget_rows
        self.alert_state = set()
        self.updated_alerts = []
        self.queries = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeSes:
    def __init__(self):
        self.calls = []

    def send_email(self, **kwargs):
        self.calls.append(kwargs)


@pytest.mark.parametrize(
    "response",
    [
        '{"allocations":[{"category_id":9,"amount":10}]}',
        '{"allocations":[{"category_id":1,"amount":10},{"category_id":1,"amount":20}]}',
        '{"allocations":[{"category_id":1,"amount":101}]}',
    ],
)
def test_llm_suggestion_rejects_unknown_duplicate_or_over_budget_categories(response):
    with pytest.raises(BudgetSuggestionError):
        _parse_allocations(
            response,
            {1: "Food", 2: "Transport"},
            income_estimate=100,
            savings_goal=0,
        )


@pytest.mark.parametrize(
    "spent,budget,expected",
    [
        (799, 1_000, []),
        (800, 1_000, [80]),
        (999, 1_000, [80]),
        (1_000, 1_000, [80, 100]),
        (1_001, 1_000, [80, 100]),
    ],
)
def test_budget_alert_thresholds_reached_at_and_above_boundary(
    spent, budget, expected
):
    assert recurring_alerts._thresholds_reached(spent, budget) == expected


def test_budget_spending_query_only_uses_confirmed_transactions():
    db = FakeDb([])

    recurring_alerts._active_budget_spending(db, "2026-10")

    query, params = db.queries[0]
    assert "t.status = 'CONFIRMED'" in query
    assert params == (date(2026, 10, 1), date(2026, 11, 1), "2026-10")


def test_budget_alert_job_is_idempotent_for_same_period_key(monkeypatch):
    db = FakeDb(
        [
            {
                "household_id": 7,
                "category_id": 2,
                "category_name": "Food",
                "budget_amount": 1_000,
                "spent": 1_000,
            }
        ]
    )
    ses = FakeSes()
    claimed_keys = set()
    finished = []
    notifications = []
    pushes = []

    def claim(_db, job_name, period_key):
        key = (job_name, period_key)
        if key in claimed_keys:
            return False
        claimed_keys.add(key)
        return True

    def finish(_db, job_name, period_key, status):
        finished.append((job_name, period_key, status))

    def create_notifications(_db, household_id, **kwargs):
        notifications.append((household_id, kwargs["event_key"]))
        return [11]

    def send_push(_db, user_ids, **kwargs):
        pushes.append((tuple(user_ids), kwargs["event_type"]))
        return {"configured": False, "sent": 0, "failed": 0, "expired": 0}

    monkeypatch.setattr(recurring_alerts, "_claim_job_run", claim)
    monkeypatch.setattr(recurring_alerts, "_finish_job_run", finish)
    monkeypatch.setattr(
        recurring_alerts,
        "_household_recipients",
        lambda _db, _household_id: [
            {"email": "owner@example.test", "preferred_locale": "en"}
        ],
    )
    monkeypatch.setattr(
        recurring_alerts,
        "create_household_notifications",
        create_notifications,
    )
    monkeypatch.setattr(recurring_alerts, "send_push_to_users", send_push)

    config = {"SES_FROM_ADDRESS": "sender@example.test"}
    first = recurring_alerts.run_budget_alerts(
        config=config,
        ses_client=ses,
        period_key="2026-10-28",
        db=db,
    )
    second = recurring_alerts.run_budget_alerts(
        config=config,
        ses_client=ses,
        period_key="2026-10-28",
        db=db,
    )

    assert first["sent"] == 2
    assert first["failed"] == 0
    assert second == {
        "job": "budget-alerts",
        "period_key": "2026-10-28",
        "skipped": True,
    }
    assert len(ses.calls) == 2
    assert len(notifications) == 2
    assert len(pushes) == 2
    assert db.alert_state == {
        (7, "2026-10", 2, 80),
        (7, "2026-10", 2, 100),
    }
    assert finished == [("BUDGET_ALERTS", "2026-10-28", "SUCCEEDED")]
