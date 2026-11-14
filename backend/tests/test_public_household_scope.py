from unittest.mock import MagicMock
import pytest
from app.household_policy import household_admitted
from jobs.household_scope import approved_households, household_filter
from jobs import recurring_alerts, weekly_report


def test_public_job_sql_excludes_retained_household_without_fixed_allowlist():
    scope = approved_households({"APP_ENV": "production", "PRODUCTION_PUBLIC_REGISTRATION": True})
    assert household_filter(scope, "household_id") == (" AND household_id > %s", (1,))
    db = MagicMock()
    cursor = db.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []
    weekly_report._list_households(db, scope)
    recurring_alerts._list_active_bills(db, scope)
    recurring_alerts._active_budget_spending(db, "2026-11", scope)
    queries = cursor.execute.call_args_list
    assert len(queries) == 3
    for query in queries:
        assert "> %s" in query.args[0]
        assert 1 in query.args[1]


def test_missing_policy_keeps_closed_rollout_fail_closed():
    with pytest.raises(ValueError):
        approved_households({"APP_ENV": "production"})
    assert not household_admitted({"APP_ENV": "production"}, 999)
    assert not household_admitted({"APP_ENV": "production", "PRODUCTION_PUBLIC_REGISTRATION": "true"}, 999)
