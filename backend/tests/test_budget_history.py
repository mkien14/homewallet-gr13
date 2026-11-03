from app.budgets import _historical_spending


def test_history_query_formats_parameters_and_groups_previous_three_months():
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, args):
            # PyMySQL uses percent formatting for bind parameters before sending SQL.
            rendered = query % tuple(str(value) for value in args)
            assert "DATE_FORMAT(occurred_on, '%Y-%m')" in rendered

        def fetchall(self):
            return [
                {"period": "2026-07", "category_id": 1, "amount": 150000},
                {"period": "2026-09", "category_id": 2, "amount": 30000},
            ]

    class Database:
        def cursor(self):
            return Cursor()

    assert _historical_spending(Database(), 7, "2026-10") == [
        {1: 150000}, {}, {2: 30000},
    ]
