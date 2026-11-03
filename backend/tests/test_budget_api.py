from copy import deepcopy

import pytest

from app import budgets, users
from app.budget_suggestions import BudgetSuggestionError


class FakeBudgetDB:
    def __init__(self):
        self.categories = {1: "Food", 2: "Transport"}
        self.budgets = {}
        self.lines = {}
        self.history = []
        self.writes = []
        self.next_budget_id = 1
        self.commits = 0

    def cursor(self):
        return FakeBudgetCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


class FakeBudgetCursor:
    def __init__(self, db):
        self.db = db
        self.rowcount = 0
        self.lastrowid = 0
        self._one = None
        self._all = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        query = " ".join(query.split())
        params = params or ()
        self._one = None
        self._all = []
        self.rowcount = 0

        if query.startswith("SELECT id, name FROM categories"):
            household_id = params[0]
            del household_id  # Categories are global in this fixture.
            ids = set(params[1:]) if " AND id IN " in query else set(self.db.categories)
            self._all = [
                {"id": category_id, "name": name}
                for category_id, name in self.db.categories.items()
                if category_id in ids
            ]
        elif query.startswith("SELECT DATE_FORMAT(occurred_on"):
            self._all = deepcopy(self.db.history)
        elif query.startswith("SELECT id, period, income_estimate"):
            household_id, period = params
            self._one = deepcopy(self.db.budgets.get((household_id, period)))
        elif query.startswith("SELECT bl.category_id, c.name, bl.amount"):
            (budget_id,) = params
            self._all = [
                {
                    "category_id": category_id,
                    "name": self.db.categories[category_id],
                    "amount": amount,
                }
                for category_id, amount in sorted(self.db.lines.get(budget_id, {}).items())
            ]
        elif query.startswith("INSERT INTO budgets"):
            household_id, period, income_estimate, savings_goal = params
            key = (household_id, period)
            existing = self.db.budgets.get(key)
            values = {
                "period": period,
                "income_estimate": income_estimate,
                "savings_goal": savings_goal,
                "source": "MANUAL",
                "status": "ACTIVE",
            }
            if existing:
                changed = any(existing.get(name) != value for name, value in values.items())
                existing.update(values)
                self.lastrowid = existing["id"]
                self.rowcount = 2 if changed else 0
            else:
                self.lastrowid = self.db.next_budget_id
                self.db.next_budget_id += 1
                self.db.budgets[key] = {"id": self.lastrowid, **values}
                self.rowcount = 1
            self.db.writes.append(("budget", key))
        elif query.startswith("DELETE FROM budget_lines"):
            (budget_id,) = params
            self.db.lines[budget_id] = {}
            self.rowcount = 1
        else:
            raise AssertionError(f"Unexpected SQL in budget test: {query}")

    def executemany(self, query, rows):
        query = " ".join(query.split())
        assert query.startswith("INSERT INTO budget_lines")
        self.db.writes.append(("budget_lines", tuple(rows)))
        for budget_id, category_id, amount in rows:
            self.db.lines.setdefault(budget_id, {})[category_id] = amount
        self.rowcount = len(rows)

    def fetchone(self):
        return deepcopy(self._one)

    def fetchall(self):
        return deepcopy(self._all)


def _auth(make_token, sub):
    return {"Authorization": f"Bearer {make_token(sub=sub)}"}


def _install_budget_fakes(monkeypatch, db):
    monkeypatch.setattr(
        users,
        "get_or_create_user",
        lambda claims, _token: {"id": 1 if claims["sub"] == "owner" else 2},
    )
    monkeypatch.setattr(budgets, "get_db", lambda: db)
    monkeypatch.setattr(
        budgets,
        "membership",
        lambda _db, user_id: {
            "household_id": 10,
            "role": "owner" if user_id == 1 else "member",
        },
    )


def test_budget_owner_can_save_and_member_can_read_but_not_write(
    client, make_token, monkeypatch
):
    db = FakeBudgetDB()
    _install_budget_fakes(monkeypatch, db)
    payload = {
        "income_estimate": 1_000_000,
        "savings_goal": 100_000,
        "allocations": [
            {"category_id": 1, "amount": 500_000},
            {"category_id": 2, "amount": 200_000},
        ],
    }

    created = client.put(
        "/api/budgets/2026-10", json=payload, headers=_auth(make_token, "owner")
    )
    assert created.status_code == 201
    assert created.get_json()["budget"] == {
        "period": "2026-10",
        "income_estimate": 1_000_000,
        "savings_goal": 100_000,
        "source": "MANUAL",
        "status": "ACTIVE",
        "allocations": [
            {"category_id": 1, "name": "Food", "amount": 500_000},
            {"category_id": 2, "name": "Transport", "amount": 200_000},
        ],
    }

    member_headers = _auth(make_token, "member")
    read = client.get("/api/budgets/2026-10", headers=member_headers)
    denied_put = client.put("/api/budgets/2026-10", json=payload, headers=member_headers)
    denied_suggest = client.post(
        "/api/budgets/2026-10/suggest",
        json={"income_estimate": 1_000_000, "savings_goal": 100_000},
        headers=member_headers,
    )

    assert read.status_code == 200
    assert read.get_json()["budget"] == created.get_json()["budget"]
    assert denied_put.status_code == 403
    assert denied_suggest.status_code == 403


def test_budget_put_updates_and_get_returns_persisted_values(client, make_token, monkeypatch):
    db = FakeBudgetDB()
    _install_budget_fakes(monkeypatch, db)
    headers = _auth(make_token, "owner")
    first = {
        "income_estimate": 1_000_000,
        "savings_goal": 100_000,
        "allocations": [{"category_id": 1, "amount": 400_000}],
    }
    changed = {
        "income_estimate": 1_200_000,
        "savings_goal": 200_000,
        "allocations": [{"category_id": 2, "amount": 800_000}],
    }

    assert client.put("/api/budgets/2026-10", json=first, headers=headers).status_code == 201
    updated = client.put("/api/budgets/2026-10", json=changed, headers=headers)
    loaded = client.get("/api/budgets/2026-10", headers=headers)

    assert updated.status_code == 200
    assert loaded.status_code == 200
    assert loaded.get_json()["budget"] == updated.get_json()["budget"]
    assert loaded.get_json()["budget"]["income_estimate"] == 1_200_000
    assert loaded.get_json()["budget"]["allocations"] == [
        {"category_id": 2, "name": "Transport", "amount": 800_000}
    ]


def test_gemini_suggestion_is_draft_and_does_not_change_saved_budget(
    client, make_token, monkeypatch
):
    db = FakeBudgetDB()
    db.budgets[(10, "2026-10")] = {
        "id": 7,
        "period": "2026-10",
        "income_estimate": 900_000,
        "savings_goal": 100_000,
        "source": "MANUAL",
        "status": "ACTIVE",
    }
    db.lines[7] = {1: 300_000}
    _install_budget_fakes(monkeypatch, db)
    captured = {}

    def gemini(**kwargs):
        captured.update(kwargs)
        return {1: 400_000, 2: 200_000}

    monkeypatch.setattr(budgets, "suggest_with_gemini", gemini)
    before = deepcopy(db.budgets)
    response = client.post(
        "/api/budgets/2026-10/suggest",
        json={"income_estimate": 1_000_000, "savings_goal": 100_000},
        headers=_auth(make_token, "owner"),
    )

    body = response.get_json()["suggestion"]
    assert response.status_code == 200
    assert body["source"] == "LLM"
    assert body["status"] == "DRAFT"
    assert [row["amount"] for row in body["allocations"]] == [400_000, 200_000]
    assert [period for period, _ in captured["monthly_spending"]] == [
        "2026-07",
        "2026-08",
        "2026-09",
    ]
    assert db.budgets == before
    assert db.writes == []


def test_rule_fallback_is_valid_draft_and_does_not_persist(
    client, make_token, monkeypatch
):
    db = FakeBudgetDB()
    db.history = [
        {"period": month, "category_id": 1, "amount": 900_000}
        for month in ("2026-07", "2026-08", "2026-09")
    ]
    _install_budget_fakes(monkeypatch, db)

    def unavailable(**_kwargs):
        raise BudgetSuggestionError("Gemini is unavailable")

    monkeypatch.setattr(budgets, "suggest_with_gemini", unavailable)
    response = client.post(
        "/api/budgets/2026-10/suggest",
        json={"income_estimate": 1_000_000, "savings_goal": 200_000},
        headers=_auth(make_token, "owner"),
    )

    suggestion = response.get_json()["suggestion"]
    assert response.status_code == 200
    assert suggestion["source"] == "RULE"
    assert suggestion["status"] == "DRAFT"
    assert suggestion["allocations"] == [
        {"category_id": 1, "name": "Food", "amount": 800_000}
    ]
    assert sum(row["amount"] for row in suggestion["allocations"]) <= 800_000
    assert db.budgets == {}
    assert db.writes == []


def test_suggestion_rejects_invalid_period_and_savings_above_income(
    client, make_token, monkeypatch
):
    db = FakeBudgetDB()
    _install_budget_fakes(monkeypatch, db)
    headers = _auth(make_token, "owner")

    invalid_period = client.post(
        "/api/budgets/2026-13/suggest",
        json={"income_estimate": 100, "savings_goal": 0},
        headers=headers,
    )
    invalid_savings = client.post(
        "/api/budgets/2026-10/suggest",
        json={"income_estimate": 100, "savings_goal": 101},
        headers=headers,
    )

    assert invalid_period.status_code == 422
    assert invalid_period.get_json()["error"]["code"] == "VALIDATION"
    assert invalid_savings.status_code == 422
    assert invalid_savings.get_json()["error"]["code"] == "VALIDATION"
    assert db.writes == []


@pytest.mark.parametrize(
    "payload",
    [
        {"income_estimate": -1, "savings_goal": 0},
        {"income_estimate": 100, "savings_goal": -1},
        {"income_estimate": 100, "savings_goal": 101},
    ],
)
def test_suggestion_rejects_negative_or_unavailable_income(
    client, make_token, monkeypatch, payload
):
    db = FakeBudgetDB()
    _install_budget_fakes(monkeypatch, db)

    response = client.post(
        "/api/budgets/2026-10/suggest",
        json=payload,
        headers=_auth(make_token, "owner"),
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "VALIDATION"
    assert db.writes == []


def test_rule_fallback_with_missing_history_returns_empty_draft(
    client, make_token, monkeypatch
):
    db = FakeBudgetDB()
    _install_budget_fakes(monkeypatch, db)
    monkeypatch.setattr(
        budgets,
        "suggest_with_gemini",
        lambda **_kwargs: (_ for _ in ()).throw(
            BudgetSuggestionError("Gemini is unavailable")
        ),
    )

    response = client.post(
        "/api/budgets/2026-10/suggest",
        json={"income_estimate": 1_000_000, "savings_goal": 200_000},
        headers=_auth(make_token, "owner"),
    )

    assert response.status_code == 200
    assert response.get_json()["suggestion"] == {
        "period": "2026-10",
        "income_estimate": 1_000_000,
        "savings_goal": 200_000,
        "source": "RULE",
        "status": "DRAFT",
        "allocations": [],
    }
